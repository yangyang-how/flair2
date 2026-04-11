"""Simulate a pipeline run by injecting SSE events into Redis.

Writes the same Redis keys/events the orchestrator would, but without
needing Celery, LLM APIs, or a dataset. Used for frontend testing.

Usage:
    python scripts/simulate_pipeline.py [--run-id <uuid>] [--speed <multiplier>]
"""

import argparse
import json
import time
import uuid

import redis

REDIS_URL = "redis://localhost:6379/0"


def emit(r: redis.Redis, run_id: str, event: str, data: dict) -> str:
    """Add an event to the SSE stream, matching orchestrator format."""
    payload = json.dumps({
        "event": event,
        "data": data,
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    })
    msg_id = r.xadd(f"sse:{run_id}", {"payload": payload})
    print(f"  [{msg_id}] {event}: {json.dumps(data)}")
    return msg_id


def simulate(run_id: str, speed: float = 1.0):
    """Run a full pipeline simulation."""
    r = redis.from_url(REDIS_URL, decode_responses=True)

    num_videos = 10
    num_scripts = 5
    num_personas = 20
    top_n = 3

    # Set up run state (what the orchestrator does on start)
    r.set(f"run:{run_id}:status", "running")
    r.set(f"run:{run_id}:stage", "S1_MAP")

    print(f"\nSimulating pipeline run: {run_id}")
    print(f"  videos={num_videos}, scripts={num_scripts}, personas={num_personas}, top_n={top_n}")
    print(f"  speed={speed}x\n")

    delay = lambda s: time.sleep(s / speed)

    # Pipeline started
    emit(r, run_id, "pipeline_started", {
        "run_id": run_id,
        "total_videos": num_videos,
        "total_personas": num_personas,
        "top_n": top_n,
    })
    delay(0.5)

    # S1: Discover (fan-out)
    emit(r, run_id, "stage_started", {"stage": "S1_MAP", "total_items": num_videos})
    for i in range(1, num_videos + 1):
        delay(0.3)
        emit(r, run_id, "s1_progress", {
            "video_id": f"vid_{i:03d}",
            "completed": i,
            "total": num_videos,
        })
    r.set(f"run:{run_id}:stage", "S2_REDUCE")
    delay(0.5)

    # S2: Aggregate (single task)
    emit(r, run_id, "stage_started", {"stage": "S2_REDUCE", "total_items": 1})
    delay(1.0)
    emit(r, run_id, "s2_complete", {"pattern_count": 8})
    r.set(f"run:{run_id}:stage", "S3_SEQUENTIAL")
    delay(0.5)

    # S3: Generate scripts (sequential)
    emit(r, run_id, "stage_started", {"stage": "S3_SEQUENTIAL", "total_items": 1})
    delay(1.5)
    emit(r, run_id, "s3_complete", {"script_count": num_scripts})

    # Generate script IDs for voting
    script_ids = [f"script_{uuid.uuid4().hex[:8]}" for _ in range(num_scripts)]
    r.set(f"run:{run_id}:stage", "S4_MAP")
    delay(0.5)

    # S4: Vote (fan-out)
    emit(r, run_id, "stage_started", {"stage": "S4_MAP", "total_items": num_personas})
    import random
    for i in range(1, num_personas + 1):
        delay(0.2)
        top_5 = random.sample(script_ids, min(5, len(script_ids)))
        emit(r, run_id, "vote_cast", {
            "persona_id": f"persona_{i:03d}",
            "top_5": top_5,
            "completed": i,
            "total": num_personas,
        })
    r.set(f"run:{run_id}:stage", "S5_REDUCE")
    delay(0.5)

    # S5: Rank (single task)
    emit(r, run_id, "stage_started", {"stage": "S5_REDUCE", "total_items": 1})
    delay(1.0)
    top_ids = script_ids[:top_n]
    emit(r, run_id, "s5_complete", {"top_ids": top_ids, "top_n": top_n})
    r.set(f"run:{run_id}:stage", "S6_PERSONALIZE")
    delay(0.5)

    # S6: Personalize (fan-out over top_n)
    emit(r, run_id, "stage_started", {"stage": "S6_PERSONALIZE", "total_items": top_n})
    for i in range(1, top_n + 1):
        delay(0.5)
        emit(r, run_id, "s6_progress", {
            "script_id": top_ids[i - 1],
            "completed": i,
            "total": top_n,
        })
    delay(0.3)

    # Write final results to Redis (what results endpoint reads)
    results = {
        "run_id": run_id,
        "results": [
            {
                "script_id": sid,
                "original_script": {
                    "script_id": sid,
                    "pattern_used": random.choice(["curiosity_gap", "hot_take", "story_hook", "challenge"]),
                    "hook": f"You won't believe what happens when you try this {random.choice(['simple', 'weird', 'secret'])} trick...",
                    "body": f"Here's the thing nobody tells you about content creation. The algorithm doesn't care about your production value. It cares about retention. Every second counts, and the first 3 seconds are everything.",
                    "payoff": f"Try this on your next video and watch what happens. Comment below with your results.",
                    "estimated_duration": random.uniform(15, 60),
                    "structural_notes": "Opens with pattern interrupt, builds tension, closes with CTA",
                },
                "personalized_script": f"So like... nobody's talking about this but {random.choice(['the algorithm', 'engagement', 'watch time'])} is completely different now. I tested this on my last {random.randint(3, 10)} videos and the results are insane. Drop a comment if you want the full breakdown.",
                "video_prompt": f"Fast-paced montage. Open on close-up of creator's face, dramatic lighting. Cut to screen recording showing analytics dashboard. Text overlay: 'THE SECRET'. Background music: trending lo-fi beat. Duration: {random.randint(15, 45)}s.",
                "rank": rank,
                "vote_score": round(random.uniform(5, 20), 1),
            }
            for rank, sid in enumerate(top_ids, 1)
        ],
        "creator_profile": {
            "tone": "casual",
            "vocabulary": ["insane", "literally", "no cap"],
            "catchphrases": ["here's the thing", "watch this"],
            "topics_to_avoid": ["politics"],
            "niche": "content creation tips",
            "audience_description": "18-25 aspiring creators",
            "content_themes": ["growth hacks", "algorithm tips"],
            "example_hooks": ["Stop scrolling, this is important"],
            "recent_topics": ["TikTok algorithm changes"],
        },
        "completed_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    r.set(f"results:final:{run_id}", json.dumps(results))

    # Pipeline complete
    r.set(f"run:{run_id}:status", "completed")
    emit(r, run_id, "pipeline_complete", {"run_id": run_id, "result_count": top_n})

    print(f"\nDone. Pipeline {run_id} completed.")
    print(f"  View pipeline: http://localhost:4321/pipeline/{run_id}")
    print(f"  View voting:   http://localhost:4321/vote/{run_id}")
    print(f"  View results:  http://localhost:4321/results/{run_id}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Simulate a pipeline run for frontend testing")
    parser.add_argument("--run-id", default=str(uuid.uuid4()), help="Run ID (default: random UUID)")
    parser.add_argument("--speed", type=float, default=2.0, help="Speed multiplier (default: 2.0)")
    args = parser.parse_args()
    simulate(args.run_id, args.speed)
