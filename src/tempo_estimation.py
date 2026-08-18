"""Module for estimating a track's tempo locally via audio beat-tracking, since
Spotify's audio-features endpoint (the usual source of tempo) isn't available to
apps created after Nov 2024 - see spotify_export.py."""
import librosa
import numpy as np


def estimate_tempo(filepath: str) -> float:
    """Estimate a track's tempo in BPM by analyzing its audio."""
    y, sr = librosa.load(filepath)
    tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
    return float(np.ravel(tempo)[0])
