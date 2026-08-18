"""Module for handling youtube search."""
import re
from datetime import datetime
from typing import Dict, List

from youtube_search import YoutubeSearch

from src.data_handling import (
    DURATION_THRESHOLD,
    FALLBACK_DURATION_THRESHOLD,
    find_closest_matching_result,
    get_song_search_string,
)


class NoMatchingYoutubeVideoFoundError(Exception):
    """Exception raised when no matching youtube video could be found"""


def get_youtube_search_results(input_string: str, n_results: int = 5) -> List[dict]:
    """This function searches a string on youtube, loads and sorts the best 5 potential matches"""
    # Make GET request to youtube
    raw_results = YoutubeSearch(
        search_terms=input_string, max_results=n_results
    ).to_dict()

    # Extract the relevant data and format it
    formatted_results = [
        {
            "ID": result["id"],
            "Views": _youtube_result_views_to_integer(str(result["views"])),
            "Duration (s)": _youtube_result_duration_to_seconds(
                str(result["duration"])
            ),
            "Title": f"{result.get('channel', '')} {result.get('title', '')}".strip(),
        }
        for result in raw_results
    ]
    return formatted_results


def _youtube_result_views_to_integer(youtube_views: str) -> int:
    """Function to convert the youtube result views format into an integer."""
    numeric_string = re.sub(r"\D", "", youtube_views)
    return int(numeric_string if numeric_string else 0)


def _youtube_result_duration_to_seconds(time_str: str) -> int:
    """Function to convert the youtube result duration format into the number of seconds."""
    normalized_time_str = _get_normalized_time_str(time_str)
    # Parse time string
    time_format = _find_time_string_format(normalized_time_str)
    time_obj = datetime.strptime(normalized_time_str, time_format)

    # Calculate total duration in seconds
    total_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second

    return total_seconds


def _get_normalized_time_str(time_str):
    # Handle fractional seconds: only remove if it's clearly fractional (after seconds in a time format)
    # Look for pattern like "1:23.456" or "45.123" where the decimal part is likely fractional seconds
    # But preserve "8.51" as "8:51" (minutes:seconds)
    # If there's a decimal followed by 3+ digits, it's likely fractional seconds
    if re.search(r'\.\d{3,}', time_str):
        time_str = re.sub(r'\.\d+.*$', '', time_str)
    # If format is like "XX.Y" where Y > 59, it's likely fractional seconds
    elif re.search(r'\.\d{1,2}$', time_str):
        match = re.search(r'\.(\d{1,2})$', time_str)
        if match and int(match.group(1)) > 59:
            time_str = re.sub(r'\.\d+.*$', '', time_str)
    # Now normalize remaining dot separators to colon separators (e.g., "8.51" -> "8:51")
    normalized_time_str = time_str.replace('.', ':')
    return normalized_time_str


def _find_time_string_format(time_str: str) -> str:
    """Function to find the format used by the youtube result duration."""
    match len(time_str.split(":")):
        case 1:
            time_format = "%S"
        case 2:
            time_format = "%M:%S"
        case 3:
            time_format = "%H:%M:%S"
        case _:
            raise ValueError(f"Format of '{time_str}' is not supported")
    return time_format


def find_best_matching_youtube_id(db_entry: Dict, search_results: List[dict]) -> str:
    """Function to pick the best match out of the results.

    We first try to find the closest-duration video within a strict 5% threshold
    whose title/channel text plausibly matches the song. If nothing qualifies, we
    fall back to a relaxed 15% duration threshold, still gated by the same title
    check - duration alone isn't enough to tell two unrelated videos of similar
    length apart.
    """
    match = find_closest_matching_result(
        db_entry, search_results, "Duration (s)", "Title", DURATION_THRESHOLD
    )
    if match is None:
        match = find_closest_matching_result(
            db_entry, search_results, "Duration (s)", "Title", FALLBACK_DURATION_THRESHOLD
        )
    if match is None:
        raise NoMatchingYoutubeVideoFoundError(
            f"Unable to find a matching youtube video for {get_song_search_string(db_entry)}"
        )
    return match["ID"]
