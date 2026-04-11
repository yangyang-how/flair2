"""Locust load test — M5-4: API concurrent load test.

Runs K concurrent virtual users against the deployed ALB.
Each user starts pipeline runs, lists runs, and checks providers.

Usage:
    # Install locust first:
    pip install locust

    # Against deployed AWS:
    locust -f tests/load/locustfile.py \
        --host http://<ALB_DNS_NAME> \
        --users 10 --spawn-rate 2 --run-time 60s \
        --headless --csv=../../docs/locust-results

    # Multiple K values (run sequentially):
    for K in 1 5 10 20; do
        locust -f tests/load/locustfile.py \
            --host http://<ALB_DNS_NAME> \
            --users $K --spawn-rate $K --run-time 60s \
            --headless --csv=../../docs/locust-k${K}
    done

Issue: https://github.com/yangyang-how/flair2/issues/89
"""

import uuid

from locust import HttpUser, between, task


# Sample creator profile — minimal but valid
SAMPLE_PROFILE = {
    "tone": "casual",
    "vocabulary": ["insane", "literally"],
    "catchphrases": ["here's the thing"],
    "topics_to_avoid": ["politics"],
    "niche": "content creation tips",
    "audience_description": "18-25 aspiring creators",
    "content_themes": ["growth hacks"],
    "example_hooks": ["Stop scrolling"],
    "recent_topics": ["algorithm changes"],
}


class PipelineUser(HttpUser):
    """Simulates a user interacting with the Flair2 API.

    Each virtual user gets a unique session_id so run history
    is properly scoped and doesn't collide across users.
    """

    # Wait 1-3s between tasks to simulate realistic user behavior
    wait_time = between(1, 3)

    def on_start(self):
        """Called once per user when they start. Set up session."""
        self.session_id = str(uuid.uuid4())

    @task(1)
    def get_providers(self):
        """GET /api/providers — lightweight read, should be fast."""
        self.client.get("/api/providers", name="/api/providers")

    @task(2)
    def list_runs(self):
        """GET /api/runs — list runs for this session."""
        self.client.get(
            f"/api/runs?session_id={self.session_id}",
            name="/api/runs",
        )

    @task(3)
    def start_pipeline(self):
        """POST /api/pipeline/start — the heavy operation.

        Uses small counts to avoid overwhelming the LLM provider
        during load tests. The goal is to test API/infra throughput,
        not pipeline completion.
        """
        payload = {
            "creator_profile": SAMPLE_PROFILE,
            "reasoning_model": "kimi",
            "num_videos": 2,
            "num_scripts": 2,
            "num_personas": 2,
            "top_n": 1,
        }
        self.client.post(
            f"/api/pipeline/start?session_id={self.session_id}",
            json=payload,
            name="/api/pipeline/start",
        )

    @task(1)
    def health_check(self):
        """GET /api/health — baseline latency measurement."""
        self.client.get("/api/health", name="/api/health")
