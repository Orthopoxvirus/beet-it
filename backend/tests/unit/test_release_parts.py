"""Unit tests for multi-part release detection (issue #190).

A multi-part audiobook release ("Komplettlesung") must import as one album per
part — either split on the leading ``NN - <part name> - `` filename prefix or
on part subfolders — while normal music albums, multi-disc rips and ambiguous
layouts stay a single album. Album-title disambiguation guards against parts
re-collapsing (and duplicating rows) when tags don't distinguish them.
"""

from app.services.release_parts import (
    ReleasePart,
    disambiguate_part_albums,
    split_release_parts,
)

ROOT = "/import/audiobook/J. R. R. Tolkien - Der Herr der Ringe - Die Komplettlesung"


def _flat(names):
    return [f"{ROOT}/{n}" for n in names]


def test_flat_prefix_release_splits_into_parts():
    """The Tolkien repro: flat files with a ``NN - <part> - `` prefix."""
    files = _flat(
        [
            "01 -  Die Gefährten - 00001 - Kapitel 1.mp3",
            "01 -  Die Gefährten - 00002 - Kapitel 2.mp3",
            "01 -  Die Gefährten - 00003 - Kapitel 3.mp3",
            "02 - Die Zwei Türme - 30000 - Kapitel 1.mp3",
            "02 - Die Zwei Türme - 30001 - Kapitel 2.mp3",
            "03 - Die Wiederkehr des Königs - 60905 - Kapitel 1.mp3",
            "03 - Die Wiederkehr des Königs - 60906 - Kapitel 2.mp3",
        ]
    )

    parts = split_release_parts(files, ROOT)

    assert [p.name for p in parts] == [
        "01 - Die Gefährten",
        "02 - Die Zwei Türme",
        "03 - Die Wiederkehr des Königs",
    ]
    assert [len(p.files) for p in parts] == [3, 2, 2]
    assert all(p.root == ROOT for p in parts)
    # Every source file lands in exactly one part.
    assert sorted(f for p in parts for f in p.files) == sorted(files)


def test_music_album_track_listing_stays_single():
    """``NN - Title`` tracks form groups of one — never split."""
    files = _flat(
        [
            "01 - Ouvertüre.mp3",
            "02 - Größenwahn.mp3",
            "03 - Straßenlied.mp3",
        ]
    )

    parts = split_release_parts(files, ROOT)

    assert len(parts) == 1
    assert parts[0].name is None
    assert parts[0].files == files


def test_track_artist_title_naming_stays_single():
    """``NN - Artist - Title`` compilations group per track, not per part."""
    files = _flat(
        [
            "01 - Mätzler Bräu - Anfang.mp3",
            "02 - Mätzler Bräu - Mitte.mp3",
            "03 - Mätzler Bräu - Ende.mp3",
        ]
    )

    assert len(split_release_parts(files, ROOT)) == 1


def test_numeric_part_name_stays_single():
    """``NN - NN - Title`` is disc/track numbering, not a part title."""
    files = _flat(
        [
            "1 - 01 - Teil 1.mp3",
            "1 - 02 - Teil 2.mp3",
            "2 - 01 - Teil 1.mp3",
            "2 - 02 - Teil 2.mp3",
        ]
    )

    assert len(split_release_parts(files, ROOT)) == 1


def test_subfolder_release_splits_per_folder():
    files = [
        f"{ROOT}/01 - Die Gefährten/Kapitel 1.mp3",
        f"{ROOT}/01 - Die Gefährten/Kapitel 2.mp3",
        f"{ROOT}/02 - Die Zwei Türme/Kapitel 1.mp3",
    ]

    parts = split_release_parts(files, ROOT)

    assert [p.name for p in parts] == ["01 - Die Gefährten", "02 - Die Zwei Türme"]
    assert parts[0].root == f"{ROOT}/01 - Die Gefährten"
    assert parts[1].root == f"{ROOT}/02 - Die Zwei Türme"
    assert [len(p.files) for p in parts] == [2, 1]


def test_disc_subfolders_stay_one_album():
    """``CD n`` / ``Disc n`` folders are a multi-disc album, not parts."""
    files = [
        f"{ROOT}/CD 1/01 Teil 1.mp3",
        f"{ROOT}/CD 1/02 Teil 2.mp3",
        f"{ROOT}/Disc 2/01 Teil 1.mp3",
        f"{ROOT}/Disc 2/02 Teil 2.mp3",
    ]

    assert len(split_release_parts(files, ROOT)) == 1


def test_mixed_root_and_subfolder_audio_stays_single():
    """Loose root files alongside subfolders is ambiguous — don't split."""
    files = [
        f"{ROOT}/Intro.mp3",
        f"{ROOT}/01 - Die Gefährten/Kapitel 1.mp3",
        f"{ROOT}/02 - Die Zwei Türme/Kapitel 1.mp3",
    ]

    assert len(split_release_parts(files, ROOT)) == 1


def test_partial_prefix_match_stays_single():
    """One non-matching file disqualifies the whole prefix scheme."""
    files = _flat(
        [
            "01 - Die Gefährten - Kapitel 1.mp3",
            "01 - Die Gefährten - Kapitel 2.mp3",
            "02 - Die Zwei Türme - Kapitel 1.mp3",
            "02 - Die Zwei Türme - Kapitel 2.mp3",
            "Bonus Interview.mp3",
        ]
    )

    assert len(split_release_parts(files, ROOT)) == 1


def test_duplicate_part_numbers_stay_single():
    """Two different part names on the same number is not a part scheme."""
    files = _flat(
        [
            "01 - Die Gefährten - a.mp3",
            "01 - Die Gefährten - b.mp3",
            "01 - Die Zwei Türme - a.mp3",
            "01 - Die Zwei Türme - b.mp3",
        ]
    )

    assert len(split_release_parts(files, ROOT)) == 1


def test_disc_numbered_flat_naming_stays_single():
    """``NN - <same album> - Track``: the number marks a disc, not a part."""
    files = _flat(
        [
            "01 - Größenwahn - Intro.mp3",
            "01 - Größenwahn - Outro.mp3",
            "02 - Größenwahn - Intro.mp3",
            "02 - Größenwahn - Outro.mp3",
        ]
    )

    assert len(split_release_parts(files, ROOT)) == 1


def test_disambiguate_appends_part_name_on_collision():
    """Uniform tags across parts must not collapse into one destination."""
    parts = [
        ReleasePart(name="01 - Die Gefährten", root=ROOT, files=[]),
        ReleasePart(name="02 - Die Zwei Türme", root=ROOT, files=[]),
    ]
    metas = [
        {"artist": "Jürgen Groß", "album": "Der Herr der Ringe", "year": None},
        {"artist": "Jürgen Groß", "album": "Der Herr der Ringe", "year": None},
    ]

    disambiguate_part_albums(metas, parts)

    assert metas[0]["album"] == "Der Herr der Ringe - 01 - Die Gefährten"
    assert metas[1]["album"] == "Der Herr der Ringe - 02 - Die Zwei Türme"


def test_disambiguate_keeps_distinct_tag_albums_untouched():
    """Tags that already distinguish the parts stay exactly as read."""
    parts = [
        ReleasePart(name="01 - Die Gefährten", root=ROOT, files=[]),
        ReleasePart(name="02 - Die Zwei Türme", root=ROOT, files=[]),
    ]
    metas = [
        {"artist": "Jürgen Groß", "album": "Der Herr der Ringe 01 - Die Gefährten"},
        {"artist": "Jürgen Groß", "album": "Der Herr der Ringe 02 - Die Zwei Türme"},
    ]

    disambiguate_part_albums(metas, parts)

    assert metas[0]["album"] == "Der Herr der Ringe 01 - Die Gefährten"
    assert metas[1]["album"] == "Der Herr der Ringe 02 - Die Zwei Türme"


def test_disambiguate_without_part_name_uses_teil_index():
    parts = [ReleasePart(name=None, root=ROOT, files=[])] * 2
    metas = [
        {"artist": "Jürgen Groß", "album": "Hörbuch"},
        {"artist": "Jürgen Groß", "album": "Hörbuch"},
    ]

    disambiguate_part_albums(metas, parts)

    assert metas[0]["album"] == "Hörbuch - Teil 1"
    assert metas[1]["album"] == "Hörbuch - Teil 2"


def test_same_album_different_artist_not_disambiguated():
    """Different artists already yield different destination folders."""
    parts = [
        ReleasePart(name="01 - A", root=ROOT, files=[]),
        ReleasePart(name="02 - B", root=ROOT, files=[]),
    ]
    metas = [
        {"artist": "Jürgen Groß", "album": "Lesung"},
        {"artist": "Erika Muster", "album": "Lesung"},
    ]

    disambiguate_part_albums(metas, parts)

    assert metas[0]["album"] == "Lesung"
    assert metas[1]["album"] == "Lesung"
