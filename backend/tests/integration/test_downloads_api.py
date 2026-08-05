"""Integration tests for the Download Center API.

POST/GET/DELETE /api/v1/libraries/{slug}/downloads[...]
"""

import os
import tempfile
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.models.library import Library
from app.models.download_job import DownloadJob

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def db_session():
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(Library(
        id=1, name="Test Library", slug="test-library", path="/data/libraries/test",
        database_path="/tmp/test.db", library_path="/data/libraries/test",
    ))
    session.commit()
    yield session
    session.close()
    Base.metadata.drop_all(bind=engine)


@pytest.fixture
def client(db_session):
    def override_get_db():
        try:
            yield db_session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()


class TestQueueDownload:
    def test_creates_pending_job_and_dispatches_task(self, client, db_session):
        with patch("app.api.routes.downloads.pack_download_job.delay") as delay:
            resp = client.post(
                "/api/v1/libraries/test-library/downloads",
                json={"album_ids": [3, 1, 2]},
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["status"] == "pending"
        assert body["album_count"] == 3
        assert body["processed_count"] == 0
        assert body["expires_at"] is not None
        delay.assert_called_once_with(body["id"])

        job = db_session.query(DownloadJob).filter_by(id=body["id"]).first()
        assert job.album_ids == [3, 1, 2]  # order preserved

    def test_deduplicates_album_ids(self, client):
        with patch("app.api.routes.downloads.pack_download_job.delay"):
            resp = client.post(
                "/api/v1/libraries/test-library/downloads",
                json={"album_ids": [1, 1, 2, 2, 2]},
            )
        assert resp.json()["album_count"] == 2

    def test_rejects_empty_selection(self, client):
        # No albums AND no tracks — nothing to pack.
        resp = client.post(
            "/api/v1/libraries/test-library/downloads", json={"album_ids": []}
        )
        assert resp.status_code == 400

    def test_queues_track_and_mixed_jobs(self, client, db_session):
        with patch("app.api.routes.downloads.pack_download_job.delay"):
            resp = client.post(
                "/api/v1/libraries/test-library/downloads",
                json={"track_ids": [11, 12, 11]},
            )
            assert resp.status_code == 201
            assert resp.json()["album_count"] == 2  # deduped: one unit per track

            resp = client.post(
                "/api/v1/libraries/test-library/downloads",
                json={"album_ids": [1], "track_ids": [11]},
            )
            assert resp.status_code == 201
            assert resp.json()["album_count"] == 2  # 1 album + 1 track

    def test_404_for_unknown_library(self, client):
        with patch("app.api.routes.downloads.pack_download_job.delay"):
            resp = client.post(
                "/api/v1/libraries/nope/downloads", json={"album_ids": [1]}
            )
        assert resp.status_code == 404


class TestListDownloads:
    def test_lists_jobs_newest_first(self, client, db_session):
        now = datetime.now(timezone.utc)
        db_session.add_all([
            DownloadJob(library_id=1, library_slug="test-library", status="completed",
                        album_ids=[1], album_count=1, created_at=now - timedelta(hours=2)),
            DownloadJob(library_id=1, library_slug="test-library", status="pending",
                        album_ids=[2], album_count=1, created_at=now),
        ])
        db_session.commit()
        resp = client.get("/api/v1/libraries/test-library/downloads")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert resp.json()["total"] == 2
        assert items[0]["status"] == "pending"  # newest first


class TestDownloadFile:
    def test_409_when_not_ready(self, client, db_session):
        job = DownloadJob(library_id=1, library_slug="test-library", status="packing",
                          album_ids=[1], album_count=1)
        db_session.add(job)
        db_session.commit()
        resp = client.get(f"/api/v1/libraries/test-library/downloads/{job.id}/file")
        assert resp.status_code == 409

    def test_serves_completed_archive(self, client, db_session):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "out.zip")
            with open(zip_path, "wb") as f:
                f.write(b"PK\x03\x04 pretend zip")
            job = DownloadJob(library_id=1, library_slug="test-library", status="completed",
                              album_ids=[1], album_count=1, filename="out.zip",
                              zip_path=zip_path, size_bytes=16)
            db_session.add(job)
            db_session.commit()
            resp = client.get(f"/api/v1/libraries/test-library/downloads/{job.id}/file")
            assert resp.status_code == 200
            assert resp.headers["content-type"] == "application/zip"
            assert resp.content.startswith(b"PK")

    def test_410_when_archive_file_gone(self, client, db_session):
        job = DownloadJob(library_id=1, library_slug="test-library", status="completed",
                          album_ids=[1], album_count=1, filename="out.zip",
                          zip_path="/nonexistent/out.zip", size_bytes=10)
        db_session.add(job)
        db_session.commit()
        resp = client.get(f"/api/v1/libraries/test-library/downloads/{job.id}/file")
        assert resp.status_code == 410

    def test_404_for_unknown_job(self, client):
        resp = client.get("/api/v1/libraries/test-library/downloads/999/file")
        assert resp.status_code == 404


class TestCleanupExpiredDownloads:
    def test_removes_expired_jobs_and_archives_keeps_fresh(self, db_session, monkeypatch):
        import app.tasks.download_tasks as dt

        with tempfile.TemporaryDirectory() as tmp:
            now = datetime.now(timezone.utc)
            expired_zip = os.path.join(tmp, "expired.zip")
            fresh_zip = os.path.join(tmp, "fresh.zip")
            for p in (expired_zip, fresh_zip):
                with open(p, "wb") as f:
                    f.write(b"PK")

            expired = DownloadJob(
                library_id=1, library_slug="test-library", status="completed",
                album_ids=[1], album_count=1, zip_path=expired_zip,
                created_at=now - timedelta(days=8), expires_at=now - timedelta(days=1),
            )
            fresh = DownloadJob(
                library_id=1, library_slug="test-library", status="completed",
                album_ids=[2], album_count=1, zip_path=fresh_zip,
                created_at=now, expires_at=now + timedelta(days=7),
            )
            db_session.add_all([expired, fresh])
            db_session.commit()
            fresh_id = fresh.id

            # The task opens its own session; point it at the shared test engine.
            monkeypatch.setattr(dt, "get_db", lambda: TestingSessionLocal())
            result = dt.cleanup_expired_downloads()

            assert result["status"] == "completed"
            assert result["removed_count"] == 1
            assert not os.path.exists(expired_zip)  # archive removed
            assert os.path.exists(fresh_zip)        # fresh archive kept

            remaining = TestingSessionLocal().query(DownloadJob).all()
            assert [j.id for j in remaining] == [fresh_id]


class TestDeleteDownload:
    def test_deletes_row_and_archive(self, client, db_session):
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "out.zip")
            with open(zip_path, "wb") as f:
                f.write(b"PK")
            job = DownloadJob(library_id=1, library_slug="test-library", status="completed",
                              album_ids=[1], album_count=1, zip_path=zip_path)
            db_session.add(job)
            db_session.commit()
            job_id = job.id

            resp = client.delete(f"/api/v1/libraries/test-library/downloads/{job_id}")
            assert resp.status_code == 204
            assert not os.path.exists(zip_path)
            assert db_session.query(DownloadJob).filter_by(id=job_id).first() is None

    def test_404_for_unknown_job(self, client):
        resp = client.delete("/api/v1/libraries/test-library/downloads/999")
        assert resp.status_code == 404
