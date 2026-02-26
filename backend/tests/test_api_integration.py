"""
API integration tests — run against a live backend (Docker Compose or GCP).

Usage:
    # Against local Docker Compose stack:
    cd backend && docker compose up -d
    API_BASE_URL=http://localhost:8000 python -m pytest tests/test_api_integration.py -v

    # Against GCP production:
    API_BASE_URL=https://bball-api-XXXX.run.app python -m pytest tests/test_api_integration.py -v

These tests exercise the real API, database, GCS, and Pub/Sub — no mocking.
"""

import os
import uuid

import pytest
import requests

BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")


@pytest.fixture(scope="module")
def unique_email():
    return f"test-{uuid.uuid4().hex[:8]}@test.com"


@pytest.fixture(scope="module")
def auth_token(unique_email):
    """Sign up a new user and return the JWT token."""
    resp = requests.post(
        f"{BASE_URL}/auth/signup",
        json={"email": unique_email, "password": "testpass123"},
    )
    assert resp.status_code == 200, f"Signup failed: {resp.text}"
    data = resp.json()
    assert "access_token" in data
    return data["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ── Health ──────────────────────────────────────────────────────────────────


class TestHealth:
    def test_health_check(self):
        resp = requests.get(f"{BASE_URL}/health")
        assert resp.status_code == 200
        assert resp.json() == {"status": "ok"}


# ── Auth ────────────────────────────────────────────────────────────────────


class TestAuth:
    def test_signup_returns_token(self, auth_token):
        assert auth_token is not None
        assert len(auth_token) > 0

    def test_login(self, unique_email):
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": unique_email, "password": "testpass123"},
        )
        assert resp.status_code == 200
        assert "access_token" in resp.json()

    def test_login_wrong_password(self, unique_email):
        resp = requests.post(
            f"{BASE_URL}/auth/login",
            json={"email": unique_email, "password": "wrongpassword"},
        )
        assert resp.status_code == 401

    def test_get_me(self, auth_headers, unique_email):
        resp = requests.get(f"{BASE_URL}/auth/me", headers=auth_headers)
        assert resp.status_code == 200
        data = resp.json()
        assert data["email"] == unique_email

    def test_get_me_no_token(self):
        resp = requests.get(f"{BASE_URL}/auth/me")
        assert resp.status_code in (401, 403)

    def test_duplicate_signup(self, unique_email):
        resp = requests.post(
            f"{BASE_URL}/auth/signup",
            json={"email": unique_email, "password": "testpass123"},
        )
        assert resp.status_code in (400, 409)


# ── Videos ──────────────────────────────────────────────────────────────────


class TestVideos:
    def test_get_upload_url(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/videos/upload-url",
            json={"filename": "test_game.mp4", "content_type": "video/mp4"},
            headers=auth_headers,
        )
        assert resp.status_code == 200, f"Upload URL failed: {resp.text}"
        data = resp.json()
        assert "upload_url" in data
        assert "video_id" in data
        # Signed URL should be a real URL
        assert data["upload_url"].startswith("http")

    def test_list_videos(self, auth_headers):
        resp = requests.get(f"{BASE_URL}/videos", headers=auth_headers)
        assert resp.status_code == 200
        assert isinstance(resp.json(), list)

    def test_upload_url_no_auth(self):
        resp = requests.post(
            f"{BASE_URL}/videos/upload-url",
            json={"filename": "test.mp4", "content_type": "video/mp4"},
        )
        assert resp.status_code in (401, 403)


# ── Jobs ────────────────────────────────────────────────────────────────────


class TestJobs:
    def test_create_job_invalid_video(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/jobs",
            json={"video_id": str(uuid.uuid4())},
            headers=auth_headers,
        )
        # Should fail — video doesn't exist
        assert resp.status_code in (400, 404, 422)

    def test_reselect_nonexistent_job(self, auth_headers):
        resp = requests.post(
            f"{BASE_URL}/jobs/{uuid.uuid4()}/reselect",
            headers=auth_headers,
        )
        assert resp.status_code == 404


# ── Highlights ──────────────────────────────────────────────────────────────


class TestHighlights:
    def test_list_highlights_no_job(self, auth_headers):
        resp = requests.get(
            f"{BASE_URL}/highlights",
            params={"job_id": str(uuid.uuid4())},
            headers=auth_headers,
        )
        # Should return empty list or 404
        assert resp.status_code in (200, 404)
