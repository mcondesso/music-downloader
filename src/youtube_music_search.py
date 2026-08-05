"""Module for searching YouTube Music for a track match. Used as the matching
source for every track regardless of where the playlist itself came from
(Spotify or YouTube Music), replacing youtube_id_search.py's free-text search
parsing with ytmusicapi's structured results (exact artist name, exact
duration in seconds) - no login needed, search is fully public."""
from typing import Dict, List, Optional

from ytmusicapi import YTMusic

from src.data_handling import COLUMN_TRACK_DURATION, get_song_search_string

DURATION_THRESHOLD = 0.05
FALLBACK_DURATION_THRESHOLD = 0.50

_ytmusic_search_client: Optional[YTMusic] = None


class NoMatchingYoutubeMusicVideoFoundError(Exception):
    """Exception raised when no matching YouTube Music video could be found."""


def _get_search_client() -> YTMusic:
    global _ytmusic_search_client
    if _ytmusic_search_client is None:
        _ytmusic_search_client = YTMusic()
    return _ytmusic_search_client


def get_youtube_music_search_results(query: str, limit: int = 5) -> List[dict]:
    """Search YouTube Music for tracks matching a query."""
    results = _get_search_client().search(query, filter="songs", limit=limit)
    return [
        {"video_id": r["videoId"], "duration_s": r["duration_seconds"]}
        for r in results
        if r.get("videoId") and r.get("duration_seconds") is not None
    ]


def find_best_matching_youtube_music_video(db_entry: Dict, search_results: List[dict]) -> str:
    """Pick the best-matching video by duration, mirroring youtube_id_search's
    strict-then-fallback threshold approach."""
    db_duration = db_entry[COLUMN_TRACK_DURATION]

    for result in search_results:
        if _is_duration_acceptable(db_duration, result["duration_s"], strict=True):
            return result["video_id"]

    for result in search_results:
        if _is_duration_acceptable(db_duration, result["duration_s"], strict=False):
            return result["video_id"]

    raise NoMatchingYoutubeMusicVideoFoundError(
        f"Unable to find a matching YouTube Music video for {get_song_search_string(db_entry)}"
    )


def _is_duration_acceptable(db_duration: int, result_duration: int, strict: bool = True) -> bool:
    threshold = DURATION_THRESHOLD if strict else FALLBACK_DURATION_THRESHOLD
    return abs(db_duration - result_duration) / db_duration < threshold
