from datetime import datetime
import re
from typing import List

from pandas.core.series import Series
from youtube_search import YoutubeSearch

from src.data_handling import get_song_filename


DURATION_THRESHOLD = 0.05


class NoMatchingYoutubeVideoFoundError(Exception):
    """Exception raised when no matching youtube video could be found"""


def get_youtube_search_results(input_string: str, n_results: int = 5) -> List[dict]:
    # Make GET request to youtube
    raw_results = YoutubeSearch(
        search_terms=input_string, max_results=n_results
    ).to_dict()

    # Extract the relevant data and format it
    formatted_results = [
        {
            "ID": result["id"],
            "Views": _youtube_result_views_to_integer(str(result["views"])),
            "Duration (s)": _youtube_result_duration_to_seconds(result["duration"]),
        }
        for result in raw_results
    ]
    return formatted_results


def _youtube_result_views_to_integer(youtube_views: str) -> int:
    numeric_string = re.sub(r"\D", "", youtube_views)
    return int(numeric_string)


def _youtube_result_duration_to_seconds(time_str: str) -> int:
    # Parse time string
    time_format = "%H:%M:%S" if len(time_str.split(":")) == 3 else "%M:%S"
    time_obj = datetime.strptime(time_str, time_format)

    # Calculate total duration in seconds
    total_seconds = time_obj.hour * 3600 + time_obj.minute * 60 + time_obj.second

    return total_seconds


def find_best_matching_youtube_id(db_entry: Series, search_results: List[dict]) -> str:
    for result in search_results:
        if _is_video_duration_acceptable(
            db_entry["Duration (s)"], result["Duration (s)"]
        ):
            return result["ID"]
    raise NoMatchingYoutubeVideoFoundError(
        f"Unable to find a matching youtube video for {get_song_filename(db_entry)}"
    )


def _is_video_duration_acceptable(db_duration: int, result_duration: int) -> bool:
    # If video duration matches down to DURATION_THRESHOLD, assume it's good
    return abs(db_duration - result_duration) / db_duration < DURATION_THRESHOLD
