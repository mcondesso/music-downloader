"""Module for handling youtube search."""
import re
from datetime import datetime
from typing import Dict, List

from youtube_search import YoutubeSearch

from src.data_handling import COLUMN_TRACK_DURATION, get_song_search_string

DURATION_THRESHOLD = 0.05
FALLBACK_DURATION_THRESHOLD = 0.50  # 50% threshold for fallback matching


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
    # Parse time string
    time_format = _find_time_string_format(time_str)
    time_obj = datetime.strptime(time_str, time_format)

    # Calculate total duration in seconds
    total_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second

    return total_seconds


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
    
    We first try to find a video with duration close to the Spotify track (5% threshold).
    If no exact match is found, we fall back to the best available match within 50% threshold,
    prioritizing by YouTube's relevance ranking.
    """
    db_duration = db_entry[COLUMN_TRACK_DURATION]
    
    # First pass: try to find exact matches within strict threshold
    for result in search_results:
        if _is_video_duration_acceptable(db_duration, result["Duration (s)"], strict=True):
            return result["ID"]
    
    # Second pass: find fallback matches within relaxed threshold
    fallback_candidates = []
    for result in search_results:
        if _is_video_duration_acceptable(db_duration, result["Duration (s)"], strict=False):
            fallback_candidates.append(result)
    
    if fallback_candidates:
        # Return the first (most relevant) fallback candidate
        return fallback_candidates[0]["ID"]
    
    raise NoMatchingYoutubeVideoFoundError(
        f"Unable to find a matching youtube video for {get_song_search_string(db_entry)}"
    )


def _is_video_duration_acceptable(db_duration: int, result_duration: int, strict: bool = True) -> bool:
    """Function to define the threshold whether a youtube stream duration is a valid match.
    
    Args:
        db_duration: Duration from Spotify track in seconds
        result_duration: Duration from YouTube video in seconds  
        strict: If True, use strict 5% threshold. If False, use 50% fallback threshold.
    """
    threshold = DURATION_THRESHOLD if strict else FALLBACK_DURATION_THRESHOLD
    return abs(db_duration - result_duration) / db_duration < threshold
