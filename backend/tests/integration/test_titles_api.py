"""Integration tests for the Titles page API.

GET /api/v1/libraries/{slug}/titles and /titles/ids — text search, BPM
filtering, pagination, and the select-all ceiling.
"""

import os
import sqlite3
import tempfile
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from main import app
from app.database import Base, get_db
from app.models.library import Library

engine = create_engine(
    "sqlite://",
    connect_args={"check_same_thread": False},
    poolclass=StaticPool,
)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


@pytest.fixture
def beets_db():
    """A beets DB with a handful of searchable, BPM-tagged tracks."""
    with tempfile.TemporaryDirectory() as tmp:
        db_path = os.path.join(tmp, "library.db")
        conn = sqlite3.connect(db_path)
        cur = conn.cursor()
        cur.execute(
            "CREATE TABLE albums (id INTEGER PRIMARY KEY, album TEXT, albumartist TEXT, artpath BLOB)"
        )
        cur.execute(
            """CREATE TABLE items (
                id INTEGER PRIMARY KEY, album_id INTEGER, title TEXT, artist TEXT,
                album TEXT, length REAL, format TEXT, bitrate INTEGER, path BLOB, bpm REAL
            )"""
        )
        # Distinct album artists (with umlauts) so the artist filter has real
        # groups to work with; item 5 has no album → no album artist at all.
        cur.execute("INSERT INTO albums VALUES (1, 'Running Mix', 'Die Ärzte', NULL)")
        cur.execute("INSERT INTO albums VALUES (2, 'Chill', 'Beethoven', NULL)")
        rows = [
            (1, 1, "Marathon", "Kraftklub", 155.0),
            (2, 1, "Sprint", "Kraftklub", 160.0),
            (3, 2, "Sofa", "Slowband", 78.0),
            (4, 2, "Untagged", "Slowband", None),
            (5, None, "Loose Single", "Solo", 152.0),
        ]
        for item_id, album_id, title, artist, bpm in rows:
            cur.execute(
                "INSERT INTO items (id, album_id, title, artist, album, length, format, bitrate, path, bpm) "
                "VALUES (?, ?, ?, ?, '', 60.0, 'mp3', 320, ?, ?)",
                (item_id, album_id, title, artist, f"/m/{title}.mp3".encode(), bpm),
            )
        conn.commit()
        conn.close()
        yield db_path


@pytest.fixture
def client(beets_db):
    Base.metadata.create_all(bind=engine)
    session = TestingSessionLocal()
    session.add(Library(
        id=1, name="Test Library", slug="test-library", path="/data/libraries/test",
        database_path=beets_db, library_path="/data/libraries/test",
    ))
    session.commit()

    def override_get_db():
        try:
            yield session
        finally:
            pass

    app.dependency_overrides[get_db] = override_get_db
    yield TestClient(app)
    app.dependency_overrides.clear()
    session.close()
    Base.metadata.drop_all(bind=engine)


class TestListTitles:
    def test_lists_all_titles_paginated(self, client):
        resp = client.get("/api/v1/libraries/test-library/titles?per_page=3")
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 5
        assert len(body["items"]) == 3
        assert body["page"] == 1

    def test_rows_carry_album_artist(self, client):
        by_title = client.get("/api/v1/libraries/test-library/titles?search=Marathon").json()
        assert by_title["items"][0]["albumartist"] == "Die Ärzte"

    def test_search_matches_title_artist_album(self, client):
        by_title = client.get("/api/v1/libraries/test-library/titles?search=Marathon").json()
        assert [i["title"] for i in by_title["items"]] == ["Marathon"]

        by_artist = client.get("/api/v1/libraries/test-library/titles?search=Kraftklub").json()
        assert by_artist["total"] == 2

        by_album = client.get("/api/v1/libraries/test-library/titles?search=Running").json()
        assert by_album["total"] == 2
        assert by_album["items"][0]["album"] == "Running Mix"

    def test_bpm_filter(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles?bpm_min=150&bpm_max=160"
        ).json()
        assert {i["title"] for i in resp["items"]} == {"Marathon", "Sprint", "Loose Single"}
        # Untagged (bpm NULL) never matches a BPM filter.
        assert all(i["bpm"] for i in resp["items"])

    def test_bpm_half_double(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles"
            "?bpm_min=150&bpm_max=160&include_half_double=true"
        ).json()
        assert {i["title"] for i in resp["items"]} == {
            "Marathon", "Sprint", "Loose Single", "Sofa",
        }

    def test_bpm_requires_both_bounds(self, client):
        resp = client.get("/api/v1/libraries/test-library/titles?bpm_min=150")
        assert resp.status_code == 400

    def test_bpm_min_above_max_rejected(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles?bpm_min=160&bpm_max=150"
        )
        assert resp.status_code == 400

    def test_unknown_library_404(self, client):
        assert client.get("/api/v1/libraries/nope/titles").status_code == 404


class TestListTitleIds:
    def test_returns_minimal_rows_for_filter(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles/ids?bpm_min=150&bpm_max=160"
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["total"] == 3
        assert {r["id"] for r in body["items"]} == {1, 2, 5}
        assert set(body["items"][0].keys()) == {"id", "title", "artist"}

    def test_select_all_ceiling(self, client):
        with patch("app.api.routes.titles.MAX_SELECT_ALL", 2):
            resp = client.get("/api/v1/libraries/test-library/titles/ids")
        assert resp.status_code == 413
        assert "limit is 2" in resp.json()["detail"]


class TestAlbumArtistFilter:
    def test_single_album_artist(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles",
            params={"album_artist": "Beethoven"},
        ).json()
        assert {i["title"] for i in resp["items"]} == {"Sofa", "Untagged"}
        assert all(i["albumartist"] == "Beethoven" for i in resp["items"])

    def test_multiple_album_artists(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles",
            params=[("album_artist", "Beethoven"), ("album_artist", "Die Ärzte")],
        ).json()
        # Item 5 (no album → no album artist) is excluded.
        assert resp["total"] == 4
        assert {i["title"] for i in resp["items"]} == {"Marathon", "Sprint", "Sofa", "Untagged"}

    def test_album_artist_narrows_select_all_ids(self, client):
        resp = client.get(
            "/api/v1/libraries/test-library/titles/ids",
            params={"album_artist": "Die Ärzte"},
        ).json()
        assert {r["id"] for r in resp["items"]} == {1, 2}


class TestListTitleArtists:
    def test_all_album_artists_unfiltered(self, client):
        body = client.get("/api/v1/libraries/test-library/titles/artists").json()
        # No filter → everything is "in result", alphabetical (case-insensitive).
        assert body["in_result"] == ["Beethoven", "Die Ärzte"]
        assert body["others"] == []
        assert body["total"] == 2

    def test_search_scopes_in_result_group(self, client):
        # "Marathon" only appears on the Die Ärzte album; Beethoven drops to others.
        body = client.get(
            "/api/v1/libraries/test-library/titles/artists",
            params={"search": "Marathon"},
        ).json()
        assert body["in_result"] == ["Die Ärzte"]
        assert body["others"] == ["Beethoven"]

    def test_bpm_scopes_in_result_group(self, client):
        # 150-160 matches only Die Ärzte tracks (+ an album-less single, which
        # has no album artist and appears in neither group).
        body = client.get(
            "/api/v1/libraries/test-library/titles/artists",
            params={"bpm_min": 150, "bpm_max": 160},
        ).json()
        assert body["in_result"] == ["Die Ärzte"]
        assert body["others"] == ["Beethoven"]
