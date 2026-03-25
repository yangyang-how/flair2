import json
from pathlib import Path

import structlog

from app.models.stages import VideoInput

logger = structlog.get_logger()


def load_videos_from_json(path: Path, limit: int = 100) -> list[VideoInput]:
    """Load videos from a JSON file (array of video objects)."""
    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError(f"Expected JSON array, got {type(data)}")
    videos = [VideoInput(**v) for v in data[:limit]]
    logger.info("loaded_videos", count=len(videos), source=str(path))
    return videos
