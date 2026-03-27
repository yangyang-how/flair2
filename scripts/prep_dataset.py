"""Download TikTok-10M from HuggingFace and extract top videos by engagement.

Produces data/sample_videos.json matching the VideoInput schema:
  { video_id, description, duration, engagement, transcript }

Usage:
  python scripts/prep_dataset.py [--top 100] [--output data/sample_videos.json]
"""

import argparse
import json
from pathlib import Path

import pyarrow.parquet as pq
import structlog
from huggingface_hub import hf_hub_download

logger = structlog.get_logger()

REPO_ID = "The-data-company/TikTok-10M"
# Only need the first chunk (1M rows) — plenty to find top 100
PARQUET_FILE = "data/train-00000-of-00010.parquet"

# Columns we actually need — skip the rest for speed
COLUMNS = [
    "id",
    "desc",
    "duration",
    "play_count",
    "digg_count",
    "comment_count",
    "share_count",
    "collect_count",
    "challenges",
    "music_title",
]


def download_chunk() -> Path:
    """Download first parquet chunk from HuggingFace."""
    logger.info("downloading_dataset", repo=REPO_ID, file=PARQUET_FILE)
    path = hf_hub_download(REPO_ID, PARQUET_FILE, repo_type="dataset")
    logger.info("download_complete", path=path)
    return Path(path)


def compute_engagement_score(row: dict) -> float:
    """Weighted engagement score — mirrors TikTok's algorithm priorities.

    Rewatch/play is king, then saves (collect), shares, comments, likes.
    Weights from the design doc's engagement hierarchy.
    """
    return (
        row["play_count"] * 1.0
        + row["collect_count"] * 8.0
        + row["share_count"] * 6.0
        + row["comment_count"] * 4.0
        + row["digg_count"] * 2.0
    )


def extract_top_videos(parquet_path: Path, top_n: int) -> list[dict]:
    """Read parquet, rank by engagement, return top N as VideoInput dicts."""
    logger.info("reading_parquet", path=str(parquet_path))
    table = pq.read_table(parquet_path, columns=COLUMNS)
    df = table.to_pydict()
    num_rows = len(df["id"])
    logger.info("loaded_rows", count=num_rows)

    # Build list of (score, index) for sorting
    scored = []
    for i in range(num_rows):
        # Skip videos with missing engagement data
        play = df["play_count"][i]
        if play is None or play == 0:
            continue

        score = compute_engagement_score(
            {
                "play_count": play or 0,
                "digg_count": df["digg_count"][i] or 0,
                "comment_count": df["comment_count"][i] or 0,
                "share_count": df["share_count"][i] or 0,
                "collect_count": df["collect_count"][i] or 0,
            }
        )
        scored.append((score, i))

    # Sort descending by score, take top N
    scored.sort(key=lambda x: x[0], reverse=True)
    top_indices = [idx for _, idx in scored[:top_n]]

    logger.info(
        "top_videos_selected",
        count=len(top_indices),
        min_score=scored[top_n - 1][0] if len(scored) >= top_n else 0,
        max_score=scored[0][0] if scored else 0,
    )

    # Convert to VideoInput format
    videos = []
    for i in top_indices:
        # Parse challenges JSON if present
        challenges_raw = df["challenges"][i]
        challenge_tags = []
        if challenges_raw:
            try:
                if isinstance(challenges_raw, str):
                    challenges_data = json.loads(challenges_raw)
                else:
                    challenges_data = challenges_raw
                if isinstance(challenges_data, list):
                    challenge_tags = [
                        c.get("title", "") for c in challenges_data if isinstance(c, dict)
                    ]
            except (json.JSONDecodeError, TypeError):
                pass

        # Build rich description from available fields
        desc = df["desc"][i] or ""
        music = df["music_title"][i] or ""
        if challenge_tags:
            desc += f"\nChallenges: {', '.join(challenge_tags)}"
        if music:
            desc += f"\nMusic: {music}"

        video = {
            "video_id": str(df["id"][i]),
            "description": desc.strip() or None,
            "transcript": None,  # TikTok-10M doesn't include transcripts
            "duration": float(df["duration"][i] or 0),
            "engagement": {
                "play_count": df["play_count"][i] or 0,
                "digg_count": df["digg_count"][i] or 0,
                "comment_count": df["comment_count"][i] or 0,
                "share_count": df["share_count"][i] or 0,
                "collect_count": df["collect_count"][i] or 0,
            },
        }
        videos.append(video)

    return videos


def main() -> None:
    parser = argparse.ArgumentParser(description="Prep TikTok-10M dataset for Flair2 pipeline")
    parser.add_argument("--top", type=int, default=100, help="Number of top videos to extract")
    parser.add_argument("--output", default="data/sample_videos.json", help="Output path")
    args = parser.parse_args()

    parquet_path = download_chunk()
    videos = extract_top_videos(parquet_path, args.top)

    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(videos, indent=2, ensure_ascii=False))

    logger.info("output_written", path=str(output_path), videos=len(videos))
    print(f"\nDone! {len(videos)} videos saved to {output_path}")


if __name__ == "__main__":
    main()
