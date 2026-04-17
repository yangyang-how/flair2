import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.providers.kimi import KimiProvider


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
            result = await kimi_provider.generate_text("Give JSON", schema=dict)
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
        good_resp = _mock_message('{"valid": true}')
        with patch.object(kimi_provider, "_get_client") as mock_client_fn:
            mock_client = MagicMock()
            mock_client.messages.create = AsyncMock(side_effect=[bad_resp, good_resp])
            mock_client_fn.return_value = mock_client
            result = await kimi_provider.generate_text("Give JSON", schema=dict)
            assert json.loads(result) == {"valid": True}
            assert mock_client.messages.create.call_count == 2


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
