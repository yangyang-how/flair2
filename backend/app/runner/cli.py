import argparse
import asyncio
import json
import uuid
from pathlib import Path

import structlog

from app.models.pipeline import CreatorProfile, PipelineConfig
from app.providers.registry import get_reasoning_provider
from app.runner.data_loader import load_videos_from_json
from app.runner.local_runner import run_pipeline

logger = structlog.get_logger()


def main():
    parser = argparse.ArgumentParser(description="Flair2 MVP Pipeline — Local Mode")
    parser.add_argument("--data", required=True, help="Path to video dataset (JSON)")
    parser.add_argument("--profile", required=True, help="Path to creator_profile.json")
    parser.add_argument("--provider", default="gemini", help="Reasoning provider (default: gemini)")
    parser.add_argument("--output", default="output.json", help="Output file path")
    parser.add_argument("--limit", type=int, default=100, help="Number of videos to analyze")
    args = parser.parse_args()

    # Load data
    videos = load_videos_from_json(Path(args.data), limit=args.limit)

    # Load creator profile
    profile_data = json.loads(Path(args.profile).read_text())
    profile = CreatorProfile(**profile_data)

    # Build config
    config = PipelineConfig(
        run_id=str(uuid.uuid4()),
        session_id="local",
        reasoning_model=args.provider,
        video_model=None,
        creator_profile=profile,
    )

    # Get provider
    provider = get_reasoning_provider(args.provider)

    # Run pipeline
    logger.info("cli_start", run_id=config.run_id, provider=args.provider, videos=len(videos))
    output = asyncio.run(run_pipeline(config, videos, provider))

    # Save output
    output_path = Path(args.output)
    output_path.write_text(output.model_dump_json(indent=2))
    logger.info("cli_complete", output=str(output_path), results=len(output.results))
    print(f"\nPipeline complete! {len(output.results)} results saved to {output_path}")


if __name__ == "__main__":
    main()
