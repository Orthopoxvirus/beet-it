"""Integration tests for upload API endpoints."""

import io
import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from unittest.mock import Mock, patch, MagicMock

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session


@pytest.fixture
def temp_import_dir():
    """Create a temporary directory for testing."""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    # Cleanup
    import shutil

    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def mock_db():
    """Create a mock database session."""
    return Mock(spec=Session)


class TestUploadResponseSchemas:
    """Tests for upload response schema validation."""

    def test_upload_response_schema(self):
        """Test UploadResponse schema."""
        from app.schemas.upload import UploadResponse, UploadedFile

        file_info = UploadedFile(
            filename="track.mp3",
            path="Album/track.mp3",
            size_bytes=1024000,
        )

        response = UploadResponse(
            status="success",
            message="Successfully uploaded 1 file",
            files_uploaded=1,
            files=[file_info],
        )

        assert response.status == "success"
        assert response.files_uploaded == 1
        assert len(response.files) == 1
        assert response.files[0].filename == "track.mp3"
        assert response.files[0].path == "Album/track.mp3"
        assert response.files[0].size_bytes == 1024000

    def test_uploaded_file_schema(self):
        """Test UploadedFile schema."""
        from app.schemas.upload import UploadedFile

        file_info = UploadedFile(
            filename="01 - Track.flac",
            path="Artist - Album (2024)/01 - Track.flac",
            size_bytes=45678901,
        )

        assert file_info.filename == "01 - Track.flac"
        assert file_info.path == "Artist - Album (2024)/01 - Track.flac"
        assert file_info.size_bytes == 45678901

    def test_file_conflict_schema(self):
        """Test FileConflict schema."""
        from app.schemas.upload import FileConflict

        conflict = FileConflict(
            filename="cover.jpg",
            path="Album/cover.jpg",
        )

        assert conflict.filename == "cover.jpg"
        assert conflict.path == "Album/cover.jpg"


class TestSingleFileUpload:
    """Tests for single file upload."""

    def test_upload_single_file_success(self, temp_import_dir, mock_db):
        """Test uploading a single file successfully."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        # Create mock library
        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        # Configure mock query
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        # Override database dependency
        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            # Create a test file
            file_content = b"Test audio file content"
            files = {"files": ("test_track.mp3", io.BytesIO(file_content), "audio/mpeg")}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["status"] == "success"
            assert data["files_uploaded"] == 1
            assert len(data["files"]) == 1
            assert data["files"][0]["filename"] == "test_track.mp3"
            assert data["files"][0]["path"] == "test_track.mp3"
            assert data["files"][0]["size_bytes"] == len(file_content)

            # Verify file was written
            written_path = Path(temp_import_dir) / "test_track.mp3"
            assert written_path.exists()
            assert written_path.read_bytes() == file_content
        finally:
            app.dependency_overrides.clear()

    def test_upload_single_file_with_path(self, temp_import_dir, mock_db):
        """Test uploading a single file with a custom path."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            file_content = b"Test audio file content"
            files = {"files": ("track.mp3", io.BytesIO(file_content), "audio/mpeg")}
            data = {"paths": json.dumps(["Artist/Album/track.mp3"])}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 200
            result = response.json()
            assert result["files"][0]["path"] == "Artist/Album/track.mp3"

            # Verify directory structure was created
            written_path = Path(temp_import_dir) / "Artist" / "Album" / "track.mp3"
            assert written_path.exists()
            assert written_path.read_bytes() == file_content
        finally:
            app.dependency_overrides.clear()


class TestMultipleFileUpload:
    """Tests for multiple file upload."""

    def test_upload_multiple_files_success(self, temp_import_dir, mock_db):
        """Test uploading multiple files successfully."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = [
                ("files", ("track1.mp3", io.BytesIO(b"Track 1 content"), "audio/mpeg")),
                ("files", ("track2.mp3", io.BytesIO(b"Track 2 content"), "audio/mpeg")),
                ("files", ("cover.jpg", io.BytesIO(b"Cover art"), "image/jpeg")),
            ]

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["files_uploaded"] == 3
            assert len(data["files"]) == 3

            # Verify all files were written
            import_path = Path(temp_import_dir)
            assert (import_path / "track1.mp3").exists()
            assert (import_path / "track2.mp3").exists()
            assert (import_path / "cover.jpg").exists()
        finally:
            app.dependency_overrides.clear()

    def test_upload_multiple_files_with_paths(self, temp_import_dir, mock_db):
        """Test uploading multiple files with custom paths."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = [
                ("files", ("track1.mp3", io.BytesIO(b"Track 1"), "audio/mpeg")),
                ("files", ("track2.mp3", io.BytesIO(b"Track 2"), "audio/mpeg")),
            ]
            data = {"paths": json.dumps(["Album/track1.mp3", "Album/track2.mp3"])}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 200
            result = response.json()
            assert all(f["path"].startswith("Album/") for f in result["files"])

            # Verify directory structure
            import_path = Path(temp_import_dir)
            assert (import_path / "Album" / "track1.mp3").exists()
            assert (import_path / "Album" / "track2.mp3").exists()
        finally:
            app.dependency_overrides.clear()


class TestFolderStructurePreservation:
    """Tests for folder structure preservation."""

    def test_preserve_nested_folder_structure(self, temp_import_dir, mock_db):
        """Test that nested folder structures are preserved."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            # Simulate album upload with nested structure
            files = [
                ("files", ("01 - Intro.flac", io.BytesIO(b"Track 1"), "audio/flac")),
                ("files", ("02 - Main.flac", io.BytesIO(b"Track 2"), "audio/flac")),
                ("files", ("cover.jpg", io.BytesIO(b"Cover"), "image/jpeg")),
            ]
            paths = [
                "Artist/Album (2024)/01 - Intro.flac",
                "Artist/Album (2024)/02 - Main.flac",
                "Artist/Album (2024)/cover.jpg",
            ]
            data = {"paths": json.dumps(paths)}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 200

            # Verify full directory structure
            import_path = Path(temp_import_dir)
            album_path = import_path / "Artist" / "Album (2024)"
            assert album_path.is_dir()
            assert (album_path / "01 - Intro.flac").exists()
            assert (album_path / "02 - Main.flac").exists()
            assert (album_path / "cover.jpg").exists()
        finally:
            app.dependency_overrides.clear()


class TestErrorCases:
    """Tests for error cases."""

    def test_library_not_found_404(self, mock_db):
        """Test 404 response for non-existent library."""
        from main import app
        from app.database import get_db

        # Configure mock to return None (library not found)
        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = None
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)
            files = {"files": ("track.mp3", io.BytesIO(b"content"), "audio/mpeg")}

            response = client.post(
                "/api/v1/libraries/nonexistent-library/upload",
                files=files,
            )

            assert response.status_code == 404
            data = response.json()
            assert data["detail"]["code"] == "LIBRARY_NOT_FOUND"
        finally:
            app.dependency_overrides.clear()

    def test_empty_request_400(self, temp_import_dir, mock_db):
        """Test 400/422 response for empty file list."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            # Send request without files - FastAPI returns 422 for missing required field
            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files={},
            )

            # FastAPI returns 422 for missing required field
            assert response.status_code == 422
        finally:
            app.dependency_overrides.clear()

    def test_path_traversal_400(self, temp_import_dir, mock_db):
        """Test 400 response for path traversal attempt."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = {"files": ("malicious.txt", io.BytesIO(b"data"), "text/plain")}
            data = {"paths": json.dumps(["../../../etc/passwd"])}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 400
            result = response.json()
            assert result["detail"]["code"] == "PATH_TRAVERSAL"
            assert "../../../etc/passwd" in result["detail"]["invalid_paths"]
        finally:
            app.dependency_overrides.clear()

    def test_file_conflict_409(self, temp_import_dir, mock_db):
        """Test 409 response for file conflict."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        # Create an existing file
        existing_file = Path(temp_import_dir) / "existing.mp3"
        existing_file.write_bytes(b"Existing content")

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = {"files": ("existing.mp3", io.BytesIO(b"New content"), "audio/mpeg")}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
            )

            assert response.status_code == 409
            result = response.json()
            assert result["detail"]["code"] == "FILE_EXISTS"
            assert len(result["detail"]["conflicts"]) == 1
            assert result["detail"]["conflicts"][0]["filename"] == "existing.mp3"
        finally:
            app.dependency_overrides.clear()

    def test_path_count_mismatch_400(self, temp_import_dir, mock_db):
        """Test 400 response for path count mismatch."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = [
                ("files", ("track1.mp3", io.BytesIO(b"Track 1"), "audio/mpeg")),
                ("files", ("track2.mp3", io.BytesIO(b"Track 2"), "audio/mpeg")),
            ]
            # Only one path for two files
            data = {"paths": json.dumps(["Album/track1.mp3"])}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 400
            result = response.json()
            assert result["detail"]["code"] == "PATH_COUNT_MISMATCH"
        finally:
            app.dependency_overrides.clear()

    def test_invalid_paths_json_400(self, temp_import_dir, mock_db):
        """Test 400 response for invalid paths JSON."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = {"files": ("track.mp3", io.BytesIO(b"content"), "audio/mpeg")}
            data = {"paths": "not valid json"}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 400
            result = response.json()
            assert result["detail"]["code"] == "INVALID_PATHS"
        finally:
            app.dependency_overrides.clear()

    def test_no_import_path_configured_400(self, mock_db):
        """Test 400 response when library has no import path."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 2
        mock_library.slug = "no-import"
        mock_library.import_path = None

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = {"files": ("track.mp3", io.BytesIO(b"content"), "audio/mpeg")}

            response = client.post(
                "/api/v1/libraries/no-import/upload",
                files=files,
            )

            assert response.status_code == 400
            result = response.json()
            assert result["detail"]["code"] == "NO_IMPORT_PATH"
        finally:
            app.dependency_overrides.clear()


class TestNullByteInjection:
    """Tests for null byte injection protection."""

    def test_null_byte_in_path_400(self, temp_import_dir, mock_db):
        """Test 400 response for null byte in path."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = {"files": ("track.mp3", io.BytesIO(b"content"), "audio/mpeg")}
            # Path with null byte
            data = {"paths": json.dumps(["Album\x00/track.mp3"])}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
                data=data,
            )

            assert response.status_code == 400
            result = response.json()
            assert result["detail"]["code"] == "INVALID_PATH_CHARACTERS"
        finally:
            app.dependency_overrides.clear()


class TestLargeFileHandling:
    """Tests for large file handling."""

    def test_large_file_upload(self, temp_import_dir, mock_db):
        """Test uploading a large file (simulated)."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            # Create a "large" file (5MB for testing)
            large_content = b"x" * (5 * 1024 * 1024)
            files = {"files": ("large_track.flac", io.BytesIO(large_content), "audio/flac")}

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
            )

            assert response.status_code == 200
            data = response.json()
            assert data["files"][0]["size_bytes"] == len(large_content)

            # Verify file was written completely
            written_path = Path(temp_import_dir) / "large_track.flac"
            assert written_path.exists()
            assert written_path.stat().st_size == len(large_content)
        finally:
            app.dependency_overrides.clear()


class TestMultipleConflicts:
    """Tests for handling multiple file conflicts."""

    def test_multiple_file_conflicts(self, temp_import_dir, mock_db):
        """Test that all conflicting files are reported."""
        from main import app
        from app.database import get_db
        from app.models.library import Library

        mock_library = Mock(spec=Library)
        mock_library.id = 1
        mock_library.slug = "test-library"
        mock_library.import_path = temp_import_dir

        mock_query = Mock()
        mock_query.filter.return_value.first.return_value = mock_library
        mock_db.query.return_value = mock_query

        # Create existing files
        import_path = Path(temp_import_dir)
        (import_path / "track1.mp3").write_bytes(b"Existing 1")
        (import_path / "track3.mp3").write_bytes(b"Existing 3")

        app.dependency_overrides[get_db] = lambda: mock_db

        try:
            client = TestClient(app)

            files = [
                ("files", ("track1.mp3", io.BytesIO(b"New 1"), "audio/mpeg")),
                ("files", ("track2.mp3", io.BytesIO(b"New 2"), "audio/mpeg")),
                ("files", ("track3.mp3", io.BytesIO(b"New 3"), "audio/mpeg")),
            ]

            response = client.post(
                "/api/v1/libraries/test-library/upload",
                files=files,
            )

            assert response.status_code == 409
            result = response.json()
            assert len(result["detail"]["conflicts"]) == 2

            conflict_filenames = [c["filename"] for c in result["detail"]["conflicts"]]
            assert "track1.mp3" in conflict_filenames
            assert "track3.mp3" in conflict_filenames
            assert "track2.mp3" not in conflict_filenames
        finally:
            app.dependency_overrides.clear()
