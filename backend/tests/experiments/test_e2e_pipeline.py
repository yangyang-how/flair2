"""M7: End-to-end pipeline smoke test against the deployed environment.

Verifies the full request path that Locust does NOT cover:
  POST /api/pipeline/start
    → SSE stream /api/pipeline/status/{run_id}
    → wait for pipeline_complete event
    → GET /api/pipeline/results/{run_id}
    → assert results contain personalised scripts

All tests are skipped when PIPELINE_BASE_URL is not set (unit / CI runs).

Run after terraform apply + docker deploy:

    export PIPELINE_BASE_URL=http://flair2-dev-alb-xxx.us-west-2.elb.amazonaws.com
    pytest tests/experiments/test_e2e_pipeline.py -v -s

The pipeline makes real LLM calls (Kimi). A single run takes ~2-5 min.
PIPELINE_TIMEOUT_S can be raised if the model is slow.

Issue: closes the gap identified after M5-4 Locust — Locust only tested
the API layer, not pipeline completion.
"""
from __future__ import annotations

import json
import os
import time
import uuid

import httpx
import pytest

# ── Skip entire module when no deployed environment is available ─────────────
PIPELINE_BASE_URL: str | None = os.getenv("PIPELINE_BASE_URL")

pytestmark = pytest.mark.skipif(
    PIPELINE_BASE_URL is None,
    reason="PIPELINE_BASE_URL not set — skipping E2E pipeline experiments",
)

# ── Experiment parameters ────────────────────────────────────────────────────
# Small counts so the run finishes quickly during smoke testing.
# The goal is end-to-end connectivity, not output quality.
PIPELINE_TIMEOUT_S: float = float(os.getenv("PIPELINE_TIMEOUT_S", "300"))
SSE_POLL_TIMEOUT_S: float = PIPELINE_TIMEOUT_S

SAMPLE_START_PAYLOAD: dict = {
    "creator_profile": {
        "tone": "casual",
        "vocabulary": ["honestly", "literally"],
        "catchphrases": ["here's the thing"],
        "topics_to_avoid": [],
        "niche": "productivity tips",
        "audience_description": "18-25 students",
        "content_themes": ["study hacks"],
        "example_hooks": ["Stop wasting time"],
        "recent_topics": ["time management"],
    },
    "reasoning_model": "kimi",
    "num_videos": 2,
    "num_scripts": 2,
    "num_personas": 2,
    "top_n": 1,
}


# ── Helpers ──────────────────────────────────────────────────────────────────

def _base() -> str:
    assert PIPELINE_BASE_URL is not None
    return PIPELINE_BASE_URL.rstrip("/")


def _wait_for_pipeline_complete(run_id: str) -> dict:
    """Open the SSE stream and block until pipeline_complete or pipeline_error.

    Returns the final event data dict.
    Raises TimeoutError if no terminal event arrives within SSE_POLL_TIMEOUT_S.
    Raises RuntimeError if a pipeline_error event is received.
    """
    url = f"{_base()}/api/pipeline/status/{run_id}"
    deadline = time.monotonic() + SSE_POLL_TIMEOUT_S

    with (
        httpx.Client(timeout=SSE_POLL_TIMEOUT_S + 10) as client,
        client.stream("GET", url) as resp,
    ):
        resp.raise_for_status()
        buffer = ""
        for chunk in resp.iter_text():
            if time.monotonic() > deadline:
                raise TimeoutError(
                    f"Pipeline {run_id} did not complete within {SSE_POLL_TIMEOUT_S}s"
                )
            buffer += chunk
            # SSE messages are separated by double newlines
            while "\n\n" in buffer:
                message, buffer = buffer.split("\n\n", 1)
                event_data = _parse_sse_message(message)
                if event_data is None:
                    continue
                event_type = event_data.get("event")
                if event_type == "pipeline_complete":
                    return event_data
                if event_type == "pipeline_error":
                    raise RuntimeError(
                        f"Pipeline {run_id} failed: {event_data}"
                    )
    raise TimeoutError(f"SSE stream closed before pipeline_complete for {run_id}")


def _parse_sse_message(message: str) -> dict | None:
    """Parse a single SSE message block into a dict.

    SSE format:
        event: pipeline_complete
        data: {"event": "pipeline_complete", "data": {...}}
    """
    data_line = None
    for line in message.strip().splitlines():
        if line.startswith("data:"):
            data_line = line[len("data:"):].strip()
    if data_line is None:
        return None
    try:
        return json.loads(data_line)
    except json.JSONDecodeError:
        return None


# ── M7-1: Single run smoke test ──────────────────────────────────────────────

class TestE2EPipelineSingleRun:
    """M7-1: Full pipeline completes end-to-end against the deployed ALB.

    Validates what no other test covers:
    - Real Celery workers pick up tasks from Redis
    - Real LLM calls succeed (Kimi API key is wired in ECS secrets)
    - All 6 stages complete and write results to Redis
    - SSE stream delivers pipeline_complete event
    - /api/pipeline/results returns valid personalised scripts
    """

    def test_pipeline_start_returns_run_id(self) -> None:
        """POST /api/pipeline/start → 200 with a non-empty run_id."""
        session_id = str(uuid.uuid4())
        resp = httpx.post(
            f"{_base()}/api/pipeline/start",
            params={"session_id": session_id},
            json=SAMPLE_START_PAYLOAD,
            timeout=30,
        )
        assert resp.status_code == 200, f"Unexpected {resp.status_code}: {resp.text}"
        body = resp.json()
        assert "run_id" in body, f"Missing run_id in response: {body}"
        assert body["run_id"], "run_id is empty"

    def test_pipeline_completes_and_results_are_valid(self) -> None:
        """Full flow: start → SSE pipeline_complete → results have scripts."""
        session_id = str(uuid.uuid4())

        # 1. Start the pipeline
        resp = httpx.post(
            f"{_base()}/api/pipeline/start",
            params={"session_id": session_id},
            json=SAMPLE_START_PAYLOAD,
            timeout=30,
        )
        assert resp.status_code == 200
        run_id = resp.json()["run_id"]
        print(f"\n[M7-1] Started run {run_id}")

        # 2. Wait for completion via SSE
        t0 = time.monotonic()
        _wait_for_pipeline_complete(run_id)
        elapsed = time.monotonic() - t0
        print(f"[M7-1] Pipeline completed in {elapsed:.1f}s")

        # 3. Fetch results
        results_resp = httpx.get(
            f"{_base()}/api/pipeline/results/{run_id}",
            timeout=30,
        )
        assert results_resp.status_code == 200, (
            f"Results endpoint returned {results_resp.status_code}: {results_resp.text}"
        )
        results = results_resp.json()

        # 4. Validate structure
        assert "results" in results, f"No 'results' key in response: {results}"
        scripts = results["results"]
        assert len(scripts) > 0, "results list is empty"

        first = scripts[0]
        assert "script_id" in first
        assert "personalized_script" in first
        assert first["personalized_script"], "personalized_script is empty"

        print(f"[M7-1] Got {len(scripts)} result(s). "
              f"First script_id: {first['script_id']}")


# ── M7-2: Concurrent runs complete without interfering ───────────────────────

class TestE2EPipelineConcurrent:
    """M7-2: Two concurrent pipeline runs both complete without interference.

    Complements test_multi_user.py (fakeredis + mocked tasks) by running
    against the real deployed stack.
    """

    def test_two_concurrent_runs_complete(self) -> None:
        import threading

        results: dict[str, dict | Exception] = {}

        def run_pipeline(label: str) -> None:
            session_id = str(uuid.uuid4())
            try:
                resp = httpx.post(
                    f"{_base()}/api/pipeline/start",
                    params={"session_id": session_id},
                    json=SAMPLE_START_PAYLOAD,
                    timeout=30,
                )
                resp.raise_for_status()
                run_id = resp.json()["run_id"]
                print(f"\n[M7-2] {label} started: {run_id}")
                _wait_for_pipeline_complete(run_id)
                results[label] = {"run_id": run_id, "status": "completed"}
                print(f"[M7-2] {label} completed")
            except Exception as exc:
                results[label] = exc

        threads = [
            threading.Thread(target=run_pipeline, args=(f"run-{i}",))
            for i in range(2)
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=PIPELINE_TIMEOUT_S + 30)

        for label, result in results.items():
            assert not isinstance(result, Exception), (
                f"{label} raised: {result}"
            )
            assert result["status"] == "completed"
