"""
Google Cloud Storage service for document operations.
"""
from __future__ import annotations

import json
import logging
import mimetypes
import os
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import List
from uuid import uuid4

from google.cloud import storage
from google.cloud.exceptions import NotFound

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
        # Supports both JSON string (for cloud platforms) and file path (for local dev)
        if getattr(settings, "google_application_credentials", ""):
            cred_value = settings.google_application_credentials.strip()
            if cred_value:
                # Check if it's a JSON string (starts with {) - for cloud platforms
                if cred_value.startswith("{"):
                    try:
                        cred_dict = json.loads(cred_value)
                        self._client = storage.Client.from_service_account_info(cred_dict)
                    except json.JSONDecodeError:
                        self._client = storage.Client()
                # Otherwise, treat as file path
                elif os.path.exists(cred_value):
                    self._client = storage.Client.from_service_account_json(cred_value)
                else:
                    # File not found, fall back to ADC
                    self._client = storage.Client()
            else:
                self._client = storage.Client()
        else:
            self._client = storage.Client()

        self._bucket = self._client.bucket(settings.gcs_bucket_name)

    def _blob_to_document(self, blob, user_id_hint: str | None = None) -> StoredDocument:
        """Convert a GCS blob to StoredDocument."""
        path = blob.name  # e.g., users/{userId}/... or documents/company/...
        filename = path.split("/")[-1]
        size = int(blob.size or 0)
        content_type, _ = mimetypes.guess_type(filename)
        file_type = content_type or "application/octet-stream"

        # Determine scope based on prefixed path
        # Treat both "documents/company/" and "company/" as company documents
        is_company = path.startswith("documents/company/") or path.startswith("company/")

        # Derive user_id from path for user docs, otherwise use provided hint or empty
        # Structure: users/{user_id}/{document_id}/{filename}
        if path.startswith("users/"):
            parts = path.split("/")
            # users/{user_id}/{document_id}/{filename}
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

    def list_all_documents(self) -> List[StoredDocument]:
        """
        List ALL documents from the bucket, regardless of prefix or path.
        
        This method retrieves every blob in the bucket that is not a directory placeholder.
        """
        documents: List[StoredDocument] = []
        
        try:
            # List all blobs in the bucket without any prefix filter
            for blob in self._bucket.list_blobs():
                if not blob.name.endswith("/"):  # Skip "directory" placeholders
                    # Determine user_id hint from path if possible
                    user_id_hint = None
                    if blob.name.startswith("users/"):
                        parts = blob.name.split("/")
                        if len(parts) > 1:
                            user_id_hint = parts[1]
                    elif blob.name.startswith("documents/company/"):
                        user_id_hint = "company"
                    
                    documents.append(self._blob_to_document(blob, user_id_hint=user_id_hint))
            
            return documents
        except Exception as exc:
            logger.exception("Error listing all documents from GCS: %s", exc)
            raise

    def list_documents_by_scope(
        self, user_id: str, scope: str, is_admin: bool
    ) -> List[StoredDocument]:
        """
        List documents from GCS based on knowledge scope.

        Scope rules:
        - MY: only user's documents under users/{user_id}/
        - COMPANY: only company docs under documents/company/
        - ALL: user's docs + company docs
        
        Storage structure:
        - User docs: users/{user_id}/{document_id}/{filename}
        - Company docs: documents/company/{document_id}/{filename}
        """
        scope = (scope or "ALL").upper()
        documents: List[StoredDocument] = []

        try:
            if scope in ("MY", "ALL"):
                # Structure: users/{user_id}/{document_id}/{filename}
                user_prefix = f"users/{user_id}/"
                for blob in self._bucket.list_blobs(prefix=user_prefix):
                    if not blob.name.endswith("/"):  # Skip "directory" placeholders
                        documents.append(self._blob_to_document(blob, user_id_hint=user_id))

            if scope in ("COMPANY", "ALL"):
                # Primary company docs location used by the app
                company_prefixes = [
                    "documents/company/",  # app-created company docs
                    "company/",            # legacy/other company docs placed directly under 'company/'
                ]
                for prefix in company_prefixes:
                    for blob in self._bucket.list_blobs(prefix=prefix):
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

        Storage key pattern (bucket name → logical folders):

        - Company docs:
          documents/company/{filename}
        - User docs:
          users/{user_id}/{filename}

        This is intentionally "flat" under each user so that the path never
        includes a separate document_id segment – the folder structure in GCS
        is always strictly:

            different-documentation/users/{user_id}/{document_name}
        """
        safe_name = filename.replace(" ", "_")

        if is_company_doc:
            path = f"documents/company/{safe_name}"
        else:
            # Store user documents in a flat per-user folder:
            #   gs://<bucket>/users/{user_id}/{filename}
            # No document_id segment is ever added to the path.
            path = f"users/{user_id}/{safe_name}"

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
            True if deleted successfully, False if document doesn't exist in GCS
        """
        try:
            # Extract path from bucket_path (format: gs://bucket-name/path)
            if bucket_path.startswith("gs://"):
                gcs_path = bucket_path.replace(f"gs://{self._bucket.name}/", "")
            else:
                # Assume it's already just the path
                gcs_path = bucket_path
            
            blob = self._bucket.blob(gcs_path)
            
            # Check if blob exists before trying to delete
            if not blob.exists():
                logger.warning(f"Document does not exist in GCS (may have been deleted manually): {gcs_path}")
                return False
            
            blob.delete()
            logger.info(f"Successfully deleted document from GCS: {gcs_path}")
            return True
        except NotFound:
            # Document doesn't exist in GCS - this is okay, just log and return False
            logger.warning(f"Document not found in GCS (may have been deleted manually): {bucket_path}")
            return False
        except Exception as exc:
            logger.error(f"Error deleting document from GCS {bucket_path}: {exc}")
            raise

    def document_exists(self, bucket_path: str) -> bool:
        """
        Check if a document exists in Google Cloud Storage.
        
        Args:
            bucket_path: Full GCS path (format: gs://bucket-name/path/to/file) or just the path
            
        Returns:
            True if document exists, False otherwise
        """
        try:
            # Extract path from bucket_path (format: gs://bucket-name/path)
            if bucket_path.startswith("gs://"):
                # Use split to be more robust than replace
                if f"gs://{self._bucket.name}/" in bucket_path:
                    gcs_path = bucket_path.split(f"gs://{self._bucket.name}/", 1)[1]
                else:
                    # Try to extract path after gs://bucket-name/
                    parts = bucket_path.split("/", 3)
                    gcs_path = parts[3] if len(parts) > 3 else bucket_path
            else:
                # Assume it's already just the path
                gcs_path = bucket_path
            
            blob = self._bucket.blob(gcs_path)
            exists = blob.exists()
            logger.debug(f"Checked document existence: bucket_path={bucket_path}, gcs_path={gcs_path}, exists={exists}")
            return exists
        except Exception as exc:
            logger.error(f"Error checking document existence for {bucket_path}: {exc}")
            # If we can't check, assume it exists to avoid false negatives
            return True

    def get_signed_url(self, bucket_path: str, expiration_seconds: int = 3600) -> str:
        """
        Generate a signed URL for viewing a document in Google Cloud Storage.
        
        Args:
            bucket_path: Full GCS path (format: gs://bucket-name/path/to/file) or just the path
            expiration_seconds: URL expiration time in seconds (default: 3600 = 1 hour)
            
        Returns:
            Signed URL string that can be used to access the document
        """
        try:
            # Extract path from bucket_path (format: gs://bucket-name/path)
            if bucket_path.startswith("gs://"):
                gcs_path = bucket_path.replace(f"gs://{self._bucket.name}/", "")
            else:
                # Assume it's already just the path
                gcs_path = bucket_path
            
            blob = self._bucket.blob(gcs_path)
            
            # Check if blob exists
            if not blob.exists():
                raise ValueError(f"Document not found at path: {gcs_path}")
            
            # Calculate expiration datetime (current time + expiration_seconds)
            expiration_time = datetime.utcnow() + timedelta(seconds=expiration_seconds)
            
            # Generate signed URL with expiration datetime
            url = blob.generate_signed_url(
                expiration=expiration_time,
                method="GET"
            )
            
            logger.info(f"Generated signed URL for document: {gcs_path} (expires at {expiration_time.isoformat()})")
            return url
        except Exception as exc:
            logger.error(f"Error generating signed URL for {bucket_path}: {exc}")
            raise


# Singleton instance
try:
    storage_service = StorageService()
except Exception as exc:  # pragma: no cover - initialization guard
    logger.error("Failed to initialize StorageService: %s", exc)
    storage_service = None


