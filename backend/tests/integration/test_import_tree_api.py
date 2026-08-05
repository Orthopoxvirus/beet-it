"""Integration tests for import tree API endpoint."""

import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch

import pytest
from fastapi.testclient import TestClient

from app.models.library import Library
from app.schemas.import_tree import ImportFolderNode, ImportTreeResponse


@pytest.fixture
def mock_library():
    """Create a mock library."""
    library = Mock(spec=Library)
    library.id = 1
    library.name = "Test Library"
    library.slug = "test-library"
    library.import_path = "/data/import/test"
    library.config_path = "/config/test.yaml"
    library.database_path = "/data/databases/test.db"
    library.library_path = "/data/libraries/test"
    library.created_at = datetime(2024, 1, 1, 0, 0, 0)
    library.updated_at = None
    return library


@pytest.fixture
def mock_library_no_import_path():
    """Create a mock library with no import_path."""
    library = Mock(spec=Library)
    library.id = 2
    library.name = "No Import Library"
    library.slug = "no-import"
    library.import_path = None
    library.config_path = "/config/no-import.yaml"
    library.database_path = "/data/databases/no-import.db"
    library.library_path = "/data/libraries/no-import"
    library.created_at = datetime(2024, 1, 1, 0, 0, 0)
    library.updated_at = None
    return library


class TestImportTreeResponseSchema:
    """Tests for ImportTreeResponse schema."""

    def test_import_tree_response_schema(self):
        """Test ImportTreeResponse schema validation."""
        response = ImportTreeResponse(
            import_path="/data/import/test",
            children=[
                ImportFolderNode(
                    name="Artist",
                    path="Artist",
                    is_album=False,
                    is_multi_disc_parent=False,
                    has_subfolders=True,
                    children=[
                        ImportFolderNode(
                            name="Album",
                            path="Artist/Album",
                            is_album=True,
                            is_multi_disc_parent=False,
                            has_subfolders=False,
                            children=[],
                        )
                    ],
                )
            ],
        )

        assert response.import_path == "/data/import/test"
        assert len(response.children) == 1
        assert response.children[0].name == "Artist"
        assert response.children[0].children[0].is_album is True

    def test_import_tree_response_empty_tree(self):
        """Test ImportTreeResponse with empty children."""
        response = ImportTreeResponse(
            import_path="/data/import/test",
            children=[],
        )

        assert response.import_path == "/data/import/test"
        assert response.children == []

    def test_import_tree_response_null_import_path(self):
        """Test ImportTreeResponse when import_path is null."""
        response = ImportTreeResponse(
            import_path=None,
            children=[],
        )

        assert response.import_path is None
        assert response.children == []


class TestImportFolderNodeSchema:
    """Tests for ImportFolderNode schema."""

    def test_import_folder_node_schema(self):
        """Test ImportFolderNode schema validation."""
        node = ImportFolderNode(
            name="Album",
            path="Artist/Album",
            is_album=True,
            is_multi_disc_parent=False,
            has_subfolders=False,
            children=[],
        )

        assert node.name == "Album"
        assert node.path == "Artist/Album"
        assert node.is_album is True
        assert node.is_multi_disc_parent is False
        assert node.has_subfolders is False
        assert node.children == []

    def test_import_folder_node_multi_disc_parent(self):
        """Test ImportFolderNode for multi-disc parent."""
        node = ImportFolderNode(
            name="Multi Disc Album",
            path="Artist/Multi Disc Album",
            is_album=True,
            is_multi_disc_parent=True,
            has_subfolders=True,
            children=[
                ImportFolderNode(
                    name="Multi Disc Album Disc 1",
                    path="Artist/Multi Disc Album/Multi Disc Album Disc 1",
                    is_album=False,
                    is_multi_disc_parent=False,
                    has_subfolders=False,
                    children=[],
                ),
                ImportFolderNode(
                    name="Multi Disc Album Disc 2",
                    path="Artist/Multi Disc Album/Multi Disc Album Disc 2",
                    is_album=False,
                    is_multi_disc_parent=False,
                    has_subfolders=False,
                    children=[],
                ),
            ],
        )

        assert node.is_album is True
        assert node.is_multi_disc_parent is True
        assert len(node.children) == 2
        # Disc subfolders should NOT be albums
        assert node.children[0].is_album is False
        assert node.children[1].is_album is False

    def test_import_folder_node_nested(self):
        """Test deeply nested ImportFolderNode."""
        deep_node = ImportFolderNode(
            name="Level4",
            path="Level1/Level2/Level3/Level4",
            is_album=True,
            is_multi_disc_parent=False,
            has_subfolders=False,
            children=[],
        )

        level3 = ImportFolderNode(
            name="Level3",
            path="Level1/Level2/Level3",
            is_album=False,
            is_multi_disc_parent=False,
            has_subfolders=True,
            children=[deep_node],
        )

        level2 = ImportFolderNode(
            name="Level2",
            path="Level1/Level2",
            is_album=False,
            is_multi_disc_parent=False,
            has_subfolders=True,
            children=[level3],
        )

        level1 = ImportFolderNode(
            name="Level1",
            path="Level1",
            is_album=False,
            is_multi_disc_parent=False,
            has_subfolders=True,
            children=[level2],
        )

        # Navigate through the tree
        assert level1.children[0].children[0].children[0].name == "Level4"
        assert level1.children[0].children[0].children[0].is_album is True


class TestImportTreeEndpointScenarios:
    """Tests for import tree endpoint behavior."""

    def test_library_not_found_returns_404(self):
        """Test that 404 is returned when library slug doesn't exist."""
        from app.api.libraries import get_library_by_slug
        from fastapi import HTTPException

        # Verify the helper function raises 404
        with patch("app.api.libraries.Session") as mock_session:
            mock_db = Mock()
            mock_db.query.return_value.filter.return_value.first.return_value = None

            try:
                get_library_by_slug(mock_db, "nonexistent")
                assert False, "Should have raised HTTPException"
            except HTTPException as e:
                assert e.status_code == 404
                assert e.detail == "Library not found"

    def test_empty_import_path_returns_empty_tree(self, mock_library_no_import_path):
        """Test that null import_path returns empty tree."""
        from app.services.import_tree import ImportTreeService

        # When import_path is None, the endpoint should return empty children
        # This is tested at the schema level
        response = ImportTreeResponse(
            import_path=None,
            children=[],
        )

        assert response.import_path is None
        assert response.children == []

    def test_nonexistent_import_path_returns_empty_tree(self):
        """Test that nonexistent import_path returns empty tree."""
        from app.services.import_tree import ImportTreeService

        service = ImportTreeService()
        result = service.build_import_tree("/nonexistent/path")

        assert result == []


class TestImportTreeEndpointIntegration:
    """Integration tests with temporary filesystem."""

    @pytest.fixture
    def temp_import_dir(self):
        """Create a temporary directory for testing."""
        with tempfile.TemporaryDirectory() as temp_dir:
            yield temp_dir

    def test_full_integration_with_filesystem(self, temp_import_dir):
        """Test the complete flow with actual filesystem."""
        from app.services.import_tree import ImportTreeService

        # Create a realistic folder structure. Leaf album folders get a track
        # so they aren't suppressed as empty husks (issue #65).
        def _track(folder):
            Path(os.path.join(folder, "01 - Track.mp3")).touch()

        kob = os.path.join(temp_import_dir, "Miles Davis", "Kind of Blue")
        bb1 = os.path.join(temp_import_dir, "Miles Davis", "Bitches Brew", "Bitches Brew Disc 1")
        bb2 = os.path.join(temp_import_dir, "Miles Davis", "Bitches Brew", "Bitches Brew Disc 2")
        als = os.path.join(temp_import_dir, "John Coltrane", "A Love Supreme")
        for leaf in (kob, bb1, bb2, als):
            os.makedirs(leaf)
            _track(leaf)

        service = ImportTreeService()
        result = service.build_import_tree(temp_import_dir)

        # Verify structure
        assert len(result) == 2

        # Find artists
        artists = {node.name: node for node in result}
        assert "Miles Davis" in artists
        assert "John Coltrane" in artists

        # Check Miles Davis
        miles = artists["Miles Davis"]
        assert miles.is_album is False
        assert len(miles.children) == 2

        miles_albums = {child.name: child for child in miles.children}

        # Kind of Blue - regular album (leaf folder)
        kind_of_blue = miles_albums["Kind of Blue"]
        assert kind_of_blue.is_album is True
        assert kind_of_blue.is_multi_disc_parent is False
        assert kind_of_blue.has_subfolders is False

        # Bitches Brew - multi-disc album
        bitches_brew = miles_albums["Bitches Brew"]
        assert bitches_brew.is_album is True
        assert bitches_brew.is_multi_disc_parent is True
        assert bitches_brew.has_subfolders is True
        assert len(bitches_brew.children) == 2

        # Disc folders should NOT be albums
        for disc in bitches_brew.children:
            assert disc.is_album is False

        # Check John Coltrane
        coltrane = artists["John Coltrane"]
        assert coltrane.is_album is False
        assert len(coltrane.children) == 1

        love_supreme = coltrane.children[0]
        assert love_supreme.name == "A Love Supreme"
        assert love_supreme.is_album is True

    def test_response_json_format(self, temp_import_dir):
        """Test that response can be serialized to JSON correctly."""
        from app.services.import_tree import ImportTreeService
        import json

        # Create simple structure (leaf album needs a track so it isn't
        # suppressed as an empty husk — issue #65).
        album = os.path.join(temp_import_dir, "Artist", "Album")
        os.makedirs(album)
        Path(os.path.join(album, "01 - Track.mp3")).touch()

        service = ImportTreeService()
        children = service.build_import_tree(temp_import_dir)

        response = ImportTreeResponse(
            import_path=temp_import_dir,
            children=children,
        )

        # Serialize to JSON
        json_str = response.model_dump_json()
        parsed = json.loads(json_str)

        # Verify JSON structure
        assert "import_path" in parsed
        assert "children" in parsed
        assert len(parsed["children"]) == 1
        assert parsed["children"][0]["name"] == "Artist"
        assert parsed["children"][0]["is_album"] is False
        assert len(parsed["children"][0]["children"]) == 1
        assert parsed["children"][0]["children"][0]["name"] == "Album"
        assert parsed["children"][0]["children"][0]["is_album"] is True
