import pytest

from app.providers.usage import UsageTracker


class TestUsageTracker:
    def test_record_request(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1500)
        assert tracker.total_requests == 1
        assert tracker.total_input_tokens == 100
        assert tracker.total_output_tokens == 200

    def test_record_multiple_stages(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        tracker.record("S1", input_tokens=150, output_tokens=250, latency_ms=1200)
        tracker.record("S3", input_tokens=80, output_tokens=500, latency_ms=3000)

        assert tracker.total_requests == 3
        assert tracker.total_input_tokens == 330
        assert tracker.total_output_tokens == 950

        s1 = tracker.stage_stats("S1")
        assert s1["requests"] == 2
        assert s1["input_tokens"] == 250
        assert s1["output_tokens"] == 450
        assert s1["avg_latency_ms"] == 1100

    def test_stage_stats_empty(self):
        tracker = UsageTracker()
        s1 = tracker.stage_stats("S1")
        assert s1["requests"] == 0

    def test_summary_table(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        tracker.record("S3", input_tokens=80, output_tokens=500, latency_ms=3000)
        table = tracker.summary_table()
        assert "S1" in table
        assert "S3" in table
        assert "TOTAL" in table

    def test_progress_string(self):
        tracker = UsageTracker()
        tracker.record("S1", input_tokens=100, output_tokens=200, latency_ms=1000)
        progress = tracker.progress("S1", completed=5, total=100)
        assert "5/100" in progress
        assert "S1" in progress
