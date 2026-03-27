"""Download Gopher-Lab transcripts + YouTube/TikTok Trends 2025 and prepare pipeline input.

Two data sources, each serving a different purpose:
  1. Gopher-Lab transcripts (~8K) — actual spoken content from proven viral TikTok videos.
     This is what S1 analyzes to learn structural patterns (hooks, pacing, arcs).
  2. YouTube/TikTok Trends 2025 (48K) — engagement signals including completion_rate and
     avg_watch_time. Enriches videos that lack transcripts with retention data.

Produces data/sample_videos.json matching the VideoInput schema:
  { video_id, description, duration, engagement, transcript }

Usage:
  python scripts/prep_dataset.py [--top 100] [--output data/sample_videos.json]
"""

import argparse
import csv
import json
import re
from pathlib import Path

import structlog
from huggingface_hub import hf_hub_download

logger = structlog.get_logger()

# Gopher-Lab transcript datasets (MIT license)
GOPHER_DATASETS = [
    {
        "repo": "Gopher-Lab/TikTok_MostComment_Video_Transcription_Example",
        "file": "TikTok_MostComments.csv",
        "source": "most_commented",
    },
    {
        "repo": "Gopher-Lab/TikTok_Most_Shared_Video_Transcription_Example",
        "file": "Most Shared TikTok - Sheet1.csv",
        "source": "most_shared",
    },
    {
        "repo": "Gopher-Lab/TikTok_Hottest_Video_Transcript_Example",
        "file": "TikTok Hottest - Sheet1.tsv",
        "source": "hottest",
    },
]

# YouTube/TikTok Trends 2025 (CC BY 4.0)
TRENDS_REPO = "tarekmasryo/youtube-tiktok-trends-dataset-2025"
TRENDS_FILE = "data/youtube_shorts_tiktok_trends_2025.csv"


def download_file(repo: str, filename: str) -> Path:
    """Download a file from HuggingFace."""
    logger.info("downloading", repo=repo, file=filename)
    path = hf_hub_download(repo, filename, repo_type="dataset")
    return Path(path)


def parse_gopher_file(path: Path, source: str) -> list[dict]:
    """Parse Gopher-Lab's quasi-JSON format into transcript records.

    These files aren't proper CSV — they're nested pseudo-JSON exported from
    spreadsheets. We extract video_id, title, duration, and transcript content.
    """
    text = path.read_text(errors="replace")
    videos = []

    # Split into blocks by video ID pattern (numeric ID followed by opening brace)
    blocks = re.split(r"\n(\d{15,25}):\s*\{", text)

    # blocks[0] is preamble (the opening '{'), then alternating: id, content, id, content...
    for i in range(1, len(blocks) - 1, 2):
        video_id = blocks[i].strip()
        block = blocks[i + 1]

        # Extract title
        title_match = re.search(r'title:\s*""(.*?)""', block)
        title = title_match.group(1) if title_match else ""

        # Extract duration
        dur_match = re.search(r'duration:\s*""(\d+)""', block)
        duration = float(dur_match.group(1)) if dur_match else 0.0

        # Extract transcript content — the main prize
        content_match = re.search(r'Content:\s*""(.*?)""', block, re.DOTALL)
        transcript = content_match.group(1).strip() if content_match else ""

        # Skip if no transcript (the whole point of using this dataset)
        if not transcript or len(transcript) < 20:
            continue

        videos.append(
            {
                "video_id": video_id,
                "description": title,
                "transcript": transcript,
                "duration": duration,
                "engagement": {
                    # Gopher-Lab doesn't include counts, but we know these are
                    # curated top-performing videos by category
                    "source": source,
                    "curated": True,
                },
            }
        )

    logger.info("parsed_gopher", source=source, videos=len(videos), path=str(path))
    return videos


def load_trends_data() -> dict[str, dict]:
    """Load YouTube/TikTok Trends 2025 as a lookup for engagement enrichment.

    Returns dict keyed by title for fuzzy matching with Gopher-Lab titles.
    Also returns top TikTok videos by engagement for standalone use.
    """
    path = download_file(TRENDS_REPO, TRENDS_FILE)
    records = {}

    with open(path) as f:
        reader = csv.DictReader(f)
        for row in reader:
            # Only TikTok videos (skip YouTube Shorts for now)
            if row.get("platform", "").lower() != "tiktok":
                continue

            title = row.get("title", "").strip()
            if not title:
                continue

            try:
                records[row.get("row_id", title)] = {
                    "title": title,
                    "duration": float(row.get("duration_sec", 0) or 0),
                    "views": int(row.get("views", 0) or 0),
                    "likes": int(row.get("likes", 0) or 0),
                    "comments": int(row.get("comments", 0) or 0),
                    "shares": int(row.get("shares", 0) or 0),
                    "saves": int(row.get("saves", 0) or 0),
                    "completion_rate": float(row.get("completion_rate", 0) or 0),
                    "avg_watch_time": float(row.get("avg_watch_time_sec", 0) or 0),
                    "engagement_rate": float(row.get("engagement_rate", 0) or 0),
                    "hashtag": row.get("hashtag", ""),
                    "category": row.get("category", ""),
                    "tags": row.get("tags", ""),
                    "sample_comments": row.get("sample_comments", ""),
                    "language": row.get("language", ""),
                }
            except (ValueError, TypeError):
                continue

    logger.info("loaded_trends", tiktok_records=len(records))
    return records


def build_trends_videos(trends: dict[str, dict], top_n: int) -> list[dict]:
    """Build VideoInput records from Trends 2025 data for videos without transcripts.

    These have completion_rate + avg_watch_time — the best engagement quality signals.
    Ranked by a composite score: completion_rate * views (reach * retention).
    """
    scored = []
    for row_id, t in trends.items():
        if t["views"] == 0 or t["language"] != "en":
            continue
        # Composite: retention quality * reach
        score = t["completion_rate"] * t["views"]
        scored.append((score, row_id, t))

    scored.sort(key=lambda x: x[0], reverse=True)

    videos = []
    for _, row_id, t in scored[:top_n]:
        desc_parts = [t["title"]]
        if t["hashtag"]:
            desc_parts.append(f"Hashtag: {t['hashtag']}")
        if t["tags"]:
            desc_parts.append(f"Tags: {t['tags']}")
        if t["category"]:
            desc_parts.append(f"Category: {t['category']}")
        if t["sample_comments"]:
            desc_parts.append(f"Top comment: {t['sample_comments']}")

        videos.append(
            {
                "video_id": f"trends_{row_id}",
                "description": "\n".join(desc_parts),
                "transcript": None,
                "duration": t["duration"],
                "engagement": {
                    "views": t["views"],
                    "likes": t["likes"],
                    "comments": t["comments"],
                    "shares": t["shares"],
                    "saves": t["saves"],
                    "completion_rate": t["completion_rate"],
                    "avg_watch_time": t["avg_watch_time"],
                    "engagement_rate": t["engagement_rate"],
                },
            }
        )

    return videos


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Prep Gopher-Lab + Trends 2025 datasets for Flair2 pipeline"
    )
    parser.add_argument("--top", type=int, default=100, help="Total videos to output")
    parser.add_argument("--output", default="data/sample_videos.json", help="Output path")
    args = parser.parse_args()

    # 1. Download and parse Gopher-Lab transcripts (the content S1 actually learns from)
    transcript_videos = []
    for ds in GOPHER_DATASETS:
        path = download_file(ds["repo"], ds["file"])
        videos = parse_gopher_file(path, ds["source"])
        transcript_videos.extend(videos)

    # Filter to English transcripts (check for common English words)
    english_videos = [
        v
        for v in transcript_videos
        if v["transcript"]
        and any(
            word in v["transcript"].lower()
            for word in ["the ", "and ", "you ", "this ", "that ", "what "]
        )
    ]

    logger.info(
        "transcripts_ready",
        total=len(transcript_videos),
        english=len(english_videos),
    )

    # 2. Load Trends 2025 for engagement-rich videos (completion_rate, avg_watch_time)
    trends = load_trends_data()

    # 3. Combine: prioritize transcript videos, fill remaining with top trends videos
    transcript_count = min(len(english_videos), args.top)
    trends_count = max(0, args.top - transcript_count)

    final_videos = english_videos[:transcript_count]
    if trends_count > 0:
        trends_videos = build_trends_videos(trends, trends_count)
        final_videos.extend(trends_videos)
        logger.info("added_trends_videos", count=len(trends_videos))

    # 4. Write output
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(final_videos, indent=2, ensure_ascii=False))

    # Report
    with_transcripts = sum(1 for v in final_videos if v["transcript"])
    without_transcripts = len(final_videos) - with_transcripts
    logger.info(
        "output_written",
        path=str(output_path),
        total=len(final_videos),
        with_transcripts=with_transcripts,
        without_transcripts=without_transcripts,
    )
    print(f"\nDone! {len(final_videos)} videos saved to {output_path}")
    print(f"  {with_transcripts} with transcripts (Gopher-Lab)")
    print(f"  {without_transcripts} with engagement signals only (Trends 2025)")


if __name__ == "__main__":
    main()
