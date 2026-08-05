"""WAV→FLAC conversion and duplicate-WAV cleanup for pre-import album folders.

These operations run on the raw files in a library's import folder *before*
beets takes ownership of them. They are intentionally conservative:

- Conversion never overwrites an existing ``.flac`` (that file is handled by the
  dedup path instead) and, when asked to delete originals, only removes a
  ``.wav`` after its ``.flac`` has been verified to exist and be non-empty.
- Dedup only ever deletes a ``.wav`` that has a same-basename ``.flac`` sibling
  in the *same* directory — never the sole copy of a track.

Sibling matching is by basename without extension, case-insensitive, scoped to
one directory. The walk is recursive so multi-disc albums (CD1/CD2 subfolders)
are handled correctly.
"""

import logging
import os
import subprocess
import tempfile
from dataclasses import dataclass, field
from typing import Callable, Dict, List, Optional

logger = logging.getLogger(__name__)

# Lossless FLAC, max compression. Argument array — never shell=True.
FFMPEG_COMPRESSION_LEVEL = "8"
# Per-file conversion timeout. A single track should never take this long;
# the cap stops a wedged ffmpeg from holding the worker forever.
FFMPEG_TIMEOUT_SECONDS = 300

# Encoder settings per conversion target.
#   flac — lossless, max compression. The right target for a lossless source
#          (WAV always; high-bitrate / lossless WMA).
#   mp3  — LAME V0 (~245 kbps VBR), the high-quality lossy target. Sensible for
#          an already-lossy source (standard WMA), where wrapping it in FLAC
#          would only bloat the file without recovering quality.
TARGET_SPECS: Dict[str, Dict[str, object]] = {
    "flac": {
        "ext": ".flac",
        "args": ["-c:a", "flac", "-compression_level", FFMPEG_COMPRESSION_LEVEL],
    },
    "mp3": {
        "ext": ".mp3",
        "args": ["-c:a", "libmp3lame", "-q:a", "0"],  # V0
    },
}

# Source containers we know how to read + convert.
SOURCE_EXTS: Dict[str, str] = {"wav": ".wav", "wma": ".wma"}

# Above this WMA bitrate we recommend FLAC (preserve a high-bitrate or lossless
# source); at or below it MP3 V0 is the smart default — re-wrapping an already
# ~320 kbps lossy stream into FLAC just wastes space.
WMA_FLAC_BITRATE_THRESHOLD_KBPS = 320


@dataclass
class WavFlacSummary:
    """Per-album WAV/FLAC breakdown that drives the card's action buttons."""

    has_wav: bool = False
    has_flac: bool = False
    # Number of .wav files that have a same-basename .flac sibling in the same
    # directory — i.e. real duplicates that dedup would remove.
    duplicate_wav_count: int = 0
    # Whether the folder contains any .wma files (drives the WMA convert action).
    has_wma: bool = False
    # Smart-default convert target for this album's WMA files — "mp3" or "flac",
    # picked from the highest WMA bitrate found. None when there is no WMA.
    wma_recommended_target: Optional[str] = None


@dataclass
class ConvertResult:
    """Outcome of a WAV→FLAC conversion run over an album folder."""

    converted: int = 0
    skipped: int = 0  # target .flac already existed
    failed: int = 0
    deleted: int = 0  # originals removed (only when delete_originals=True)
    failures: List[Dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "converted": self.converted,
            "skipped": self.skipped,
            "failed": self.failed,
            "deleted": self.deleted,
            "failures": self.failures,
        }


@dataclass
class DedupResult:
    """Outcome of a duplicate-WAV removal run over an album folder."""

    removed: int = 0
    failed: int = 0
    failures: List[Dict[str, str]] = field(default_factory=list)

    def as_dict(self) -> Dict[str, object]:
        return {
            "removed": self.removed,
            "failed": self.failed,
            "failures": self.failures,
        }


def _is_wav(name: str) -> bool:
    return name.lower().endswith(".wav")


def _is_flac(name: str) -> bool:
    return name.lower().endswith(".flac")


def _is_wma(name: str) -> bool:
    return name.lower().endswith(".wma")


def _stem_lower(name: str) -> str:
    return os.path.splitext(name)[0].lower()


def _flac_siblings_in(filenames: List[str]) -> set:
    """Lowercased basenames (without extension) of the .flac files in a dir."""
    return {_stem_lower(n) for n in filenames if _is_flac(n)}


def _iter_dirs(album_path: str):
    """Yield (dirpath, filenames) for every directory under album_path.

    Recursive so multi-disc albums (CD1/CD2) are covered. Each directory is
    considered independently for sibling matching, matching how the files would
    actually live on disk.
    """
    for dirpath, _dirnames, filenames in os.walk(album_path):
        yield dirpath, filenames


def summarize_wav_flac(album_path: str) -> WavFlacSummary:
    """Compute the per-album WAV/FLAC summary used for button visibility.

    Never raises for a missing/unreadable folder — returns an all-empty summary
    so the UI simply hides the actions rather than erroring.
    """
    summary = WavFlacSummary()
    if not album_path or not os.path.isdir(album_path):
        return summary

    wma_paths: List[str] = []
    try:
        for dirpath, filenames in _iter_dirs(album_path):
            flac_stems = _flac_siblings_in(filenames)
            for name in filenames:
                if _is_wav(name):
                    summary.has_wav = True
                    if _stem_lower(name) in flac_stems:
                        summary.duplicate_wav_count += 1
                elif _is_flac(name):
                    summary.has_flac = True
                elif _is_wma(name):
                    summary.has_wma = True
                    wma_paths.append(os.path.join(dirpath, name))
    except OSError as exc:  # pragma: no cover - defensive
        logger.warning("Failed to summarize WAV/FLAC for %s: %s", album_path, exc)
        return WavFlacSummary()

    if summary.has_wma:
        summary.wma_recommended_target = recommend_wma_target(wma_paths)

    return summary


def _read_bitrate_kbps(path: str) -> Optional[float]:
    """Best-effort audio bitrate in kbps via mutagen. None if unreadable.

    Used only to pick a smart default convert target; a missing value just
    falls back to the lossy default, so failures here are non-fatal.
    """
    try:
        from mutagen import File as MutagenFile

        mf = MutagenFile(path)
        info = getattr(mf, "info", None)
        bitrate = getattr(info, "bitrate", None) if info is not None else None
        if bitrate:
            return bitrate / 1000.0
    except Exception as exc:  # noqa: BLE001 - bitrate is advisory only
        logger.debug("Could not read bitrate for %s: %s", path, exc)
    return None


def recommend_wma_target(wma_paths: List[str]) -> str:
    """Pick the smart-default convert target for a set of WMA files.

    FLAC when the highest WMA bitrate exceeds
    :data:`WMA_FLAC_BITRATE_THRESHOLD_KBPS` (a high-bitrate or lossless source
    worth preserving); MP3 V0 otherwise — including when no bitrate can be read,
    since standard WMA is lossy and FLAC would only bloat it.
    """
    max_kbps = 0.0
    for path in wma_paths:
        kbps = _read_bitrate_kbps(path)
        if kbps and kbps > max_kbps:
            max_kbps = kbps
    return "flac" if max_kbps > WMA_FLAC_BITRATE_THRESHOLD_KBPS else "mp3"


def find_duplicate_wavs(album_path: str) -> List[str]:
    """Absolute paths of .wav files that have a same-basename .flac sibling."""
    duplicates: List[str] = []
    for dirpath, filenames in _iter_dirs(album_path):
        flac_stems = _flac_siblings_in(filenames)
        for name in filenames:
            if _is_wav(name) and _stem_lower(name) in flac_stems:
                duplicates.append(os.path.join(dirpath, name))
    return duplicates


def find_audio_files(album_path: str, ext: str) -> List[str]:
    """Absolute paths of every file with the given extension (e.g. ``.wma``)."""
    ext = ext.lower()
    matches: List[str] = []
    for dirpath, filenames in _iter_dirs(album_path):
        for name in filenames:
            if name.lower().endswith(ext):
                matches.append(os.path.join(dirpath, name))
    return matches


def find_wavs(album_path: str) -> List[str]:
    """Absolute paths of every .wav file under the album folder."""
    return find_audio_files(album_path, ".wav")


def _perm_to_mode(file_perm: Optional[int]) -> Optional[int]:
    """Convert the stored permission integer (e.g. 664) into a chmod mode.

    beet-it stores permissions the way the beets ``permissions`` plugin writes
    them — the decimal digits are the octal mode (664 -> 0o664). Returns None if
    the value can't be interpreted, so callers leave the umask default in place.
    """
    if file_perm is None:
        return None
    try:
        return int(str(int(file_perm)), 8)
    except (ValueError, TypeError):
        logger.warning("Ignoring un-parseable file permission: %r", file_perm)
        return None


def _apply_permission(path: str, file_perm: Optional[int]) -> None:
    mode = _perm_to_mode(file_perm)
    if mode is None:
        return
    try:
        os.chmod(path, mode)
    except OSError as exc:  # pragma: no cover - best effort
        logger.warning("Could not chmod %s to %o: %s", path, mode, exc)


def _run_ffmpeg(src_path: str, dst_path: str, target_format: str = "flac") -> None:
    """Transcode one file to ``target_format``. Raises on failure.

    ffmpeg auto-detects the input container, so the same call handles WAV and
    WMA sources. Isolated as a module function so tests can stub it without a
    real ffmpeg.
    """
    spec = TARGET_SPECS.get(target_format)
    if spec is None:
        raise ValueError(f"Unsupported conversion target: {target_format!r}")
    cmd = [
        "ffmpeg",
        "-hide_banner",
        "-loglevel",
        "error",
        "-y",
        "-i",
        src_path,
        *spec["args"],
        dst_path,
    ]
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=FFMPEG_TIMEOUT_SECONDS,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"ffmpeg exited {proc.returncode}: {proc.stderr.strip() or 'no stderr'}"
        )


def transcode_file(
    src_path: str,
    target_path: str,
    *,
    target_format: str = "flac",
    file_perm: Optional[int] = None,
    ffmpeg_runner: Optional[Callable[[str, str], None]] = None,
) -> None:
    """Transcode one file to ``target_path``, atomically. Raises on failure.

    Writes to a temp file in the target's directory, verifies the output is
    non-empty, then renames into place — a failed/partial transcode never
    leaves a bogus output behind. Applies ``file_perm`` to the written file.
    """
    if ffmpeg_runner is None:
        def ffmpeg_runner(src: str, dst: str, _fmt: str = target_format) -> None:
            _run_ffmpeg(src, dst, _fmt)

    directory = os.path.dirname(target_path)
    stem, target_ext = os.path.splitext(os.path.basename(target_path))
    tmp_fd, tmp_path = tempfile.mkstemp(
        prefix=f".{stem}.", suffix=target_ext, dir=directory
    )
    os.close(tmp_fd)
    os.unlink(tmp_path)  # ffmpeg writes it fresh; mkstemp just reserves a name
    try:
        ffmpeg_runner(src_path, tmp_path)
        if not os.path.isfile(tmp_path) or os.path.getsize(tmp_path) == 0:
            raise RuntimeError("ffmpeg produced no output")
        os.replace(tmp_path, target_path)
    except Exception:
        if os.path.exists(tmp_path):
            try:
                os.unlink(tmp_path)
            except OSError:  # pragma: no cover - best effort cleanup
                pass
        raise
    _apply_permission(target_path, file_perm)


def convert_album_audio(
    album_path: str,
    *,
    source_ext: str,
    target_format: str,
    delete_originals: bool,
    file_perm: Optional[int] = None,
    ffmpeg_runner: Optional[Callable[[str, str], None]] = None,
) -> ConvertResult:
    """Convert every ``source_ext`` file in the album folder to ``target_format``.

    - Skips (does not overwrite) a source file whose target sibling already
      exists.
    - Writes to a temp file in the same directory, then atomically renames, so a
      failed/partial transcode never leaves a bogus output behind.
    - Applies ``file_perm`` to each written file so it matches beets-managed
      files.
    - When ``delete_originals`` is True, removes a source file only after its
      target is verified to exist and be non-empty.
    """
    spec = TARGET_SPECS.get(target_format)
    if spec is None:
        raise ValueError(f"Unsupported conversion target: {target_format!r}")
    target_ext = spec["ext"]

    result = ConvertResult()
    if not os.path.isdir(album_path):
        raise FileNotFoundError(f"Album folder not found: {album_path}")

    for src_path in find_audio_files(album_path, source_ext):
        directory = os.path.dirname(src_path)
        stem = os.path.splitext(os.path.basename(src_path))[0]
        target_path = os.path.join(directory, f"{stem}{target_ext}")

        # Don't overwrite an existing target of the same name.
        if os.path.exists(target_path):
            result.skipped += 1
            continue

        try:
            transcode_file(
                src_path,
                target_path,
                target_format=target_format,
                file_perm=file_perm,
                ffmpeg_runner=ffmpeg_runner,
            )
            result.converted += 1
        except Exception as exc:  # noqa: BLE001 - report per-file, keep going
            result.failed += 1
            result.failures.append({"file": src_path, "error": str(exc)})
            logger.warning("Audio conversion failed for %s: %s", src_path, exc)
            continue

        # Verify-before-delete: only remove the source once the target is real.
        if delete_originals:
            try:
                if os.path.isfile(target_path) and os.path.getsize(target_path) > 0:
                    os.remove(src_path)
                    result.deleted += 1
            except OSError as exc:  # pragma: no cover - best effort
                logger.warning("Could not delete original %s: %s", src_path, exc)

    return result


def convert_album_wavs(
    album_path: str,
    delete_originals: bool,
    file_perm: Optional[int] = None,
    ffmpeg_runner: Callable[[str, str], None] = _run_ffmpeg,
) -> ConvertResult:
    """Convert every .wav in the album folder to a sibling .flac.

    Thin back-compat wrapper over :func:`convert_album_audio` (WAV→FLAC).
    """
    return convert_album_audio(
        album_path,
        source_ext=".wav",
        target_format="flac",
        delete_originals=delete_originals,
        file_perm=file_perm,
        ffmpeg_runner=ffmpeg_runner,
    )


def remove_duplicate_wavs(album_path: str) -> DedupResult:
    """Delete every .wav that has a same-basename .flac sibling. FLACs untouched."""
    result = DedupResult()
    if not os.path.isdir(album_path):
        raise FileNotFoundError(f"Album folder not found: {album_path}")

    for wav_path in find_duplicate_wavs(album_path):
        try:
            os.remove(wav_path)
            result.removed += 1
        except OSError as exc:
            result.failed += 1
            result.failures.append({"file": wav_path, "error": str(exc)})
            logger.warning("Could not remove duplicate WAV %s: %s", wav_path, exc)

    return result
