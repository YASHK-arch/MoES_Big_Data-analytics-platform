import hashlib
import os
import uuid
from datetime import datetime, timezone
from typing import Optional, Tuple

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

ALLOWED_MIME_TYPES = {
    "image/jpeg": "IMAGE",
    "image/png": "IMAGE",
    "image/webp": "IMAGE",
    "video/mp4": "VIDEO",
    "video/quicktime": "VIDEO",
}

MAX_FILE_SIZE_BYTES = 15 * 1024 * 1024  # 15 MB

MAGIC_SIGNATURES = {
    "image/jpeg": [b"\xff\xd8\xff"],
    "image/png": [b"\x89PNG\r\n\x1a\n"],
    "image/webp": [b"RIFF"],
    "video/mp4": [b"ftyp", b"moov", b"\x00\x00\x00"],
    "video/quicktime": [b"moov", b"mdat", b"ftypqt", b"\x00\x00\x00"],
}


def validate_file_magic_bytes(file_bytes: bytes, declared_mime: str) -> None:
    """Validate that the file header bytes match the declared MIME type to prevent disguised uploads."""
    if not file_bytes:
        raise ValueError("Uploaded file is empty (0 bytes).")

    # Reject HTML/SVG/executable injection signatures
    header_preview = file_bytes[:1024].lower()
    dangerous_signatures = [b"<script", b"<html", b"<?php", b"<!doctype html", b"<svg", b"#!/"]
    for danger in dangerous_signatures:
        if danger in header_preview:
            raise ValueError(f"File contains disallowed executable or script payload signature: {danger.decode('latin-1')}")

    # Check magic byte signatures
    expected_magics = MAGIC_SIGNATURES.get(declared_mime, [])
    matched = False
    for magic in expected_magics:
        if magic in file_bytes[:32]:
            matched = True
            break

    # Special check for WebP (RIFF....WEBP)
    if declared_mime == "image/webp":
        if file_bytes[:4] == b"RIFF" and b"WEBP" in file_bytes[:16]:
            matched = True

    if not matched and expected_magics:
        raise ValueError(
            f"File magic bytes do not match declared MIME type '{declared_mime}'. Upload rejected."
        )


class StorageService:
    """Service for interacting with S3 / MinIO object storage."""

    def __init__(
        self,
        endpoint_url: Optional[str] = None,
        access_key: Optional[str] = None,
        secret_key: Optional[str] = None,
        region_name: Optional[str] = None,
        use_ssl: Optional[bool] = None,
    ) -> None:
        self.endpoint_url = endpoint_url or settings.S3_ENDPOINT_URL
        self.access_key = access_key or settings.S3_ACCESS_KEY_ID
        self.secret_key = secret_key or settings.S3_SECRET_ACCESS_KEY
        self.region_name = region_name or settings.S3_REGION
        self.use_ssl = use_ssl if use_ssl is not None else settings.S3_USE_SSL
        self.default_bucket = settings.S3_BUCKET_NAME

        self.client = boto3.client(
            "s3",
            endpoint_url=self.endpoint_url,
            aws_access_key_id=self.access_key,
            aws_secret_access_key=self.secret_key,
            region_name=self.region_name,
            use_ssl=self.use_ssl,
            config=Config(signature_version="s3v4", s3={"addressing_style": "path"}),
        )

    def ensure_bucket_exists(self, bucket_name: Optional[str] = None) -> None:
        """Create bucket in MinIO / S3 if missing. Bucket remains strictly private."""
        target_bucket = bucket_name or self.default_bucket
        try:
            self.client.head_bucket(Bucket=target_bucket)
        except ClientError as e:
            error_code = e.response.get("Error", {}).get("Code", "")
            if error_code in ("404", "NoSuchBucket"):
                self.client.create_bucket(Bucket=target_bucket)
            else:
                raise

        # Ensure any legacy public bucket policy is revoked/deleted
        try:
            self.client.delete_bucket_policy(Bucket=target_bucket)
        except Exception:
            pass

    def upload_media_file(
        self,
        file_bytes: bytes,
        filename: str,
        content_type: str,
        bucket_name: Optional[str] = None,
        report_id: Optional[uuid.UUID] = None,
    ) -> Tuple[str, str, int, str]:
        """Validate, compute hash, and upload a media file to private object storage.

        Returns (storage_key, sha256_hash, file_size_bytes, media_type).
        """
        if content_type not in ALLOWED_MIME_TYPES:
            raise ValueError(
                f"Unsupported media MIME type: {content_type}. "
                f"Allowed types: {list(ALLOWED_MIME_TYPES.keys())}"
            )

        # 1. Enforce Magic Byte Verification
        validate_file_magic_bytes(file_bytes, content_type)

        file_size = len(file_bytes)
        if file_size > MAX_FILE_SIZE_BYTES:
            raise ValueError(
                f"File size ({file_size} bytes) exceeds the maximum allowed limit of "
                f"{MAX_FILE_SIZE_BYTES} bytes (15 MB)."
            )

        target_bucket = bucket_name or self.default_bucket
        self.ensure_bucket_exists(target_bucket)

        sha256_hash = hashlib.sha256(file_bytes).hexdigest()
        media_type = ALLOWED_MIME_TYPES[content_type]

        # 2. Strict path traversal prevention: strip directory components and generate immutable key
        safe_basename = os.path.basename(filename)
        clean_ext = os.path.splitext(safe_basename)[1].lower()
        if not clean_ext:
            clean_ext = ".jpg" if "jpeg" in content_type else ".png"

        now = datetime.now(timezone.utc)
        folder = report_id or uuid.uuid4()
        storage_key = (
            f"reports/{now.year}/{now.month:02d}/{now.day:02d}/{folder}/"
            f"{uuid.uuid4().hex}{clean_ext}"
        )

        self.client.put_object(
            Bucket=target_bucket,
            Key=storage_key,
            Body=file_bytes,
            ContentType=content_type,
        )

        return storage_key, sha256_hash, file_size, media_type

    def get_media_url(
        self,
        storage_key: str,
        bucket_name: Optional[str] = None,
        expires_in: Optional[int] = None,
    ) -> str:
        """Construct temporary presigned GET URL for secure, credential-free browser display."""
        target_bucket = bucket_name or self.default_bucket
        expiry = expires_in or settings.S3_PRESIGNED_EXPIRY_SECONDS
        return self.client.generate_presigned_url(
            "get_object",
            Params={"Bucket": target_bucket, "Key": storage_key},
            ExpiresIn=expiry,
        )

    def delete_media_file(self, storage_key: str, bucket_name: Optional[str] = None) -> None:
        """Delete an object from storage (e.g. on transaction rollback)."""
        target_bucket = bucket_name or self.default_bucket
        try:
            self.client.delete_object(Bucket=target_bucket, Key=storage_key)
        except Exception:
            # Best-effort cleanup
            pass


storage_service = StorageService()
