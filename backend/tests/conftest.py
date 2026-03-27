import pytest


@pytest.fixture
def sample_creator_profile():
    from app.models.pipeline import CreatorProfile

    return CreatorProfile(
        tone="casual and energetic",
        vocabulary=["vibe", "insane", "lowkey", "no cap"],
        catchphrases=["let's gooo", "wait for it"],
        topics_to_avoid=["politics", "religion"],
    )


class MockReasoningProvider:
    """Mock provider returning canned JSON for each stage."""

    name = "mock"

    def __init__(self):
        self.call_log: list[str] = []

    async def generate_text(self, prompt: str, schema=None) -> str:
        self.call_log.append(prompt[:50])
        return "Mock generated text response."

    async def analyze_content(self, content: str, prompt: str) -> str:
        self.call_log.append(f"analyze: {prompt[:50]}")
        return await self.generate_text(prompt)


@pytest.fixture
def mock_provider():
    return MockReasoningProvider()
