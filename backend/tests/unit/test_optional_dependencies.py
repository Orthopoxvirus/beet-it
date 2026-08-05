"""Regression guards for runtime dependencies that aren't pulled in transitively.

These libs are imported lazily deep in request handlers, so a missing
declaration only surfaces when a user hits the feature in the built image.
A cheap import check here fails fast in CI instead.
"""


def test_musicbrainzngs_importable():
    """MusicBrainz link resolver (app/api/routes/beets_autotag.py) needs this.

    beets 2.x dropped musicbrainzngs as a dependency (it ships its own MB
    client), so it must stay declared in requirements.txt / pyproject.toml.
    Regression guard for issue #36.
    """
    import musicbrainzngs

    # The resolver only calls set_useragent + get_release_by_id; make sure the
    # entry point it relies on is actually present in the installed version.
    assert hasattr(musicbrainzngs, "set_useragent")
    assert hasattr(musicbrainzngs, "get_release_by_id")
