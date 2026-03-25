import pytest

from app.providers.registry import get_reasoning_provider, list_providers


def test_list_providers_includes_gemini():
    providers = list_providers()
    assert "gemini" in providers["reasoning"]


def test_get_gemini_provider():
    provider = get_reasoning_provider("gemini")
    assert provider.name == "gemini"
    assert hasattr(provider, "generate_text")
    assert hasattr(provider, "analyze_content")


def test_get_unknown_provider_raises():
    with pytest.raises(ValueError, match="Unknown reasoning provider"):
        get_reasoning_provider("nonexistent")
