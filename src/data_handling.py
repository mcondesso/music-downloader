"""Module for handling file reading and writing data files."""
import re
from typing import Dict, List, Optional, Tuple

from src.csv_handling import read_csv

# Column names
COLUMN_ARTIST_NAME = "Artist Name(s)"
COLUMN_TRACK_NAME = "Track Name"
REQUIRED_COLUMNS = [COLUMN_ARTIST_NAME, COLUMN_TRACK_NAME]
COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES = {"Track Duration (ms)", "Duration (ms)"}
COLUMN_GENRES = "Genres"
COLUMN_TEMPO = "Tempo"
COLUMN_TRACK_DURATION = "Duration (s)"
COLUMN_YOUTUBE_ID = "Youtube ID"
COLUMN_SOUNDCLOUD_URL = "Soundcloud URL"
COLUMN_ABSOLUTE_FILEPATH = "Absolute Filepath"
COLUMN_BIT_RATE = "Bit rate (kbps)"


class RequiredColumnNameNotFoundError(Exception):
    """Exception raised when one of the required column names is missing"""


class TrackDurationColumnNameNotFoundError(RequiredColumnNameNotFoundError):
    """Exception raised when none of the known column names for the track duration matches"""


def get_data_list_from_exportify_csv(filepath: str) -> Tuple[List[dict], List[str]]:
    """This function loads, validates and standardizes data
    from a CSV file obtained via Exportify."""
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = read_csv(filepath)

    # Find column with Track Duration
    track_duration_col = _get_track_duration_column_name(total_colnames)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    # Select only relevant columns
    column_names = REQUIRED_COLUMNS + [
        track_duration_col,
        COLUMN_GENRES,
        COLUMN_TEMPO,
    ]

    selected_df = []
    for row in data:
        # Copy over the selected columns
        selected_row = {key: row[key] for key in column_names}

        # Rename and convert Duration column to seconds
        selected_row[COLUMN_TRACK_DURATION] = (
            int(selected_row.pop(track_duration_col)) // 1000
        )

        # Ensure that commas have a trailing space and replace multiple whitespaces
        artist_name = selected_row[COLUMN_ARTIST_NAME].replace(",", ", ")
        selected_row[COLUMN_ARTIST_NAME] = re.sub(r"\s+", " ", artist_name)

        selected_df.append(selected_row)

    final_column_names = REQUIRED_COLUMNS + [
        COLUMN_TRACK_DURATION,
        COLUMN_GENRES,
        COLUMN_TEMPO,
    ]

    return selected_df, final_column_names


def get_data_list_from_csv_with_ids(filepath: str) -> List[dict]:
    """This function loads and validates data from a file with the song youtube IDs."""
    # Read full CSV into a list of dicts and extract column names
    data, total_colnames = read_csv(filepath)

    # Validate that other required columns are present
    for col in REQUIRED_COLUMNS + [COLUMN_YOUTUBE_ID]:
        if col not in total_colnames:
            raise RequiredColumnNameNotFoundError(f"Column '{col}' is missing")

    return data


def _get_track_duration_column_name(field_names: List) -> str:
    """This function is used to figure out which column name from exportify
    contains the track duration data"""
    for column_name in COLUMN_TRACK_DURATION_EXPORTIFY_ALTERNATIVES:
        if column_name in field_names:
            return column_name
    raise TrackDurationColumnNameNotFoundError(
        "Unable to find the Track Duration column"
    )


def get_song_search_string(music_row: Dict) -> str:
    """Helper function to generate the search string a song."""
    return f"{music_row[COLUMN_ARTIST_NAME]} - {music_row[COLUMN_TRACK_NAME]}"


_TRAILING_ORIGINAL_MIX_RE = re.compile(r"\s*-\s*original\s+mix\s*$", re.IGNORECASE)


def get_song_search_string_variants(music_row: Dict) -> List[str]:
    """Query strings to try against a search source, most-preferred first.

    A literal trailing "- Original Mix" in the query text throws off YouTube
    Music's search ranking - verified empirically: the exact same query with
    that suffix stripped finds the correct track as the #1 result, while
    keeping it returns unrelated tracks. The full query (with "Original Mix")
    is tried first since it's the more precise, preferred match target; a
    second variant with the suffix stripped is offered only as a fallback for
    when the full query's results don't produce a match. Matching itself
    (duration/title thresholds) is unaffected either way - this only changes
    what's typed into the search box, not what counts as a match."""
    full = get_song_search_string(music_row)
    track_name = music_row[COLUMN_TRACK_NAME]
    stripped_track_name = _TRAILING_ORIGINAL_MIX_RE.sub("", track_name)
    if stripped_track_name == track_name:
        return [full]
    return [full, f"{music_row[COLUMN_ARTIST_NAME]} - {stripped_track_name}"]


def get_youtube_url(music_row: Dict) -> str:
    """Helper function to generate the youtube URL for a song."""
    return f"https://www.youtube.com/watch?v={music_row[COLUMN_YOUTUBE_ID]}"


def get_song_filename(music_row: Dict) -> str:
    """Helper function to generate the filename for a song,
    escaping slashes."""
    search_string = get_song_search_string(music_row=music_row)
    return sanitize_filename(search_string)


def sanitize_filename(filename: str) -> str:
    """Replaces invalid chars in filenames with underscores."""
    invalid_chars = r'\/:*?"<>|'
    translation_table = str.maketrans(invalid_chars, "_" * len(invalid_chars))
    sanitized = filename.translate(translation_table)
    return sanitized


_BRACKETED_CONTENT_RE = re.compile(r"[\(\[][^\)\]]*[\)\]]")
_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")

# Shared across every search source (SoundCloud, YouTube Music, YouTube) so their
# matching behavior stays in sync and there's a single place to retune them.
TITLE_MATCH_THRESHOLD = 0.6
DURATION_THRESHOLD = 0.05
FALLBACK_DURATION_THRESHOLD = 0.15

# Words that signal a candidate is a different version of the song (remix, edit,
# alternate cut...) rather than the plain original. Only relevant when they show up
# in a candidate's title but not in the expected "Artist - Track" search string -
# a track we're *actually* looking for a remix of has that word in its own title
# too, so it's never flagged as foreign. These aren't stripped from bracketed text
# (unlike _normalize_search_words) since that's exactly where they usually live,
# e.g. "(Moksi Switch Up)" or "(Extended Mix)".
VERSION_MARKER_WORDS = {
    "remix", "rmx", "edit", "mashup", "bootleg", "flip", "vip", "rework",
    "refix", "redo", "switch", "cover", "acoustic", "instrumental", "acapella",
}

# Connector words that show up around a version marker without introducing a new
# name, e.g. "(feat. Vintage Culture)" - ignored when deciding whether a candidate
# introduces content genuinely outside the expected artists/track.
VERSION_FILLER_WORDS = {"feat", "ft", "featuring", "with", "x", "vs", "and", "the", "a", "an"}


def _normalize_search_words(text: str) -> List[str]:
    """Lowercases, strips bracketed noise (e.g. "(Official Video)", "(feat. X)")
    and punctuation, splitting the result into a bag of words for fuzzy comparison."""
    text = _BRACKETED_CONTENT_RE.sub(" ", text.lower())
    text = _NON_ALNUM_RE.sub(" ", text)
    return [word for word in text.split() if word]


def _all_words(text: str) -> List[str]:
    """Like _normalize_search_words, but keeps bracketed content - used for the
    version-marker check, where that's exactly where the signal usually lives."""
    text = _NON_ALNUM_RE.sub(" ", text.lower())
    return [word for word in text.split() if word]


def is_title_match(expected: str, candidate: str, threshold: float = TITLE_MATCH_THRESHOLD) -> bool:
    """Whether `candidate` (a search result's title/artist text) plausibly refers to
    the same song as `expected` (an "Artist - Track" search string), based on what
    fraction of the expected artist/track words show up in the candidate. This is a
    second, independent signal alongside duration - a result can have a matching
    length while being a completely different song."""
    expected_words = set(_normalize_search_words(expected))
    candidate_words = set(_normalize_search_words(candidate))
    if not expected_words or not candidate_words:
        return False
    return len(expected_words & candidate_words) / len(expected_words) >= threshold


def has_unexpected_version_marker(expected: str, candidate: str) -> bool:
    """Whether `candidate`'s title introduces a remix/edit/alternate-version marker
    that isn't present in `expected`, *and* also introduces a name/word we don't
    already expect (a new remixer, a different uploader...). A marker word alone
    isn't suspicious - a track can be officially released and credited as e.g.
    "(Artist B Remix)" where Artist B is already one of the expected artists, and
    the db's Track Name field just doesn't spell that out. It's only a sign of a
    different, uncredited version when it comes bundled with unexpected content."""
    expected_words = set(_all_words(expected))
    candidate_words = set(_all_words(candidate))
    if not (candidate_words & VERSION_MARKER_WORDS) - expected_words:
        return False
    unexpected_words = candidate_words - expected_words - VERSION_MARKER_WORDS - VERSION_FILLER_WORDS
    return bool(unexpected_words)


def find_closest_matching_result(
    db_entry: Dict,
    search_results: List[dict],
    duration_key: str,
    title_key: str,
    duration_threshold: float,
    title_threshold: float = TITLE_MATCH_THRESHOLD,
) -> Optional[dict]:
    """Among search results within `duration_threshold` of the db entry's duration,
    whose title text plausibly matches, and that don't introduce an unexpected
    remix/edit marker, return the one with the closest duration. Returns None if
    nothing qualifies - callers should treat that as "no match on this source",
    not settle for a same-length but differently-versioned result."""
    db_duration = db_entry[COLUMN_TRACK_DURATION]
    expected = get_song_search_string(db_entry)
    # A multi-artist collab's own name words (e.g. 3 credited artists) can by
    # themselves clear is_title_match's overlap threshold even when the
    # candidate is a completely different song by that same collab - the track
    # name's own words barely move the ratio. Requiring at least one of them to
    # actually appear closes that hole without needing an exact title match.
    track_name_words = set(_normalize_search_words(db_entry[COLUMN_TRACK_NAME]))
    candidates = [
        result
        for result in search_results
        if abs(db_duration - result[duration_key]) / db_duration < duration_threshold
        and is_title_match(expected, result[title_key], threshold=title_threshold)
        and not has_unexpected_version_marker(expected, result[title_key])
        and (not track_name_words or track_name_words & set(_normalize_search_words(result[title_key])))
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda result: abs(db_duration - result[duration_key]))
