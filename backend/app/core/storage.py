import datetime
import json

import google.auth
from google.cloud import storage
from google.oauth2 import service_account

from app.config import settings

_client = None


def get_gcs_client() -> storage.Client:
    global _client
    if _client is None:
        kwargs = {"project": settings.gcs_project_id}

        if settings.gcs_service_account_json:
            info = json.loads(settings.gcs_service_account_json)
            credentials = service_account.Credentials.from_service_account_info(info)
            kwargs["credentials"] = credentials

        if settings.gcs_endpoint_url:
            # For fake-gcs-server or other local emulators
            from google.auth.credentials import AnonymousCredentials

            kwargs["credentials"] = AnonymousCredentials()
            _client = storage.Client(**kwargs)
            _client._connection.API_BASE_URL = settings.gcs_endpoint_url
        else:
            _client = storage.Client(**kwargs)
    return _client


def _get_bucket():
    return get_gcs_client().bucket(settings.gcs_bucket)


def _signing_kwargs() -> dict:
    """Return extra kwargs for generate_signed_url when running on Cloud Run.

    Cloud Run uses Compute Engine credentials which lack a private key.
    Passing the service_account_email triggers the IAM SignBlob API instead.
    """
    if settings.gcs_endpoint_url or settings.gcs_service_account_json:
        return {}
    credentials, _ = google.auth.default()
    return {"service_account_email": credentials.service_account_email}


def generate_presigned_upload_url(
    s3_key: str, content_type: str = "video/mp4", expires_in: int = 3600
) -> str:
    blob = _get_bucket().blob(s3_key)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=expires_in),
        method="PUT",
        content_type=content_type,
        **_signing_kwargs(),
    )
    return url


def generate_presigned_download_url(s3_key: str, expires_in: int = 3600) -> str:
    blob = _get_bucket().blob(s3_key)
    url = blob.generate_signed_url(
        version="v4",
        expiration=datetime.timedelta(seconds=expires_in),
        method="GET",
        **_signing_kwargs(),
    )
    return url


def upload_file(local_path: str, s3_key: str) -> None:
    blob = _get_bucket().blob(s3_key)
    blob.upload_from_filename(local_path)


def download_blob_bytes(s3_key: str) -> bytes | None:
    """Download a small file from GCS and return its bytes, or None if not found."""
    blob = _get_bucket().blob(s3_key)
    if not blob.exists():
        return None
    return blob.download_as_bytes()


def download_file(s3_key: str, local_path: str) -> None:
    blob = _get_bucket().blob(s3_key)
    blob.download_to_filename(local_path)
