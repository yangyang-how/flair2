from app.providers.gemini import GeminiProvider
from app.providers.kimi import KimiProvider

_reasoning_providers: dict[str, type] = {
    "gemini": GeminiProvider,
    "kimi": KimiProvider,
}
_video_providers: dict[str, type] = {}


def register_reasoning(name: str, cls: type) -> None:
    _reasoning_providers[name] = cls


def register_video(name: str, cls: type) -> None:
    _video_providers[name] = cls


def get_reasoning_provider(name: str, **kwargs):
    if name not in _reasoning_providers:
        raise ValueError(
            f"Unknown reasoning provider: {name}. Available: {list(_reasoning_providers)}"
        )
    return _reasoning_providers[name](**kwargs)


def get_video_provider(name: str, **kwargs):
    if name not in _video_providers:
        raise ValueError(
            f"Unknown video provider: {name}. Available: {list(_video_providers)}"
        )
    return _video_providers[name](**kwargs)


def list_providers() -> dict:
    return {
        "reasoning": list(_reasoning_providers.keys()),
        "video": list(_video_providers.keys()),
    }
