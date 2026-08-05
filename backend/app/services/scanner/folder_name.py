"""Fallback metadata hints parsed from release folder names and filenames.

Scene rips frequently ship fully untagged: the only album/artist metadata
lives in the directory name (``Artist-Album-16BIT-44-KHZ-WEB-FLAC-2021-GROUP``)
and the per-track filenames (``01-artist-title.flac``). The helpers here turn
those into *hints* used only when audio files carry no embedded tags — to seed
the beets autotag query and to populate the "Local Album" summary so it is not
blank. They are heuristics, never authoritative: real embedded tags always take
precedence over anything derived here.
"""

import html
import os
import re
from typing import Optional, Tuple

__all__ = ["parse_album_folder_name", "parse_title_from_filename"]

# Whole "-"-delimited tokens a scene release appends after "Artist-Album":
# container/codec, source, and quality markers. The leftmost such token marks
# the start of the scene suffix; everything from there to the end (including the
# trailing group name, which we cannot recognise generically) is dropped.
_SCENE_TOKENS = {
    # containers / codecs
    "flac", "mp3", "m4a", "aac", "wav", "ape", "wv", "ogg", "opus", "alac",
    "ac3", "dts", "dsd", "dsf", "mqa", "wma", "aiff", "aif",
    # sources
    "web", "webflac", "cd", "cda", "cdda", "cdr", "cdm", "cds", "cdep",
    "cdrip", "vinyl", "lp", "sacd", "dvd", "dvda", "bd", "bluray", "hdcd",
    "sat", "dab", "fm", "line", "tape", "cassette", "md", "dat", "sbd",
    # quality / release markers
    "lossless", "repack", "reissue", "remastered", "remaster", "retail",
    "promo", "bootleg", "limited", "scene", "readnfo", "nfo",
}

# Patterns that also mark the scene suffix: a 4-digit year, a bit-depth
# (16BIT/24BIT), a sample rate (44KHZ / 96KHZ), a bitrate (320KBPS / 320K) or a
# channel count (2CH). Matched case-insensitively against a whole token.
_SCENE_PATTERNS = [
    re.compile(r"^(19|20)\d{2}$"),
    re.compile(r"^\d{1,2}bits?$"),
    re.compile(r"^\d{1,3}(\.\d+)?khz$"),
    re.compile(r"^khz$"),
    re.compile(r"^\d{2,4}kbps$"),
    re.compile(r"^\d{2,4}k$"),
    re.compile(r"^\d(\.\d)?ch$"),
]


def _is_scene_token(token: str) -> bool:
    """Return True if a "-"-delimited token looks like scene-suffix metadata."""
    t = token.strip().lower()
    if not t:
        return False
    if t in _SCENE_TOKENS:
        return True
    return any(p.match(t) for p in _SCENE_PATTERNS)


def _clean(value: str) -> str:
    """Collapse internal whitespace and trim separator clutter."""
    return re.sub(r"\s+", " ", value).strip(" -_.")


def parse_album_folder_name(name: str) -> Tuple[Optional[str], Optional[str]]:
    """Derive ``(artist, album)`` hints from a release folder name.

    Decodes HTML entities (``&amp;`` -> ``&``), strips scene-release suffixes,
    collapses runs of whitespace, and splits the remainder into artist/album on
    the first ``-`` boundary. Returns ``(None, None)`` when nothing usable
    remains; either element may be ``None`` on its own (a single-token folder
    yields an album but no artist).
    """
    if not name:
        return None, None

    decoded = html.unescape(name)
    # Tokenise on "-": both scene suffixes and "Artist-Album" use it as the
    # primary separator, with or without surrounding spaces.
    tokens = [t.strip() for t in decoded.split("-")]

    # Cut at the leftmost scene-suffix token, but never at index 0 (that would
    # drop the whole name); keep at least one leading token for artist/album.
    cut = len(tokens)
    for i, tok in enumerate(tokens):
        if i >= 1 and _is_scene_token(tok):
            cut = i
            break
    core = [t for t in tokens[:cut] if t]

    if not core:
        return None, None
    if len(core) == 1:
        album = _clean(core[0])
        return None, (album or None)

    artist = _clean(core[0])
    # Rejoin any remaining tokens: an album name may legitimately contain "-".
    album = _clean(" - ".join(core[1:]))
    return (artist or None), (album or None)


def parse_title_from_filename(
    filename: str, artist_hint: Optional[str] = None
) -> Optional[str]:
    """Derive a track-title hint from a filename like ``01-artist-title.flac``.

    Drops the extension and a leading track-number prefix, turns ``_`` into
    spaces, and — when ``artist_hint`` is given and the name starts with it —
    strips the redundant leading artist. Returns ``None`` when nothing usable
    remains.
    """
    if not filename:
        return None

    stem = os.path.splitext(os.path.basename(filename))[0]
    # Drop a leading track number ("01-", "1.", "03 "): 1-3 digits directly
    # followed by a separator, mirroring parse_track_number_from_filename so a
    # year-prefixed name ("2020 - song") is not mistaken for a track number.
    stem = re.sub(r"^\d{1,3}[\s._-]+", "", stem)
    # Scene filenames use "_" as a word separator.
    stem = stem.replace("_", " ")
    stem = re.sub(r"\s+", " ", stem).strip(" -.")

    if artist_hint:
        words = [re.escape(w) for w in artist_hint.split() if w]
        if words:
            prefix = re.compile(
                r"^" + r"[\s_-]+".join(words) + r"\s*[-:_.]+\s*",
                re.IGNORECASE,
            )
            stripped = prefix.sub("", stem, count=1)
            # Only accept the strip if a real title survives it.
            if stripped.strip(" -.:_"):
                stem = stripped

    stem = stem.strip(" -.:_")
    return stem or None
