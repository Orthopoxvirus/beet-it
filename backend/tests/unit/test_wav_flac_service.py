"""Unit tests for the WAV→FLAC convert / duplicate-WAV cleanup service."""

import os
import shutil
import stat
import subprocess

import pytest

from app.services import wav_flac_service as svc


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _touch(path, content=b"data"):
    with open(path, "wb") as fh:
        fh.write(content)


def _fake_ffmpeg(src, dst):
    """Stand-in for ffmpeg: writes a small non-empty file at dst."""
    _touch(dst, b"fLaC-fake-output")


def _noop_ffmpeg(src, dst):
    """ffmpeg that 'succeeds' but produces nothing — exercises verify-before-delete."""
    return None


# ---------------------------------------------------------------------------
# summarize_wav_flac
# ---------------------------------------------------------------------------

def test_summarize_flags_and_duplicate_count(tmp_path):
    _touch(tmp_path / "01.wav")          # lone wav
    _touch(tmp_path / "02.wav")          # has flac twin -> duplicate
    _touch(tmp_path / "02.flac")
    _touch(tmp_path / "03.flac")         # lone flac

    summary = svc.summarize_wav_flac(str(tmp_path))

    assert summary.has_wav is True
    assert summary.has_flac is True
    assert summary.duplicate_wav_count == 1


def test_summarize_case_insensitive_sibling(tmp_path):
    _touch(tmp_path / "Track.WAV")
    _touch(tmp_path / "track.flac")

    summary = svc.summarize_wav_flac(str(tmp_path))

    assert summary.duplicate_wav_count == 1


def test_summarize_multidisc_per_directory_scoping(tmp_path):
    # CD1 wav has its flac twin in the SAME folder -> duplicate.
    cd1 = tmp_path / "CD1"
    cd2 = tmp_path / "CD2"
    cd1.mkdir()
    cd2.mkdir()
    _touch(cd1 / "01.wav")
    _touch(cd1 / "01.flac")
    # CD2 wav's only flac lives in CD1 -> NOT a duplicate (different directory).
    _touch(cd2 / "01.wav")

    summary = svc.summarize_wav_flac(str(tmp_path))

    assert summary.has_wav is True
    assert summary.has_flac is True
    assert summary.duplicate_wav_count == 1  # only the CD1 pair


def test_summarize_missing_folder_is_empty(tmp_path):
    summary = svc.summarize_wav_flac(str(tmp_path / "nope"))
    assert summary.has_wav is False
    assert summary.has_flac is False
    assert summary.duplicate_wav_count == 0


def test_summarize_only_flac_hides_convert_and_dedupe(tmp_path):
    _touch(tmp_path / "01.flac")
    _touch(tmp_path / "02.flac")
    summary = svc.summarize_wav_flac(str(tmp_path))
    assert summary.has_wav is False
    assert summary.has_flac is True
    assert summary.duplicate_wav_count == 0


# ---------------------------------------------------------------------------
# find helpers
# ---------------------------------------------------------------------------

def test_find_duplicate_wavs_only_twinned(tmp_path):
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "a.flac")
    _touch(tmp_path / "b.wav")  # lone

    dups = svc.find_duplicate_wavs(str(tmp_path))

    assert dups == [str(tmp_path / "a.wav")]


# ---------------------------------------------------------------------------
# convert_album_wavs
# ---------------------------------------------------------------------------

def test_convert_keeps_originals_by_default(tmp_path):
    _touch(tmp_path / "01.wav")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=False, ffmpeg_runner=_fake_ffmpeg
    )

    assert result.converted == 1
    assert result.deleted == 0
    assert os.path.exists(tmp_path / "01.wav")
    assert os.path.exists(tmp_path / "01.flac")


def test_convert_deletes_originals_when_requested(tmp_path):
    _touch(tmp_path / "01.wav")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=True, ffmpeg_runner=_fake_ffmpeg
    )

    assert result.converted == 1
    assert result.deleted == 1
    assert not os.path.exists(tmp_path / "01.wav")
    assert os.path.exists(tmp_path / "01.flac")


def test_convert_skips_existing_flac(tmp_path):
    _touch(tmp_path / "01.wav")
    _touch(tmp_path / "01.flac", b"original-flac")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=True, ffmpeg_runner=_fake_ffmpeg
    )

    assert result.converted == 0
    assert result.skipped == 1
    # Existing FLAC untouched and WAV preserved (skip never deletes).
    assert open(tmp_path / "01.flac", "rb").read() == b"original-flac"
    assert os.path.exists(tmp_path / "01.wav")


def test_convert_verify_before_delete_keeps_wav_on_empty_output(tmp_path):
    _touch(tmp_path / "01.wav")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=True, ffmpeg_runner=_noop_ffmpeg
    )

    assert result.converted == 0
    assert result.failed == 1
    # No FLAC written, original WAV must survive.
    assert os.path.exists(tmp_path / "01.wav")
    assert not os.path.exists(tmp_path / "01.flac")


def test_convert_failure_leaves_no_partial_flac(tmp_path):
    _touch(tmp_path / "01.wav")

    def boom(src, dst):
        raise RuntimeError("ffmpeg exploded")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=False, ffmpeg_runner=boom
    )

    assert result.failed == 1
    assert result.failures and result.failures[0]["file"].endswith("01.wav")
    assert not os.path.exists(tmp_path / "01.flac")
    # No stray temp files left behind.
    assert sorted(os.listdir(tmp_path)) == ["01.wav"]


def test_convert_multidisc(tmp_path):
    cd1 = tmp_path / "CD1"
    cd2 = tmp_path / "CD2"
    cd1.mkdir()
    cd2.mkdir()
    _touch(cd1 / "01.wav")
    _touch(cd2 / "01.wav")

    result = svc.convert_album_wavs(
        str(tmp_path), delete_originals=False, ffmpeg_runner=_fake_ffmpeg
    )

    assert result.converted == 2
    assert os.path.exists(cd1 / "01.flac")
    assert os.path.exists(cd2 / "01.flac")


def test_convert_applies_file_permission(tmp_path):
    _touch(tmp_path / "01.wav")

    svc.convert_album_wavs(
        str(tmp_path),
        delete_originals=False,
        file_perm=664,
        ffmpeg_runner=_fake_ffmpeg,
    )

    mode = stat.S_IMODE(os.stat(tmp_path / "01.flac").st_mode)
    assert mode == 0o664


def test_perm_to_mode_handles_garbage():
    assert svc._perm_to_mode(664) == 0o664
    assert svc._perm_to_mode(None) is None
    assert svc._perm_to_mode("not-a-number") is None


# ---------------------------------------------------------------------------
# remove_duplicate_wavs
# ---------------------------------------------------------------------------

def test_remove_duplicate_wavs_only_twinned(tmp_path):
    _touch(tmp_path / "a.wav")
    _touch(tmp_path / "a.flac")
    _touch(tmp_path / "b.wav")  # lone — must survive

    result = svc.remove_duplicate_wavs(str(tmp_path))

    assert result.removed == 1
    assert not os.path.exists(tmp_path / "a.wav")
    assert os.path.exists(tmp_path / "a.flac")  # FLAC never touched
    assert os.path.exists(tmp_path / "b.wav")   # lone WAV never touched


def test_remove_duplicate_wavs_multidisc_scoping(tmp_path):
    cd1 = tmp_path / "CD1"
    cd2 = tmp_path / "CD2"
    cd1.mkdir()
    cd2.mkdir()
    _touch(cd1 / "01.wav")
    _touch(cd1 / "01.flac")  # twin in same dir -> removed
    _touch(cd2 / "01.wav")   # flac twin only in CD1 -> kept

    result = svc.remove_duplicate_wavs(str(tmp_path))

    assert result.removed == 1
    assert not os.path.exists(cd1 / "01.wav")
    assert os.path.exists(cd2 / "01.wav")


# ---------------------------------------------------------------------------
# Real ffmpeg end-to-end (skipped where ffmpeg is unavailable)
# ---------------------------------------------------------------------------

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not installed")
def test_convert_real_ffmpeg_produces_valid_flac(tmp_path):
    wav = tmp_path / "tone.wav"
    subprocess.run(
        ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
         "-f", "lavfi", "-i", "sine=frequency=440:duration=1", str(wav)],
        check=True,
    )

    result = svc.convert_album_wavs(str(tmp_path), delete_originals=True)

    assert result.converted == 1
    assert result.deleted == 1
    flac = tmp_path / "tone.flac"
    assert flac.exists()
    with open(flac, "rb") as fh:
        assert fh.read(4) == b"fLaC"  # FLAC stream marker
    assert not wav.exists()


# ---------------------------------------------------------------------------
# Generalised convert_album_audio (WAV/WMA → FLAC/MP3) + WMA recommendation
# ---------------------------------------------------------------------------

def test_find_audio_files_by_ext(tmp_path):
    _touch(tmp_path / "a.wma")
    _touch(tmp_path / "b.WMA")  # case-insensitive
    _touch(tmp_path / "c.wav")
    found = svc.find_audio_files(str(tmp_path), ".wma")
    assert {os.path.basename(p) for p in found} == {"a.wma", "b.WMA"}


def test_convert_wma_to_mp3_keeps_originals(tmp_path):
    _touch(tmp_path / "01.wma")
    result = svc.convert_album_audio(
        str(tmp_path),
        source_ext=".wma",
        target_format="mp3",
        delete_originals=False,
        ffmpeg_runner=_fake_ffmpeg,
    )
    assert result.converted == 1
    assert result.deleted == 0
    assert os.path.exists(tmp_path / "01.mp3")
    assert os.path.exists(tmp_path / "01.wma")  # original kept


def test_convert_wma_to_flac_deletes_originals(tmp_path):
    _touch(tmp_path / "01.wma")
    result = svc.convert_album_audio(
        str(tmp_path),
        source_ext=".wma",
        target_format="flac",
        delete_originals=True,
        ffmpeg_runner=_fake_ffmpeg,
    )
    assert result.converted == 1
    assert result.deleted == 1
    assert os.path.exists(tmp_path / "01.flac")
    assert not os.path.exists(tmp_path / "01.wma")


def test_convert_audio_skips_existing_target(tmp_path):
    _touch(tmp_path / "01.wma")
    _touch(tmp_path / "01.mp3", b"original-mp3")
    result = svc.convert_album_audio(
        str(tmp_path),
        source_ext=".wma",
        target_format="mp3",
        delete_originals=True,
        ffmpeg_runner=_fake_ffmpeg,
    )
    assert result.converted == 0
    assert result.skipped == 1
    assert open(tmp_path / "01.mp3", "rb").read() == b"original-mp3"
    assert os.path.exists(tmp_path / "01.wma")  # not deleted when skipped


def test_convert_audio_rejects_unknown_target(tmp_path):
    _touch(tmp_path / "01.wma")
    with pytest.raises(ValueError):
        svc.convert_album_audio(
            str(tmp_path),
            source_ext=".wma",
            target_format="ogg",
            delete_originals=False,
            ffmpeg_runner=_fake_ffmpeg,
        )


def test_run_ffmpeg_builds_target_specific_args(monkeypatch):
    captured = {}

    class _Proc:
        returncode = 0
        stderr = ""

    def _fake_run(cmd, **kwargs):
        captured["cmd"] = cmd
        return _Proc()

    monkeypatch.setattr(svc.subprocess, "run", _fake_run)

    svc._run_ffmpeg("in.wma", "out.mp3", "mp3")
    assert "libmp3lame" in captured["cmd"]
    assert captured["cmd"][-1] == "out.mp3"

    svc._run_ffmpeg("in.wav", "out.flac", "flac")
    assert "flac" in captured["cmd"]
    assert captured["cmd"][-1] == "out.flac"

    with pytest.raises(ValueError):
        svc._run_ffmpeg("in.wma", "out.xyz", "xyz")


@pytest.mark.parametrize(
    "bitrates,expected",
    [
        ([128.0], "mp3"),       # standard lossy WMA
        ([320.0], "mp3"),       # exactly at the threshold -> still mp3
        ([700.0], "flac"),      # WMA Pro / high bitrate -> preserve as flac
        ([None], "mp3"),        # unreadable bitrate -> lossy default
        ([200.0, 500.0], "flac"),  # max wins
    ],
)
def test_recommend_wma_target(monkeypatch, bitrates, expected):
    seq = iter(bitrates)
    monkeypatch.setattr(svc, "_read_bitrate_kbps", lambda _p: next(seq))
    paths = [f"f{i}.wma" for i in range(len(bitrates))]
    assert svc.recommend_wma_target(paths) == expected


def test_summarize_detects_wma_and_recommends(monkeypatch, tmp_path):
    _touch(tmp_path / "01.wma")
    _touch(tmp_path / "02.flac")
    monkeypatch.setattr(svc, "_read_bitrate_kbps", lambda _p: 256.0)
    summary = svc.summarize_wav_flac(str(tmp_path))
    assert summary.has_wma is True
    assert summary.has_flac is True
    assert summary.has_wav is False
    assert summary.wma_recommended_target == "mp3"


def test_summarize_no_wma_leaves_recommendation_none(tmp_path):
    _touch(tmp_path / "01.wav")
    summary = svc.summarize_wav_flac(str(tmp_path))
    assert summary.has_wma is False
    assert summary.wma_recommended_target is None
