"""Module for searching YouTube Music for a track match. Used as the matching
source for every track regardless of where the playlist itself came from
(Spotify or Tidal), replacing youtube_id_search.py's free-text search parsing
with ytmusicapi's structured results (exact artist name, exact duration in
seconds) - no login needed, search is fully public."""
from typing import Dict, List, Optional

from ytmusicapi import YTMusic

from src.data_handling import (
    DURATION_THRESHOLD,
    FALLBACK_DURATION_THRESHOLD,
    find_closest_matching_result,
    get_song_search_string,
)

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
        {
            "video_id": r["videoId"],
            "duration_s": r["duration_seconds"],
            "title": f"{' '.join(a['name'] for a in r.get('artists') or [] if a.get('name'))} {r.get('title', '')}".strip(),
        }
        for r in results
        if r.get("videoId") and r.get("duration_seconds") is not None
    ]


def find_best_matching_youtube_music_video(db_entry: Dict, search_results: List[dict]) -> str:
    """Pick the best-matching video: the closest-duration result, among those
    within threshold, whose title/artists text plausibly matches the song -
    duration alone isn't enough to tell two unrelated tracks of similar length apart."""
    match = find_closest_matching_result(
        db_entry, search_results, "duration_s", "title", DURATION_THRESHOLD
    )
    if match is None:
        match = find_closest_matching_result(
            db_entry, search_results, "duration_s", "title", FALLBACK_DURATION_THRESHOLD
        )
    if match is None:
        raise NoMatchingYoutubeMusicVideoFoundError(
            f"Unable to find a matching YouTube Music video for {get_song_search_string(db_entry)}"
        )
    return match["video_id"]
