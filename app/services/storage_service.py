"""
Google Cloud Storage service for document operations.
"""
from __future__ import annotations

import logging
import mimetypes
from dataclasses import dataclass
from typing import List
from uuid import uuid4

from google.cloud import storage

from app.config import settings


logger = logging.getLogger(__name__)


@dataclass
class StoredDocument:
    """Internal document representation for responses."""

    id: str
    filename: str
    file_type: str
    file_size: int
    bucket_path: str
    user_id: str
    is_company_doc: bool
    uploaded_at: str


class StorageService:
    """Service for interacting with Google Cloud Storage."""

    def __init__(self) -> None:
        if not getattr(settings, "gcs_bucket_name", None):
            raise RuntimeError(
                "GCS bucket name is not configured. Please set GCS_BUCKET_NAME in environment variables."
            )

        # Prefer explicit service-account key file if configured, otherwise fall back to ADC.
        # This makes local dev on Windows much less flaky.
        if getattr(settings, "google_application_credentials", ""):
            cred_path = settings.google_application_credentials.strip()
            if cred_path:
                self._client = storage.Client.from_service_account_json(cred_path)
            else:
                self._client = storage.Client()
        else:
            self._client = storage.Client()

        self._bucket = self._client.bucket(settings.gcs_bucket_name)

    def _blob_to_document(self, blob, user_id_hint: str | None = None) -> StoredDocument:
        """Convert a GCS blob to StoredDocument."""
        path = blob.name  # e.g., users/{userId}/file.ext or company/file.ext
        filename = path.split("/")[-1]
        size = int(blob.size or 0)
        content_type, _ = mimetypes.guess_type(filename)
        file_type = content_type or "application/octet-stream"

        is_company = path.startswith("company/")
        # Derive user_id from path for user docs, otherwise use provided hint or empty
        if path.startswith("users/"):
            parts = path.split("/")
            doc_user_id = parts[1] if len(parts) > 2 else user_id_hint or ""
        else:
            doc_user_id = user_id_hint or ""

        uploaded_at = blob.time_created.isoformat() if blob.time_created else ""

        return StoredDocument(
            id=path,
            filename=filename,
            file_type=file_type,
            file_size=size,
            bucket_path=f"gs://{self._bucket.name}/{path}",
            user_id=doc_user_id,
            is_company_doc=is_company,
            uploaded_at=uploaded_at,
        )

    def list_documents_by_scope(
        self, user_id: str, scope: str, is_admin: bool
    ) -> List[StoredDocument]:
        """
        List documents from GCS based on knowledge scope.

        Scope rules:
        - MY: only user's documents under users/{user_id}/
        - COMPANY: only company docs under company/
        - ALL: user's docs + company docs
        """
        scope = (scope or "ALL").upper()
        documents: List[StoredDocument] = []

        try:
            if scope in ("MY", "ALL"):
                user_prefix = f"users/{user_id}/"
                for blob in self._bucket.list_blobs(prefix=user_prefix):
                    if not blob.name.endswith("/"):  # Skip "directory" placeholders
                        documents.append(self._blob_to_document(blob, user_id_hint=user_id))

            if scope in ("COMPANY", "ALL"):
                company_prefix = "company/"
                for blob in self._bucket.list_blobs(prefix=company_prefix):
                    if not blob.name.endswith("/"):
                        documents.append(self._blob_to_document(blob, user_id_hint="company"))

            # Non-admin users should still be able to see company docs; admin flag is reserved
            # for upload operations (marking company docs).

            return documents
        except Exception as exc:  # pragma: no cover - defensive logging
            logger.exception("Error listing documents from GCS: %s", exc)
            raise

    def upload_document(
        self,
        file_bytes: bytes,
        filename: str,
        user_id: str,
        is_company_doc: bool,
    ) -> StoredDocument:
        """
        Upload a document to GCS using the configured bucket.

        - If is_company_doc: path = company/{uuid}_{filename}
        - Else: path = users/{user_id}/{uuid}_{filename}
        """
        safe_name = filename.replace(" ", "_")
        object_id = uuid4().hex

        if is_company_doc:
            path = f"company/{object_id}_{safe_name}"
        else:
            path = f"users/{user_id}/{object_id}_{safe_name}"

        blob = self._bucket.blob(path)
        content_type, _ = mimetypes.guess_type(safe_name)

        logger.info(
            "Uploading document to GCS: path=%s, content_type=%s, size=%d bytes",
            path,
            content_type,
            len(file_bytes),
        )

        blob.upload_from_string(file_bytes, content_type=content_type or "application/octet-stream")

        # Refresh blob metadata
        blob.reload()

        return self._blob_to_document(blob, user_id_hint=user_id)

    def delete_document(self, bucket_path: str) -> bool:
        """
        Delete a document from Google Cloud Storage.
        
        Args:
            bucket_path: Full GCS path (format: gs://bucket-name/path/to/file)
            
        Returns:
            True if deleted successfully, False otherwise
        """
        try:
            # Extract path from bucket_path (format: gs://bucket-name/path)
            if bucket_path.startswith("gs://"):
                gcs_path = bucket_path.replace(f"gs://{self._bucket.name}/", "")
            else:
                # Assume it's already just the path
                gcs_path = bucket_path
            
            blob = self._bucket.blob(gcs_path)
            blob.delete()
            logger.info(f"Successfully deleted document from GCS: {gcs_path}")
            return True
        except Exception as exc:
            logger.error(f"Error deleting document from GCS {bucket_path}: {exc}")
            raise


# Singleton instance
try:
    storage_service = StorageService()
except Exception as exc:  # pragma: no cover - initialization guard
    logger.error("Failed to initialize StorageService: %s", exc)
    storage_service = None


