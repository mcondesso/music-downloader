"""Module for searching SoundCloud tracks via its (unofficial) api-v2 endpoints -
the same ones soundcloud.com's own web player uses. There's no official public
API key program anymore, so this scrapes a client_id out of SoundCloud's own JS
bundles, the same way it always resolves the ones its own web player uses."""
import re
from typing import Dict, List, Optional

import requests

from src.data_handling import COLUMN_TRACK_DURATION, get_song_search_string

USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0 Safari/537.36"
)
HEADERS = {"User-Agent": USER_AGENT}

SEARCH_URL = "https://api-v2.soundcloud.com/search/tracks"
RESOLVE_URL = "https://api-v2.soundcloud.com/resolve"

DURATION_THRESHOLD = 0.05
FALLBACK_DURATION_THRESHOLD = 0.50

_cached_client_id: Optional[str] = None


class NoMatchingSoundcloudTrackFoundError(Exception):
    """Exception raised when no matching SoundCloud track could be found."""


class SoundcloudClientIdUnavailableError(Exception):
    """Exception raised when a working SoundCloud client_id could not be scraped."""


def get_client_id() -> str:
    """Get a working SoundCloud client_id, reusing a cached one if it's still
    valid. Candidates scraped from SoundCloud's JS bundles are validated against
    a real API call rather than trusted on regex match alone - bundles can
    contain unrelated strings that happen to match the pattern."""
    global _cached_client_id
    if _cached_client_id and _is_client_id_valid(_cached_client_id):
        return _cached_client_id

    for candidate in _scrape_client_id_candidates():
        if _is_client_id_valid(candidate):
            _cached_client_id = candidate
            return candidate

    raise SoundcloudClientIdUnavailableError("Could not obtain a working SoundCloud client_id")


def _scrape_client_id_candidates() -> List[str]:
    html = requests.get("https://soundcloud.com", headers=HEADERS, timeout=15).text
    script_srcs = [
        src for src in re.findall(r'<script[^>]+src="([^"]+)"', html) if "sndcdn.com" in src
    ]
    candidates = []
    # SoundCloud's own config tends to live in one of the later-loaded bundles.
    for src in reversed(script_srcs):
        js = requests.get(src, headers=HEADERS, timeout=15).text
        candidates.extend(re.findall(r'client_id\s*[:=]\s*"([a-zA-Z0-9]{16,})"', js))
    return candidates


def _is_client_id_valid(client_id: str) -> bool:
    try:
        response = requests.get(
            SEARCH_URL,
            params={"q": "a", "client_id": client_id, "limit": 1},
            headers=HEADERS,
            timeout=10,
        )
        return response.status_code == 200
    except requests.RequestException:
        return False


def search_soundcloud_tracks(query: str, limit: int = 5) -> List[dict]:
    """Search SoundCloud for tracks matching a query."""
    client_id = get_client_id()
    response = requests.get(
        SEARCH_URL,
        params={"q": query, "client_id": client_id, "limit": limit},
        headers=HEADERS,
        timeout=15,
    )
    response.raise_for_status()

    results = []
    for track in response.json().get("collection", []):
        if track.get("kind") != "track" or not track.get("permalink_url"):
            continue
        results.append(
            {
                "permalink_url": track["permalink_url"],
                "duration_s": track["duration"] // 1000,
            }
        )
    return results


def find_best_matching_soundcloud_track(db_entry: Dict, search_results: List[dict]) -> str:
    """Pick the best-matching SoundCloud track by duration, mirroring
    find_best_matching_youtube_id's strict-then-fallback threshold approach."""
    db_duration = db_entry[COLUMN_TRACK_DURATION]

    for result in search_results:
        if _is_duration_acceptable(db_duration, result["duration_s"], strict=True):
            return result["permalink_url"]

    for result in search_results:
        if _is_duration_acceptable(db_duration, result["duration_s"], strict=False):
            return result["permalink_url"]

    raise NoMatchingSoundcloudTrackFoundError(
        f"Unable to find a matching SoundCloud track for {get_song_search_string(db_entry)}"
    )


def _is_duration_acceptable(db_duration: int, result_duration: int, strict: bool = True) -> bool:
    threshold = DURATION_THRESHOLD if strict else FALLBACK_DURATION_THRESHOLD
    return abs(db_duration - result_duration) / db_duration < threshold
