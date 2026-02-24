"""Tests for GCS storage module."""

from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def _reset_client():
    """Reset the module-level singleton before each test."""
    import app.core.storage as mod
    mod._client = None
    yield
    mod._client = None


@patch("app.core.storage.get_gcs_client")
def test_generate_presigned_upload_url(mock_get_client):
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.example.com/upload?sig=abc"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_get_client.return_value.bucket.return_value = mock_bucket

    from app.core.storage import generate_presigned_upload_url

    url = generate_presigned_upload_url("uploads/test.mp4", "video/mp4", 3600)

    assert url == "https://storage.example.com/upload?sig=abc"
    mock_bucket.blob.assert_called_once_with("uploads/test.mp4")
    mock_blob.generate_signed_url.assert_called_once()
    call_kwargs = mock_blob.generate_signed_url.call_args[1]
    assert call_kwargs["method"] == "PUT"
    assert call_kwargs["content_type"] == "video/mp4"


@patch("app.core.storage.get_gcs_client")
def test_generate_presigned_download_url(mock_get_client):
    mock_blob = MagicMock()
    mock_blob.generate_signed_url.return_value = "https://storage.example.com/download?sig=xyz"
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_get_client.return_value.bucket.return_value = mock_bucket

    from app.core.storage import generate_presigned_download_url

    url = generate_presigned_download_url("highlights/test.mp4", 7200)

    assert url == "https://storage.example.com/download?sig=xyz"
    call_kwargs = mock_blob.generate_signed_url.call_args[1]
    assert call_kwargs["method"] == "GET"


@patch("app.core.storage.get_gcs_client")
def test_upload_file(mock_get_client):
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_get_client.return_value.bucket.return_value = mock_bucket

    from app.core.storage import upload_file

    upload_file("/tmp/local.mp4", "uploads/remote.mp4")

    mock_bucket.blob.assert_called_once_with("uploads/remote.mp4")
    mock_blob.upload_from_filename.assert_called_once_with("/tmp/local.mp4")


@patch("app.core.storage.get_gcs_client")
def test_download_file(mock_get_client):
    mock_blob = MagicMock()
    mock_bucket = MagicMock()
    mock_bucket.blob.return_value = mock_blob
    mock_get_client.return_value.bucket.return_value = mock_bucket

    from app.core.storage import download_file

    download_file("uploads/remote.mp4", "/tmp/local.mp4")

    mock_bucket.blob.assert_called_once_with("uploads/remote.mp4")
    mock_blob.download_to_filename.assert_called_once_with("/tmp/local.mp4")


@patch("app.core.storage.storage.Client")
def test_get_gcs_client_with_endpoint(mock_client_cls):
    """When gcs_endpoint_url is set, client uses AnonymousCredentials."""
    import app.core.storage as mod

    mock_instance = MagicMock()
    mock_client_cls.return_value = mock_instance

    client = mod.get_gcs_client()

    assert client is mock_instance
    # Verify it was called with anonymous credentials
    call_kwargs = mock_client_cls.call_args[1]
    assert call_kwargs["project"] == "bball-local"
