"""Unit tests for the ``path`` regex source helper (relative_source_path)."""

from app.services.transformations import relative_source_path


class TestRelativeSourcePath:
    """Tests for relative_source_path."""

    def test_nested_directory(self):
        """Returns the folder path relative to the root, without filename."""
        result = relative_source_path("/data/import/Artist/Album", "/data/import")
        assert result == "Artist/Album"

    def test_trailing_slash_on_root(self):
        """A trailing slash on the root is handled (matches provisioned roots)."""
        result = relative_source_path("/data/import/Artist/Album", "/data/import/")
        assert result == "Artist/Album"

    def test_single_level(self):
        """A single sub-directory yields just that directory name."""
        assert relative_source_path("/data/import/Artist", "/data/import") == "Artist"

    def test_top_level_returns_empty(self):
        """An item directly in the root has no relative folder."""
        assert relative_source_path("/data/import", "/data/import") == ""

    def test_missing_directory_returns_empty(self):
        assert relative_source_path(None, "/data/import") == ""
        assert relative_source_path("", "/data/import") == ""

    def test_missing_root_returns_empty(self):
        """No root means no absolute path is leaked into the source."""
        assert relative_source_path("/data/import/Artist/Album", None) == ""
        assert relative_source_path("/data/import/Artist/Album", "") == ""

    def test_directory_outside_root_returns_empty(self):
        """A directory that escapes the root is not relativized into '..'."""
        assert relative_source_path("/other/place", "/data/import") == ""
