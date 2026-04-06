"""Unit tests for API routes.

Uses FastAPI TestClient with fakeredis for Redis operations.
No real Redis or Celery needed.
"""

import json

import fakeredis.aioredis
import pytest
from httpx import ASGITransport, AsyncClient

from app.api.deps import get_redis
from app.main import app


@pytest.fixture
def fake_redis():
    """Create a fakeredis instance for testing."""
    return fakeredis.aioredis.FakeRedis(decode_responses=True)


@pytest.fixture
async def client(fake_redis):
    """Async test client with fakeredis injected."""

    async def override_redis():
        yield fake_redis

    app.dependency_overrides[get_redis] = override_redis

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
    ) as ac:
        yield ac

    app.dependency_overrides.clear()


# ── Health ───────────────────────────────────────────────────


class TestHealth:
    async def test_health_returns_ok(self, client):
        resp = await client.get("/api/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Providers ────────────────────────────────────────────────


class TestProviders:
    async def test_list_providers(self, client):
        resp = await client.get("/api/providers")
        assert resp.status_code == 200
        data = resp.json()
        assert "reasoning" in data
        assert "video" in data


# ── Pipeline Start ───────────────────────────────────────────


class TestPipelineStart:
    @pytest.fixture
    def valid_request_body(self):
        return {
            "creator_profile": {
                "tone": "casual",
                "vocabulary": ["vibe"],
                "catchphrases": ["let's go"],
                "topics_to_avoid": ["politics"],
            },
            "reasoning_model": "kimi",
            "video_model": None,
            "num_videos": 10,
            "num_scripts": 5,
            "num_personas": 10,
            "top_n": 3,
        }

    async def test_start_returns_run_id(self, client, valid_request_body):
        resp = await client.post("/api/pipeline/start", json=valid_request_body)
        assert resp.status_code == 200
        data = resp.json()
        assert "run_id" in data
        assert len(data["run_id"]) == 36  # UUID format

    async def test_start_creates_redis_state(self, client, fake_redis, valid_request_body):
        resp = await client.post("/api/pipeline/start", json=valid_request_body)
        run_id = resp.json()["run_id"]

        # Verify Redis state was created
        assert await fake_redis.get(f"run:{run_id}:status") == "pending"
        assert await fake_redis.get(f"run:{run_id}:stage") == "PENDING"

        config_raw = await fake_redis.get(f"run:{run_id}:config")
        assert config_raw is not None
        config = json.loads(config_raw)
        assert config["run_id"] == run_id
        assert config["reasoning_model"] == "kimi"
        # Verify pipeline params flow through (#71 Section 6)
        assert config["num_videos"] == 10
        assert config["num_scripts"] == 5
        assert config["num_personas"] == 10
        assert config["top_n"] == 3

    async def test_start_tracks_session(self, client, fake_redis, valid_request_body):
        resp = await client.post(
            "/api/pipeline/start",
            json=valid_request_body,
            params={"session_id": "test-session"},
        )
        run_id = resp.json()["run_id"]

        runs = await fake_redis.lrange("session:test-session:runs", 0, -1)
        assert run_id in runs

    async def test_start_rejects_invalid_body(self, client):
        resp = await client.post("/api/pipeline/start", json={"bad": "data"})
        assert resp.status_code == 422


# ── Pipeline Results ─────────────────────────────────────────


class TestPipelineResults:
    async def test_results_404_for_unknown_run(self, client):
        resp = await client.get("/api/pipeline/results/nonexistent")
        assert resp.status_code == 404

    async def test_results_409_for_incomplete_run(self, client, fake_redis):
        await fake_redis.set("run:test-run:status", "running")
        resp = await client.get("/api/pipeline/results/test-run")
        assert resp.status_code == 409

    async def test_results_returns_data(self, client, fake_redis):
        await fake_redis.set("run:test-run:status", "completed")
        await fake_redis.set(
            "results:final:test-run",
            json.dumps({"results": [], "run_id": "test-run"}),
        )
        resp = await client.get("/api/pipeline/results/test-run")
        assert resp.status_code == 200
        assert resp.json()["run_id"] == "test-run"


# ── Runs List ────────────────────────────────────────────────


class TestRunsList:
    async def test_empty_session(self, client):
        resp = await client.get("/api/runs", params={"session_id": "empty"})
        assert resp.status_code == 200
        assert resp.json()["runs"] == []

    async def test_lists_session_runs(self, client, fake_redis):
        await fake_redis.rpush("session:sess1:runs", "run-a", "run-b")
        await fake_redis.set("run:run-a:status", "completed")
        await fake_redis.set("run:run-a:stage", "COMPLETED")
        await fake_redis.set("run:run-b:status", "running")
        await fake_redis.set("run:run-b:stage", "S4_MAP")

        resp = await client.get("/api/runs", params={"session_id": "sess1"})
        assert resp.status_code == 200
        runs = resp.json()["runs"]
        assert len(runs) == 2
        assert runs[0]["status"] == "completed"
        assert runs[1]["current_stage"] == "S4_MAP"


# ── Video ────────────────────────────────────────────────────


class TestVideo:
    async def test_generate_returns_job_id(self, client, fake_redis):
        await fake_redis.set("run:r1:status", "completed")
        resp = await client.post(
            "/api/video/generate",
            json={"run_id": "r1", "script_id": "s1"},
        )
        assert resp.status_code == 200
        assert "job_id" in resp.json()

    async def test_generate_409_for_incomplete_run(self, client, fake_redis):
        await fake_redis.set("run:r1:status", "running")
        resp = await client.post(
            "/api/video/generate",
            json={"run_id": "r1", "script_id": "s1"},
        )
        assert resp.status_code == 409

    async def test_status_404_for_unknown_job(self, client):
        resp = await client.get("/api/video/status/r1/unknown-job")
        assert resp.status_code == 404


# ── Performance ──────────────────────────────────────────────


class TestPerformance:
    async def test_submit_and_get(self, client, fake_redis):
        body = {
            "run_id": "r1",
            "script_id": "s1",
            "platform": "tiktok",
            "post_url": "https://tiktok.com/@test/123",
            "views": 10000,
            "likes": 500,
            "comments": 50,
            "shares": 100,
        }
        resp = await client.post("/api/performance", json=body)
        assert resp.status_code == 200

        resp = await client.get("/api/performance/r1")
        assert resp.status_code == 200
        perfs = resp.json()["performances"]
        assert len(perfs) == 1
        assert perfs[0]["views"] == 10000

    async def test_insights_returns_structure(self, client):
        resp = await client.get("/api/insights")
        assert resp.status_code == 200
        data = resp.json()
        assert "top_patterns" in data
        assert "total_videos_tracked" in data
