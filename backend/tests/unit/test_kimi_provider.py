import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from pydantic import BaseModel

from app.models.errors import InvalidResponseError
from app.providers.kimi import KimiProvider


class _TinySchema(BaseModel):
    key: str


@pytest.fixture
def kimi_provider():
    return KimiProvider(api_key="sk-kimi-test-key")


def _mock_message(text: str, input_tokens: int = 10, output_tokens: int = 20):
    """Build a mock Anthropic Message response."""
    msg = MagicMock()
    block = MagicMock()
    block.text = text
    msg.content = [block]
    msg.usage.input_tokens = input_tokens
    msg.usage.output_tokens = output_tokens
    return msg


class TestKimiProviderProtocol:
    def test_has_name(self, kimi_provider):
        assert kimi_provider.name == "kimi"

    def test_has_generate_text(self, kimi_provider):
        assert hasattr(kimi_provider, "generate_text")
        assert callable(kimi_provider.generate_text)

    def test_has_analyze_content(self, kimi_provider):
        assert hasattr(kimi_provider, "analyze_content")
        assert callable(kimi_provider.analyze_content)


class TestGenerateText:
    @pytest.mark.asyncio
    async def test_returns_text(self, kimi_provider):
        mock_resp = _mock_message("Hello world")
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.generate_text("Say hello")
            assert result == "Hello world"

    @pytest.mark.asyncio
    async def test_extracts_json_when_schema(self, kimi_provider):
        json_str = json.dumps({"key": "value"})
        wrapped = f"```json\n{json_str}\n```"
        mock_resp = _mock_message(wrapped)
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.generate_text("Give JSON", schema=_TinySchema)
            parsed = json.loads(result)
            assert parsed == {"key": "value"}

    @pytest.mark.asyncio
    async def test_returns_token_usage(self, kimi_provider):
        mock_resp = _mock_message("text", input_tokens=50, output_tokens=100)
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            await kimi_provider.generate_text("test")
            assert kimi_provider.last_usage == {"input_tokens": 50, "output_tokens": 100}

    @pytest.mark.asyncio
    async def test_passes_temperature_when_specified(self, kimi_provider):
        mock_resp = _mock_message("ok")
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            await kimi_provider.generate_text("test", temperature=0.2)
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert call_kwargs["temperature"] == 0.2

    @pytest.mark.asyncio
    async def test_omits_temperature_when_none(self, kimi_provider):
        mock_resp = _mock_message("ok")
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            await kimi_provider.generate_text("test")
            call_kwargs = mock_client.messages.create.call_args.kwargs
            assert "temperature" not in call_kwargs


class TestRetryBehavior:
    @pytest.mark.asyncio
    async def test_retries_on_invalid_json(self, kimi_provider):
        bad_resp = _mock_message("not json")
        good_resp = _mock_message('{"key": "ok"}')
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=[bad_resp, good_resp])
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.generate_text("Give JSON", schema=_TinySchema)
            assert json.loads(result) == {"key": "ok"}
            assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_retries_on_schema_mismatch(self, kimi_provider):
        """Valid JSON but wrong shape — retry, don't fail immediately."""
        wrong_shape = _mock_message('{"not_the_right_field": "oops"}')
        right_shape = _mock_message('{"key": "recovered"}')
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(
                side_effect=[wrong_shape, right_shape]
            )
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.generate_text(
                "Give JSON", schema=_TinySchema
            )
            assert json.loads(result) == {"key": "recovered"}
            assert mock_client.messages.create.call_count == 2

    @pytest.mark.asyncio
    async def test_raises_invalid_response_after_max_schema_retries(self, kimi_provider):
        wrong = _mock_message('{"not_the_right_field": "oops"}')
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=wrong)
            mock_client_fn.return_value = mock_client
            with pytest.raises(InvalidResponseError) as exc_info:
                await kimi_provider.generate_text("Give JSON", schema=_TinySchema)
            assert "_TinySchema" in str(exc_info.value)
            assert mock_client.messages.create.call_count == 3


class TestRateLimitRetryBudget:
    """429 errors get a separate retry budget, independent of the main attempt counter."""

    @pytest.mark.asyncio
    async def test_retries_on_429_and_succeeds(self, kimi_provider):
        """First 3 calls raise 429 — each triggers a rate-limit retry, 4th succeeds."""
        good_resp = _mock_message("success")
        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count <= 3:
                raise Exception("429 Too Many Requests: rate limit exceeded")
            return good_resp

        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = fake_create
            mock_client_fn.return_value = mock_client
            with patch("asyncio.sleep", return_value=None):
                result = await kimi_provider.generate_text("test")

        assert result == "success"
        assert call_count == 4  # 3 rate-limited retries + 1 success

    @pytest.mark.asyncio
    async def test_raises_rate_limit_error_after_budget_exhausted(self, kimi_provider):
        """After RATE_LIMIT_MAX_RETRIES 429s, RateLimitError raised with retry_after hint."""
        from app.models.errors import RateLimitError
        from app.providers.kimi import RATE_LIMIT_BACKOFF

        async def fake_create(**kwargs):
            raise Exception("429 rate limit hit")

        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = fake_create
            mock_client_fn.return_value = mock_client
            with (
                patch("asyncio.sleep", return_value=None),
                pytest.raises(RateLimitError) as exc_info,
            ):
                await kimi_provider.generate_text("test")

        assert exc_info.value.retry_after == RATE_LIMIT_BACKOFF[-1]

    @pytest.mark.asyncio
    async def test_rate_limit_retry_does_not_burn_main_budget(self, kimi_provider):
        """One 429 followed by success: main attempt counter stays at 1."""
        good_resp = _mock_message("ok")
        call_count = 0

        async def fake_create(**kwargs):
            nonlocal call_count
            call_count += 1
            if call_count == 1:
                raise Exception("429 rate limit")
            return good_resp

        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = fake_create
            mock_client_fn.return_value = mock_client
            with patch("asyncio.sleep", return_value=None):
                result = await kimi_provider.generate_text("test")

        assert result == "ok"
        assert call_count == 2  # 1 rate-limited + 1 success (main budget never decremented)


class TestAnalyzeContent:
    @pytest.mark.asyncio
    async def test_combines_content_and_prompt(self, kimi_provider):
        mock_resp = _mock_message("analysis result")
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(return_value=mock_resp)
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.analyze_content("video data", "analyze this")
            assert result == "analysis result"
            call_args = mock_client.messages.create.call_args
            messages = call_args[1]["messages"]
            user_msg = messages[-1]["content"]
            assert "video data" in user_msg
            assert "analyze this" in user_msg
