"""Unit tests for import tree service."""

import os
import tempfile
from pathlib import Path

import pytest

from app.services.import_tree import (
    detect_multi_disc,
    ImportTreeService,
    MULTI_DISC_PATTERN,
)


def _add_track(folder: str, name: str = "01 - Track.mp3") -> None:
    """Drop a dummy audio file into a folder so it counts as a real album.

    The import tree only treats a leaf folder as an album when it directly
    holds audio; an audio-less folder is suppressed as an empty husk. Tests
    that assert ``is_album`` on a leaf must therefore give it a track.
    """
    Path(os.path.join(folder, name)).touch()


class TestMultiDiscDetection:
    """Tests for multi-disc detection function."""

    def test_detect_basic_disc_pattern(self):
        """Test detection of 'Album Disc 1', 'Album Disc 2' pattern."""
        folder_names = ["Album Disc 1", "Album Disc 2"]
        result = detect_multi_disc(folder_names)

        assert "Album" in result
        assert len(result["Album"]) == 2
        assert "Album Disc 1" in result["Album"]
        assert "Album Disc 2" in result["Album"]

    def test_detect_cd_pattern(self):
        """Test detection of 'Album CD1', 'Album CD2' pattern."""
        folder_names = ["Album CD1", "Album CD2", "Album CD3"]
        result = detect_multi_disc(folder_names)

        assert "Album" in result
        assert len(result["Album"]) == 3

    def test_detect_case_insensitive(self):
        """Test that detection is case-insensitive."""
        folder_names = ["Album DISC 1", "Album disc 2", "Album Disc 3"]
        result = detect_multi_disc(folder_names)

        assert "Album" in result
        assert len(result["Album"]) == 3

    def test_detect_with_spacing_variations(self):
        """Test detection with various spacing patterns."""
        # Space before disc number
        folder_names = ["Album disc 1", "Album disc 2"]
        result = detect_multi_disc(folder_names)
        assert "Album" in result

        # No space before disc number
        folder_names2 = ["Album disc1", "Album disc2"]
        result2 = detect_multi_disc(folder_names2)
        assert "Album" in result2

    def test_single_disc_not_detected(self):
        """Test that single disc folders are not returned."""
        folder_names = ["Album Disc 1"]
        result = detect_multi_disc(folder_names)

        assert result == {}

    def test_mixed_folders(self):
        """Test with a mix of disc folders and regular folders."""
        folder_names = [
            "Album A Disc 1",
            "Album A Disc 2",
            "Regular Album",
            "Another Regular Album",
        ]
        result = detect_multi_disc(folder_names)

        assert "Album A" in result
        assert len(result["Album A"]) == 2
        assert "Regular Album" not in result

    def test_multiple_multi_disc_albums(self):
        """Test detection of multiple multi-disc albums."""
        folder_names = [
            "Album A Disc 1",
            "Album A Disc 2",
            "Album B CD 1",
            "Album B CD 2",
            "Album B CD 3",
        ]
        result = detect_multi_disc(folder_names)

        assert "Album A" in result
        assert "Album B" in result
        assert len(result["Album A"]) == 2
        assert len(result["Album B"]) == 3

    def test_similar_prefixes_kept_separate(self):
        """Test that albums with similar but different prefixes stay separate."""
        folder_names = [
            "Greatest Hits Disc 1",
            "Greatest Hits Disc 2",
            "Greatest Hits Vol 2 Disc 1",
            "Greatest Hits Vol 2 Disc 2",
        ]
        result = detect_multi_disc(folder_names)

        assert "Greatest Hits" in result
        assert "Greatest Hits Vol 2" in result

    def test_empty_input(self):
        """Test with empty input."""
        result = detect_multi_disc([])
        assert result == {}

    def test_no_disc_folders(self):
        """Test with folders that don't match disc pattern."""
        folder_names = ["Album 1", "Album 2", "My Music"]
        result = detect_multi_disc(folder_names)
        assert result == {}


class TestMultiDiscPattern:
    """Tests for the multi-disc regex pattern."""

    def test_pattern_matches_disc(self):
        """Test pattern matches 'disc' keyword."""
        match = MULTI_DISC_PATTERN.match("Album Disc 1")
        assert match is not None
        assert match.group(1) == "Album"
        assert match.group(2) == "1"

    def test_pattern_matches_cd(self):
        """Test pattern matches 'cd' keyword."""
        match = MULTI_DISC_PATTERN.match("Album CD 2")
        assert match is not None
        assert match.group(1) == "Album"
        assert match.group(2) == "2"

    def test_pattern_case_insensitive(self):
        """Test pattern is case-insensitive."""
        assert MULTI_DISC_PATTERN.match("Album DISC 1") is not None
        assert MULTI_DISC_PATTERN.match("Album disc 1") is not None
        assert MULTI_DISC_PATTERN.match("Album Disc 1") is not None

    def test_pattern_handles_no_space(self):
        """Test pattern handles no space before number."""
        match = MULTI_DISC_PATTERN.match("Album CD1")
        assert match is not None
        assert match.group(2) == "1"

    def test_pattern_handles_multi_digit(self):
        """Test pattern handles multi-digit disc numbers."""
        match = MULTI_DISC_PATTERN.match("Album Disc 10")
        assert match is not None
        assert match.group(2) == "10"


class TestImportTreeService:
    """Tests for ImportTreeService."""

    @pytest.fixture
    def import_tree_service(self):
        """Create an ImportTreeService instance."""
        return ImportTreeService()

    @pytest.fixture
    def temp_import_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_empty_import_path_nonexistent(self, import_tree_service, temp_import_dir):
        """Test behavior when import path doesn't exist."""
        nonexistent = os.path.join(temp_import_dir, "nonexistent")
        result = import_tree_service.build_import_tree(nonexistent)
        assert result == []

    def test_empty_import_folder(self, import_tree_service, temp_import_dir):
        """Test with an empty import folder."""
        result = import_tree_service.build_import_tree(temp_import_dir)
        assert result == []

    def test_simple_album_structure(self, import_tree_service, temp_import_dir):
        """Test simple artist/album structure."""
        # Create structure: Artist/Album/
        artist_dir = os.path.join(temp_import_dir, "Artist")
        album_dir = os.path.join(artist_dir, "Album")
        os.makedirs(album_dir)
        _add_track(album_dir)

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert len(result) == 1
        artist_node = result[0]
        assert artist_node.name == "Artist"
        assert artist_node.path == "Artist"
        assert artist_node.is_album is False
        assert artist_node.has_subfolders is True

        assert len(artist_node.children) == 1
        album_node = artist_node.children[0]
        assert album_node.name == "Album"
        assert album_node.path == "Artist/Album"
        assert album_node.is_album is True
        assert album_node.has_subfolders is False

    def test_multi_disc_detection(self, import_tree_service, temp_import_dir):
        """Test multi-disc album detection."""
        # Create structure: Artist/Album/Album Disc 1/, Album Disc 2/
        artist_dir = os.path.join(temp_import_dir, "Artist")
        album_dir = os.path.join(artist_dir, "Album")
        disc1_dir = os.path.join(album_dir, "Album Disc 1")
        disc2_dir = os.path.join(album_dir, "Album Disc 2")
        os.makedirs(disc1_dir)
        os.makedirs(disc2_dir)
        _add_track(disc1_dir)
        _add_track(disc2_dir)

        result = import_tree_service.build_import_tree(temp_import_dir)

        artist_node = result[0]
        album_node = artist_node.children[0]

        # Album parent should be marked as multi-disc parent and album
        assert album_node.name == "Album"
        assert album_node.is_album is True
        assert album_node.is_multi_disc_parent is True

        # Disc folders should NOT be marked as albums
        disc1_node = next(c for c in album_node.children if "Disc 1" in c.name)
        disc2_node = next(c for c in album_node.children if "Disc 2" in c.name)

        assert disc1_node.is_album is False
        assert disc2_node.is_album is False

    def test_hidden_folders_excluded(self, import_tree_service, temp_import_dir):
        """Test that hidden folders (starting with .) are excluded."""
        # Create visible and hidden folders
        visible_dir = os.path.join(temp_import_dir, "Visible")
        hidden_dir = os.path.join(temp_import_dir, ".hidden")
        os.makedirs(visible_dir)
        os.makedirs(hidden_dir)
        _add_track(visible_dir)

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert len(result) == 1
        assert result[0].name == "Visible"

    def test_alphabetical_sorting(self, import_tree_service, temp_import_dir):
        """Test that folders are sorted alphabetically."""
        # Create folders in non-alphabetical order
        for name in ("Zeppelin", "ABBA", "Beatles"):
            folder = os.path.join(temp_import_dir, name)
            os.makedirs(folder)
            _add_track(folder)

        result = import_tree_service.build_import_tree(temp_import_dir)

        names = [node.name for node in result]
        assert names == ["ABBA", "Beatles", "Zeppelin"]

    def test_deeply_nested_structure(self, import_tree_service, temp_import_dir):
        """Test deeply nested folder structure."""
        # Create: Level1/Level2/Level3/Level4 (leaf)
        deep_path = os.path.join(temp_import_dir, "Level1", "Level2", "Level3", "Level4")
        os.makedirs(deep_path)
        _add_track(deep_path)

        result = import_tree_service.build_import_tree(temp_import_dir)

        # Navigate through the tree
        level1 = result[0]
        assert level1.name == "Level1"
        assert level1.is_album is False

        level2 = level1.children[0]
        assert level2.name == "Level2"
        assert level2.is_album is False

        level3 = level2.children[0]
        assert level3.name == "Level3"
        assert level3.is_album is False

        level4 = level3.children[0]
        assert level4.name == "Level4"
        assert level4.is_album is True  # Leaf folder

    def test_relative_paths_calculated_correctly(self, import_tree_service, temp_import_dir):
        """Test that relative paths are calculated from import root."""
        # Create: Artist/Album/
        album_path = os.path.join(temp_import_dir, "Artist", "Album")
        os.makedirs(album_path)
        _add_track(album_path)

        result = import_tree_service.build_import_tree(temp_import_dir)

        artist_node = result[0]
        assert artist_node.path == "Artist"

        album_node = artist_node.children[0]
        assert album_node.path == "Artist/Album"

    def test_files_are_ignored(self, import_tree_service, temp_import_dir):
        """Test that files are not included in the tree."""
        # Create a directory (with audio so it isn't suppressed) and a
        # loose file at the import root.
        folder = os.path.join(temp_import_dir, "Folder")
        os.makedirs(folder)
        _add_track(folder)
        Path(os.path.join(temp_import_dir, "file.txt")).touch()

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert len(result) == 1
        assert result[0].name == "Folder"

    def test_single_disc_folder_is_album(self, import_tree_service, temp_import_dir):
        """Test that a single 'Disc 1' folder (without siblings) is treated as album."""
        # Create: Artist/Album Disc 1/ (only one disc folder)
        disc_path = os.path.join(temp_import_dir, "Artist", "Album Disc 1")
        os.makedirs(disc_path)
        _add_track(disc_path)

        result = import_tree_service.build_import_tree(temp_import_dir)

        artist_node = result[0]
        assert artist_node.is_album is False

        disc_node = artist_node.children[0]
        # Single disc folder should be treated as a regular album
        assert disc_node.name == "Album Disc 1"
        assert disc_node.is_album is True
        assert disc_node.is_multi_disc_parent is False

    def test_import_path_is_file_returns_empty(self, import_tree_service, temp_import_dir):
        """Test that if import_path points to a file, empty list is returned."""
        file_path = os.path.join(temp_import_dir, "not_a_directory.txt")
        Path(file_path).touch()

        result = import_tree_service.build_import_tree(file_path)
        assert result == []


class TestAlbumFolderDetection:
    """Tests specifically for album folder detection logic."""

    @pytest.fixture
    def import_tree_service(self):
        """Create an ImportTreeService instance."""
        return ImportTreeService()

    @pytest.fixture
    def temp_import_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_leaf_folder_is_album(self, import_tree_service, temp_import_dir):
        """Test that a leaf folder (no subdirectories) is marked as album."""
        leaf_path = os.path.join(temp_import_dir, "Leaf Album")
        os.makedirs(leaf_path)
        _add_track(leaf_path)

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert result[0].is_album is True
        assert result[0].has_subfolders is False

    def test_folder_with_children_not_album(self, import_tree_service, temp_import_dir):
        """Test that a folder with children is not marked as album."""
        parent_path = os.path.join(temp_import_dir, "Parent")
        child_path = os.path.join(parent_path, "Child")
        os.makedirs(child_path)
        _add_track(child_path)

        result = import_tree_service.build_import_tree(temp_import_dir)

        parent_node = result[0]
        assert parent_node.is_album is False
        assert parent_node.has_subfolders is True

    def test_multi_disc_parent_is_album(self, import_tree_service, temp_import_dir):
        """Test that a multi-disc parent folder is marked as album."""
        parent_path = os.path.join(temp_import_dir, "Album")
        os.makedirs(os.path.join(parent_path, "Album Disc 1"))
        os.makedirs(os.path.join(parent_path, "Album Disc 2"))
        _add_track(os.path.join(parent_path, "Album Disc 1"))
        _add_track(os.path.join(parent_path, "Album Disc 2"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        album_node = result[0]
        assert album_node.is_album is True
        assert album_node.is_multi_disc_parent is True

    def test_disc_subfolders_not_album(self, import_tree_service, temp_import_dir):
        """Test that disc subfolders in a multi-disc set are NOT albums."""
        parent_path = os.path.join(temp_import_dir, "Album")
        os.makedirs(os.path.join(parent_path, "Album Disc 1"))
        os.makedirs(os.path.join(parent_path, "Album Disc 2"))
        _add_track(os.path.join(parent_path, "Album Disc 1"))
        _add_track(os.path.join(parent_path, "Album Disc 2"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        album_node = result[0]
        for child in album_node.children:
            assert child.is_album is False

    def test_mixed_disc_and_regular_folders(self, import_tree_service, temp_import_dir):
        """Test folder with both disc folders and regular subfolders."""
        parent_path = os.path.join(temp_import_dir, "Parent")
        os.makedirs(os.path.join(parent_path, "Album Disc 1"))
        os.makedirs(os.path.join(parent_path, "Album Disc 2"))
        os.makedirs(os.path.join(parent_path, "Bonus"))
        _add_track(os.path.join(parent_path, "Album Disc 1"))
        _add_track(os.path.join(parent_path, "Album Disc 2"))
        _add_track(os.path.join(parent_path, "Bonus"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        parent_node = result[0]
        # Parent should be multi-disc parent
        assert parent_node.is_multi_disc_parent is True
        assert parent_node.is_album is True

        # Find the Bonus folder - it should be a leaf album
        bonus_node = next(c for c in parent_node.children if c.name == "Bonus")
        assert bonus_node.is_album is True  # Leaf folder


class TestEmptyFolderSuppression:
    """Regression tests for issue #65 — empty folders must not show as albums.

    Deleting an album folder can leave its parent artist directory behind as an
    empty leaf. Such a husk must not appear in the tree as a phantom album.
    """

    @pytest.fixture
    def import_tree_service(self):
        return ImportTreeService()

    @pytest.fixture
    def temp_import_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_empty_leaf_folder_is_suppressed(self, import_tree_service, temp_import_dir):
        """An empty leaf folder (no audio, no subfolders) is dropped entirely."""
        os.makedirs(os.path.join(temp_import_dir, "Empty Artist"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert result == []

    def test_artist_husk_after_album_deletion_is_suppressed(
        self, import_tree_service, temp_import_dir
    ):
        """The exact issue #65 scenario: an artist dir with one real album and
        one emptied-out album leaf only surfaces the real album."""
        artist = os.path.join(temp_import_dir, "Artist")
        kept = os.path.join(artist, "Real Album")
        os.makedirs(kept)
        _add_track(kept)
        # The album whose audio was deleted leaves an empty husk behind.
        os.makedirs(os.path.join(artist, "Deleted Album"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert len(result) == 1
        artist_node = result[0]
        assert artist_node.name == "Artist"
        child_names = [c.name for c in artist_node.children]
        assert child_names == ["Real Album"]
        assert "Deleted Album" not in child_names

    def test_artist_with_only_empty_albums_is_suppressed(
        self, import_tree_service, temp_import_dir
    ):
        """If every child folder is an empty husk, the parent vanishes too."""
        artist = os.path.join(temp_import_dir, "Artist")
        os.makedirs(os.path.join(artist, "Gone One"))
        os.makedirs(os.path.join(artist, "Gone Two"))

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert result == []

    def test_leaf_with_only_non_audio_files_is_suppressed(
        self, import_tree_service, temp_import_dir
    ):
        """A leaf holding only sidecar files (e.g. a leftover cover.jpg the
        cleanup couldn't rmdir) is a husk, not an importable album, and is
        dropped — matching "deleted with the last content"."""
        folder = os.path.join(temp_import_dir, "Cover Only")
        os.makedirs(folder)
        Path(os.path.join(folder, "cover.jpg")).touch()

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert result == []


class TestBareDiscFolderDetection:
    """Bare `Disc 1` / `CD2` folder names — the most common folder-per-disc
    rip layout — must be detected as a multi-disc set (empty shared prefix),
    matching beets' own heuristic."""

    @pytest.fixture
    def import_tree_service(self):
        return ImportTreeService()

    @pytest.fixture
    def temp_import_dir(self):
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_bare_disc_folders_group(self):
        result = detect_multi_disc(["Disc 1", "Disc 2"])
        assert list(result.values()) == [["Disc 1", "Disc 2"]]

    def test_bare_cd_folders_group(self):
        result = detect_multi_disc(["CD1", "CD2", "CD3"])
        assert list(result.values()) == [["CD1", "CD2", "CD3"]]

    def test_pattern_matches_bare_disc_name(self):
        match = MULTI_DISC_PATTERN.match("Disc 2")
        assert match is not None
        assert match.group(2) == "2"

    def test_bare_disc_parent_is_album(self, import_tree_service, temp_import_dir):
        """A parent holding bare `Disc N` subfolders is the album node; the
        disc folders themselves are not albums."""
        album = os.path.join(temp_import_dir, "Die Grosse Box")
        for disc in ("Disc 1", "Disc 2"):
            os.makedirs(os.path.join(album, disc))
            Path(os.path.join(album, disc, "01 - Teil 1.mp3")).touch()

        result = import_tree_service.build_import_tree(temp_import_dir)

        assert len(result) == 1
        parent = result[0]
        assert parent.is_album is True
        assert parent.is_multi_disc_parent is True
        assert all(child.is_album is False for child in parent.children)
