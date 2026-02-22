import boto3
from botocore.config import Config

from app.config import settings

_client = None


def get_s3_client():
    global _client
    if _client is None:
        _client = boto3.client(
            "s3",
            endpoint_url=settings.s3_endpoint_url,
            aws_access_key_id=settings.aws_access_key_id,
            aws_secret_access_key=settings.aws_secret_access_key,
            region_name=settings.s3_region,
            config=Config(signature_version="s3v4"),
        )
    return _client


def generate_presigned_upload_url(s3_key: str, content_type: str = "video/mp4", expires_in: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": s3_key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def generate_presigned_download_url(s3_key: str, expires_in: int = 3600) -> str:
    client = get_s3_client()
    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": settings.s3_bucket,
            "Key": s3_key,
        },
        ExpiresIn=expires_in,
    )


def upload_file(local_path: str, s3_key: str) -> None:
    client = get_s3_client()
    client.upload_file(local_path, settings.s3_bucket, s3_key)


def download_file(s3_key: str, local_path: str) -> None:
    client = get_s3_client()
    client.download_file(settings.s3_bucket, s3_key, local_path)
