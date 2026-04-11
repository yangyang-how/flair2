"""Frontend integration tests using Playwright.

Tests the three M4-A pages against a running backend + frontend.
Requires:
  - Redis on localhost:6379
  - Backend on localhost:8001
  - Frontend on localhost:4324 (with PUBLIC_API_URL=http://localhost:8001)

Usage:
    python scripts/test_frontend.py
"""

import json
import subprocess
import sys
import time
import uuid
from threading import Thread

import redis
from playwright.sync_api import sync_playwright

FRONTEND_URL = "http://localhost:4324"
REDIS_URL = "redis://localhost:6379/0"
SCREENSHOT_DIR = "/tmp/flair2-screenshots"

r = redis.from_url(REDIS_URL, decode_responses=True)


def emit(run_id: str, event: str, data: dict) -> str:
    payload = json.dumps({
        "event": event,
        "data": data,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    return r.xadd(f"sse:{run_id}", {"payload": payload})


def setup_completed_run() -> str:
    """Create a completed run in Redis with full results."""
    run_id = str(uuid.uuid4())
    r.set(f"run:{run_id}:status", "completed")

    script_ids = [f"script_{uuid.uuid4().hex[:8]}" for _ in range(3)]
    results = {
        "run_id": run_id,
        "results": [
            {
                "script_id": sid,
                "original_script": {
                    "script_id": sid,
                    "pattern_used": ["curiosity_gap", "hot_take", "story_hook"][i],
                    "hook": f"Test hook {i+1} — this is the opening line",
                    "body": f"Test body {i+1} — main content goes here with details",
                    "payoff": f"Test payoff {i+1} — call to action closing",
                    "estimated_duration": 30.0 + i * 10,
                    "structural_notes": "Test structural notes",
                },
                "personalized_script": f"Personalized version of script {i+1}...",
                "video_prompt": f"Video prompt for script {i+1}: fast cuts, dramatic lighting...",
                "rank": i + 1,
                "vote_score": round(20.0 - i * 3.5, 1),
            }
            for i, sid in enumerate(script_ids)
        ],
        "creator_profile": {
            "tone": "casual",
            "vocabulary": [],
            "catchphrases": [],
            "topics_to_avoid": [],
        },
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    r.set(f"results:final:{run_id}", json.dumps(results))

    # Also add SSE events so pipeline/vote pages work
    emit(run_id, "pipeline_started", {"run_id": run_id, "total_videos": 5, "total_personas": 10, "top_n": 3})
    for stage in ["S1_MAP", "S2_REDUCE", "S3_SEQUENTIAL", "S4_MAP", "S5_REDUCE", "S6_PERSONALIZE"]:
        emit(run_id, "stage_started", {"stage": stage, "total_items": 5})
    emit(run_id, "s2_complete", {"pattern_count": 4})
    emit(run_id, "s3_complete", {"script_count": 3})
    for i in range(10):
        emit(run_id, "vote_cast", {
            "persona_id": f"p{i}",
            "top_5": script_ids,
            "completed": i + 1,
            "total": 10,
        })
    emit(run_id, "s5_complete", {"top_ids": script_ids, "top_n": 3})
    emit(run_id, "pipeline_complete", {"run_id": run_id, "result_count": 3})

    return run_id


def setup_live_run() -> str:
    """Create a run that will receive events slowly (for live SSE testing)."""
    run_id = str(uuid.uuid4())
    r.set(f"run:{run_id}:status", "running")
    r.set(f"run:{run_id}:stage", "S1_MAP")
    return run_id


def emit_live_events(run_id: str):
    """Emit events slowly to test live SSE updates."""
    time.sleep(1)  # Give browser time to connect

    emit(run_id, "pipeline_started", {
        "run_id": run_id, "total_videos": 5, "total_personas": 10, "top_n": 3,
    })
    time.sleep(0.5)

    emit(run_id, "stage_started", {"stage": "S1_MAP", "total_items": 5})
    for i in range(1, 6):
        time.sleep(0.8)
        emit(run_id, "s1_progress", {"video_id": f"v{i}", "completed": i, "total": 5})

    time.sleep(0.5)
    emit(run_id, "stage_started", {"stage": "S2_REDUCE", "total_items": 1})
    time.sleep(1)
    emit(run_id, "s2_complete", {"pattern_count": 4})

    time.sleep(0.5)
    emit(run_id, "stage_started", {"stage": "S3_SEQUENTIAL", "total_items": 1})
    time.sleep(1)
    emit(run_id, "s3_complete", {"script_count": 3})

    r.set(f"run:{run_id}:status", "completed")
    emit(run_id, "pipeline_complete", {"run_id": run_id, "result_count": 3})


def run_tests():
    import os
    os.makedirs(SCREENSHOT_DIR, exist_ok=True)

    passed = 0
    failed = 0
    errors = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(viewport={"width": 1280, "height": 800})

        # ── Test 1: Results page loads with completed run ──────
        print("\n[TEST 1] Results page — completed run")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/results/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            page.screenshot(path=f"{SCREENSHOT_DIR}/01_results_loading.png", full_page=True)

            # Check for results content
            content = page.content()
            has_results_heading = "Campaign Results" in content
            has_scripts_tab = "Scripts" in content
            has_prompts_tab = "Video Prompts" in content
            has_hook = "Test hook 1" in content or "hook" in content.lower()

            if has_results_heading and has_scripts_tab and has_prompts_tab:
                print("  PASS: Results page loaded with tabs")
                passed += 1
            else:
                msg = f"Missing: heading={has_results_heading}, scripts={has_scripts_tab}, prompts={has_prompts_tab}"
                print(f"  FAIL: {msg}")
                errors.append(f"Test 1: {msg}")
                failed += 1

            page.screenshot(path=f"{SCREENSHOT_DIR}/01_results_final.png", full_page=True)
            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 1: {e}")
            failed += 1

        # ── Test 2: Results page — expand a script card ────────
        print("\n[TEST 2] Results page — expand script card")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/results/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            # Click "Expand" button
            expand_btn = page.locator("text=Expand").first
            if expand_btn.is_visible():
                expand_btn.click()
                page.wait_for_timeout(500)
                page.screenshot(path=f"{SCREENSHOT_DIR}/02_results_expanded.png", full_page=True)

                content = page.content()
                has_body = "Test body" in content or "Body" in content
                has_personalized = "Personalized" in content
                has_generate = "Generate Video" in content

                if has_body and has_personalized and has_generate:
                    print("  PASS: Script card expanded with all sections")
                    passed += 1
                else:
                    msg = f"Missing: body={has_body}, personalized={has_personalized}, generate={has_generate}"
                    print(f"  FAIL: {msg}")
                    errors.append(f"Test 2: {msg}")
                    failed += 1
            else:
                print("  FAIL: No Expand button found")
                errors.append("Test 2: No Expand button")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 2: {e}")
            failed += 1

        # ── Test 3: Results page — Video Prompts tab ───────────
        print("\n[TEST 3] Results page — Video Prompts tab")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/results/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            # Click Video Prompts tab
            prompts_tab = page.locator("text=Video Prompts")
            if prompts_tab.is_visible():
                prompts_tab.click()
                page.wait_for_timeout(500)
                page.screenshot(path=f"{SCREENSHOT_DIR}/03_video_prompts.png", full_page=True)

                content = page.content()
                has_prompt = "Video prompt for script" in content or "dramatic lighting" in content

                if has_prompt:
                    print("  PASS: Video Prompts tab shows prompts")
                    passed += 1
                else:
                    print("  FAIL: Video prompt content not found")
                    errors.append("Test 3: prompt content missing")
                    failed += 1
            else:
                print("  FAIL: Video Prompts tab not found")
                errors.append("Test 3: tab not found")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 3: {e}")
            failed += 1

        # ── Test 4: Pipeline page — completed run shows all stages done ──
        print("\n[TEST 4] Pipeline page — completed run")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/pipeline/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            page.screenshot(path=f"{SCREENSHOT_DIR}/04_pipeline_completed.png", full_page=True)

            content = page.content()
            has_heading = "Pipeline Progress" in content or "Pipeline" in content
            has_stages = "Discover" in content and "Aggregate" in content and "Generate" in content
            has_completed = content.count("completed") >= 3  # Multiple completed badges

            if has_heading and has_stages:
                print("  PASS: Pipeline page loaded with stages")
                passed += 1
            else:
                msg = f"Missing: heading={has_heading}, stages={has_stages}"
                print(f"  FAIL: {msg}")
                errors.append(f"Test 4: {msg}")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 4: {e}")
            failed += 1

        # ── Test 5: Vote page — completed run shows avatars ───
        print("\n[TEST 5] Vote page — completed run")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/vote/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(3000)

            page.screenshot(path=f"{SCREENSHOT_DIR}/05_vote_completed.png", full_page=True)

            content = page.content()
            has_heading = "Audience Vote" in content
            has_leaderboard = "Leaderboard" in content
            has_vote_count = "10" in content  # 10 votes cast

            if has_heading and has_leaderboard:
                print("  PASS: Vote page loaded with leaderboard")
                passed += 1
            else:
                msg = f"Missing: heading={has_heading}, leaderboard={has_leaderboard}"
                print(f"  FAIL: {msg}")
                errors.append(f"Test 5: {msg}")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 5: {e}")
            failed += 1

        # ── Test 6: Pipeline page — live SSE updates ──────────
        print("\n[TEST 6] Pipeline page — live SSE streaming")
        try:
            run_id = setup_live_run()
            page = context.new_page()

            # Start emitting events in background
            thread = Thread(target=emit_live_events, args=(run_id,), daemon=True)
            thread.start()

            page.goto(f"{FRONTEND_URL}/pipeline/{run_id}")
            page.wait_for_load_state("networkidle")

            # Wait for some events to arrive
            page.wait_for_timeout(3000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_pipeline_live_1.png", full_page=True)

            # Check for running state
            content1 = page.content()
            has_running = "running" in content1.lower()

            # Wait for more progress
            page.wait_for_timeout(4000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_pipeline_live_2.png", full_page=True)
            content2 = page.content()

            # Wait for completion
            thread.join(timeout=15)
            page.wait_for_timeout(3000)
            page.screenshot(path=f"{SCREENSHOT_DIR}/06_pipeline_live_3.png", full_page=True)
            content3 = page.content()

            has_complete = "complete" in content3.lower() or "Done" in content3

            if has_running or has_complete:
                print("  PASS: Live SSE events received and rendered")
                passed += 1
            else:
                print("  FAIL: No evidence of live updates")
                errors.append("Test 6: no live updates detected")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 6: {e}")
            failed += 1

        # ── Test 7: Navigation breadcrumbs ─────────────────────
        print("\n[TEST 7] Navigation breadcrumbs")
        try:
            run_id = setup_completed_run()
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/results/{run_id}")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            content = page.content()
            has_home_link = 'href="/"' in content
            has_runs_link = 'href="/runs"' in content
            has_pipeline_link = f'href="/pipeline/{run_id}"' in content

            if has_home_link and has_runs_link and has_pipeline_link:
                print("  PASS: Breadcrumbs have correct navigation links")
                passed += 1
            else:
                msg = f"Missing: home={has_home_link}, runs={has_runs_link}, pipeline={has_pipeline_link}"
                print(f"  FAIL: {msg}")
                errors.append(f"Test 7: {msg}")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 7: {e}")
            failed += 1

        # ── Test 8: Results page — 404 for nonexistent run ────
        print("\n[TEST 8] Results page — handles missing run")
        try:
            page = context.new_page()
            page.goto(f"{FRONTEND_URL}/results/nonexistent-run-id")
            page.wait_for_load_state("networkidle")
            page.wait_for_timeout(2000)

            page.screenshot(path=f"{SCREENSHOT_DIR}/08_results_404.png", full_page=True)

            content = page.content()
            has_error = "Failed" in content or "error" in content.lower() or "not found" in content.lower()

            if has_error:
                print("  PASS: Error state shown for missing run")
                passed += 1
            else:
                print("  FAIL: No error state for missing run")
                errors.append("Test 8: no error state")
                failed += 1

            page.close()
        except Exception as e:
            print(f"  ERROR: {e}")
            errors.append(f"Test 8: {e}")
            failed += 1

        browser.close()

    # ── Summary ────────────────────────────────────────────
    print(f"\n{'='*50}")
    print(f"Results: {passed} passed, {failed} failed")
    print(f"Screenshots saved to {SCREENSHOT_DIR}/")
    if errors:
        print("\nFailures:")
        for e in errors:
            print(f"  - {e}")

    return failed == 0


if __name__ == "__main__":
    success = run_tests()
    sys.exit(0 if success else 1)
