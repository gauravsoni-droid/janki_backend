"""
Document API endpoints for listing and uploading documents in Google Cloud Storage.
Documents are stored in GCS and metadata is saved in SQLite database.
"""
from typing import List, Optional
import os

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.routers.chat import verify_token
from app.services.storage_service import storage_service, StoredDocument
from app.database import get_db
from app.models.document import Document
from app.config import settings
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)


router = APIRouter()


class DocumentModel(BaseModel):
    """Response model for a single document."""

    id: str
    filename: str
    file_type: str
    file_size: int
    bucket_path: str
    user_id: str
    is_company_doc: bool
    uploaded_at: str
    category: Optional[str] = None


class CreateDocumentRequest(BaseModel):
    """Request model for creating a text-based document."""

    title: str
    category: str
    custom_category: Optional[str] = None
    content: str
    is_company_doc: bool = False


class DocumentListResponse(BaseModel):
    """Response model for a list of documents."""

    documents: List[DocumentModel]
    total: int


class ViewUrlResponse(BaseModel):
    """Response model for document view URL."""

    url: str
    expires_in: int


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    scope: Optional[str] = Query("ALL", description="MY | COMPANY | ALL"),
    limit: int = Query(100, ge=1, le=500),
    offset: int = Query(0, ge=0),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    List documents from database and/or bucket based on knowledge scope.
    
    Documents are retrieved from SQLite database using user_id from Google OAuth token.
    The same user_id is used consistently across sessions.
    
    When scope=ALL, also retrieves all documents directly from the bucket to ensure
    complete visibility of all available documents.

    - scope=MY: only documents uploaded by the current user
    - scope=COMPANY: only company-wide documents (is_company_doc=True)
    - scope=ALL: both personal and company documents, plus all documents from bucket
    """
    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))
    scope_upper = (scope or "ALL").upper()

    try:
        # When scope is ALL, retrieve documents from both database and bucket
        if scope_upper == "ALL" and storage_service:
            # Get ALL documents from bucket (not just specific prefixes)
            bucket_docs = storage_service.list_all_documents()
            logger.info(f"Retrieved {len(bucket_docs)} documents from bucket for scope ALL")

            # Helper function to normalize bucket_path for comparison
            def normalize_path(path: str) -> str:
                """Normalize bucket_path by removing gs://bucket-name/ prefix if present."""
                if not path:
                    return ""
                # Remove gs://bucket-name/ prefix if present
                if path.startswith("gs://"):
                    # Split: gs://bucket-name/path/to/file
                    # We want: path/to/file
                    parts = path.split("/", 3)
                    if len(parts) >= 4:
                        return parts[3]  # Return path after bucket name
                    # If split didn't work as expected, try removing gs:// and bucket name
                    if "/" in path[5:]:  # After "gs://"
                        return path.split("/", 3)[-1] if len(path.split("/")) > 3 else path
                    return path
                # If it's already just a path, return as-is
                return path

            # Shared merge helper so we can reuse for ALL and COMPANY scopes
            def merge_bucket_and_db(
                bucket_documents,
                db_documents,
            ):
                # Create a map of normalized path -> StoredDocument for quick lookup
                bucket_docs_map = {}
                for bucket_doc in bucket_documents:
                    normalized_path = normalize_path(bucket_doc.bucket_path)
                    bucket_docs_map[normalized_path] = bucket_doc

                merged_documents = []
                seen_paths = set()

                # First, add all database documents (they have richer metadata)
                for db_doc in db_documents:
                    normalized_path = normalize_path(db_doc.bucket_path)
                    if normalized_path not in seen_paths:
                        # Verify document exists in bucket
                        if storage_service.document_exists(db_doc.bucket_path):
                            merged_documents.append(db_doc)
                            seen_paths.add(normalized_path)

                # Then, add bucket documents that aren't in database
                for normalized_path, bucket_doc in bucket_docs_map.items():
                    if normalized_path not in seen_paths:
                        # Create a Document-like object from bucket document
                        merged_documents.append(
                            {
                                "id": bucket_doc.id,  # This is the path from StoredDocument
                                "filename": bucket_doc.filename,
                                "file_type": bucket_doc.file_type,
                                "file_size": bucket_doc.file_size,
                                "bucket_path": bucket_doc.bucket_path,
                                "user_id": bucket_doc.user_id,
                                "is_company_doc": bucket_doc.is_company_doc,
                                "uploaded_at": bucket_doc.uploaded_at,
                                "category": None,  # Bucket documents don't have category
                            }
                        )
                        seen_paths.add(normalized_path)

                return merged_documents

            # Load DB docs for ALL scope (user + company)
            db_query = db.query(Document).filter(
                (Document.user_id == user_id) | (Document.is_company_doc == True)
            )
            db_docs = db_query.all()

            merged_documents = merge_bucket_and_db(bucket_docs, db_docs)

            logger.info(
                f"Total merged documents for ALL: {len(merged_documents)} (DB: {len(db_docs)}, Bucket: {len(bucket_docs)})"
            )

            # Sort by uploaded_at (newest first)
            def get_sort_key(doc):
                if isinstance(doc, Document):
                    return doc.uploaded_at.isoformat() if doc.uploaded_at else ""
                else:
                    return doc["uploaded_at"] if isinstance(doc["uploaded_at"], str) else ""

            merged_documents.sort(key=get_sort_key, reverse=True)

            # Apply pagination
            total_count = len(merged_documents)
            paginated_docs = merged_documents[offset : offset + limit]

            # Convert to response model
            documents = []
            for doc in paginated_docs:
                if isinstance(doc, Document):
                    # Database document
                    documents.append(
                        DocumentModel(
                            id=doc.id,
                            filename=doc.filename,
                            file_type=doc.file_type,
                            file_size=doc.file_size,
                            bucket_path=doc.bucket_path,
                            user_id=doc.user_id,
                            is_company_doc=doc.is_company_doc,
                            uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else "",
                            category=getattr(doc, "category", None),
                        )
                    )
                else:
                    # Bucket document (dict)
                    documents.append(
                        DocumentModel(
                            id=doc["id"],
                            filename=doc["filename"],
                            file_type=doc["file_type"],
                            file_size=doc["file_size"],
                            bucket_path=doc["bucket_path"],
                            user_id=doc["user_id"],
                            is_company_doc=doc["is_company_doc"],
                            uploaded_at=doc["uploaded_at"],
                            category=doc.get("category"),
                        )
                    )

            return DocumentListResponse(
                documents=documents,
                total=total_count,
            )

        # When scope is COMPANY, retrieve only company docs from company folder
        if scope_upper == "COMPANY" and storage_service:
            # List only company documents from bucket (documents/company/)
            bucket_docs = storage_service.list_documents_by_scope(user_id, "COMPANY", is_admin)
            logger.info(
                f"Retrieved {len(bucket_docs)} company documents from bucket for scope COMPANY"
            )

            # Helper function to normalize bucket_path for comparison (reuse from ALL)
            def normalize_path_company(path: str) -> str:
                if not path:
                    return ""
                if path.startswith("gs://"):
                    parts = path.split("/", 3)
                    if len(parts) >= 4:
                        return parts[3]
                    if "/" in path[5:]:
                        return path.split("/", 3)[-1] if len(path.split("/")) > 3 else path
                    return path
                return path

            # Map bucket docs by normalized path
            bucket_docs_map = {}
            for bucket_doc in bucket_docs:
                normalized_path = normalize_path_company(bucket_doc.bucket_path)
                bucket_docs_map[normalized_path] = bucket_doc

            # Load only company documents from DB
            db_docs = db.query(Document).filter(Document.is_company_doc == True).all()

            merged_documents = []
            seen_paths = set()

            # Add DB company docs first
            for db_doc in db_docs:
                normalized_path = normalize_path_company(db_doc.bucket_path)
                if normalized_path not in seen_paths:
                    if storage_service.document_exists(db_doc.bucket_path):
                        merged_documents.append(db_doc)
                        seen_paths.add(normalized_path)

            # Add bucket-only company docs
            for normalized_path, bucket_doc in bucket_docs_map.items():
                if normalized_path not in seen_paths:
                    merged_documents.append(
                        {
                            "id": bucket_doc.id,
                            "filename": bucket_doc.filename,
                            "file_type": bucket_doc.file_type,
                            "file_size": bucket_doc.file_size,
                            "bucket_path": bucket_doc.bucket_path,
                            "user_id": bucket_doc.user_id,
                            "is_company_doc": bucket_doc.is_company_doc,
                            "uploaded_at": bucket_doc.uploaded_at,
                            "category": None,
                        }
                    )
                    seen_paths.add(normalized_path)

            logger.info(
                f"Total merged company documents: {len(merged_documents)} (DB: {len(db_docs)}, Bucket: {len(bucket_docs)})"
            )

            # Sort and paginate (same as ALL)
            def get_sort_key_company(doc):
                if isinstance(doc, Document):
                    return doc.uploaded_at.isoformat() if doc.uploaded_at else ""
                else:
                    return doc["uploaded_at"] if isinstance(doc["uploaded_at"], str) else ""

            merged_documents.sort(key=get_sort_key_company, reverse=True)

            total_count = len(merged_documents)
            paginated_docs = merged_documents[offset : offset + limit]

            documents = []
            for doc in paginated_docs:
                if isinstance(doc, Document):
                    documents.append(
                        DocumentModel(
                            id=doc.id,
                            filename=doc.filename,
                            file_type=doc.file_type,
                            file_size=doc.file_size,
                            bucket_path=doc.bucket_path,
                            user_id=doc.user_id,
                            is_company_doc=doc.is_company_doc,
                            uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else "",
                            category=getattr(doc, "category", None),
                        )
                    )
                else:
                    documents.append(
                        DocumentModel(
                            id=doc["id"],
                            filename=doc["filename"],
                            file_type=doc["file_type"],
                            file_size=doc["file_size"],
                            bucket_path=doc["bucket_path"],
                            user_id=doc["user_id"],
                            is_company_doc=doc["is_company_doc"],
                            uploaded_at=doc["uploaded_at"],
                            category=doc.get("category"),
                        )
                    )

            return DocumentListResponse(
                documents=documents,
                total=total_count,
            )

        # For MY and COMPANY scopes (when storage_service is unavailable), use database-only approach
        # Build query based on scope
        query = db.query(Document)
        
        if scope_upper == "MY":
            # Only user's personal documents
            query = query.filter(Document.user_id == user_id, Document.is_company_doc == False)
        elif scope_upper == "COMPANY":
            # Only company documents
            query = query.filter(Document.is_company_doc == True)
        else:  # ALL (fallback if storage_service is None)
            # User's documents OR company documents
            query = query.filter(
                (Document.user_id == user_id) | (Document.is_company_doc == True)
            )
        
        # Get total count before applying limit
        total_count = query.count()
        
        # Order by upload date (newest first)
        query = query.order_by(Document.uploaded_at.desc())
        
        # Apply offset and limit
        db_docs = query.offset(offset).limit(limit).all()
        
        # Filter out documents that don't exist in GCS (real-time sync)
        # This ensures the list reflects the actual state of documents in storage
        valid_documents = []
        for doc in db_docs:
            if storage_service:
                try:
                    if storage_service.document_exists(doc.bucket_path):
                        valid_documents.append(doc)
                    else:
                        # Document doesn't exist in GCS - log and skip it
                        logger.warning(f"Document {doc.id} ({doc.filename}) not found in GCS, excluding from list")
                except Exception as exc:
                    # If check fails, include the document to avoid false negatives
                    logger.warning(f"Error checking document existence for {doc.id}: {exc}")
                    valid_documents.append(doc)
            else:
                # If storage service not available, include all documents
                valid_documents.append(doc)
        
        # Convert to response model
        documents = [
            DocumentModel(
                id=doc.id,
                filename=doc.filename,
                file_type=doc.file_type,
                file_size=doc.file_size,
                bucket_path=doc.bucket_path,
                user_id=doc.user_id,
                is_company_doc=doc.is_company_doc,
                uploaded_at=doc.uploaded_at.isoformat() if doc.uploaded_at else "",
                category=getattr(doc, "category", None),
            )
            for doc in valid_documents
        ]
        
        # Adjust total count to reflect filtered documents
        # Note: This is an approximation since we only check documents in current page
        # For exact count, we'd need to check all documents, which could be slow
        adjusted_total = total_count - (len(db_docs) - len(valid_documents))
        
        return DocumentListResponse(
            documents=documents,
            total=max(0, adjusted_total),  # Ensure total is not negative
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing documents: {exc}",
        )


@router.post("/documents", response_model=DocumentModel)
async def upload_document(
    file: UploadFile = File(...),
    category: str = Form(..., description="Predefined category label"),
    custom_category: Optional[str] = Form(
        None, description="Optional custom category when 'Other' is selected"
    ),
    is_company_doc: str = Form("false"),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Upload a document to Google Cloud Storage and save metadata to database.

    - Uses userId from verified token (Google OAuth user ID) as the owner identifier.
    - The same user_id is used consistently when user logs in again.
    - Document metadata (filename, user_id, category, etc.) is stored in SQLite database.
    - If is_company_doc is True, only admins are allowed to upload.
    - Category is normalized from the predefined dropdown plus optional custom category.
    """
    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized. Please check GCS configuration.",
        )

    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))
    
    # Normalize category
    normalized_category = (category or "").strip()
    if normalized_category.lower() == "other" and custom_category:
        normalized_category = custom_category.strip()

    if not normalized_category:
        raise HTTPException(
            status_code=400,
            detail="Category is required.",
        )

    # Convert string form field to boolean
    is_company_doc_bool = is_company_doc.lower() in ("true", "1", "yes")

    if is_company_doc_bool and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only admin users can upload company documents.",
        )
    
    # Validate file
    if not file.filename:
        raise HTTPException(status_code=400, detail="Filename is required.")
    
    # Validate file extension
    allowed_extensions = [ext.strip().lower() for ext in settings.allowed_file_extensions.split(",")]
    file_ext = os.path.splitext(file.filename)[1].lower()
    
    if file_ext not in allowed_extensions:
        raise HTTPException(
            status_code=400,
            detail=f"File type not allowed. Allowed types: {', '.join(allowed_extensions)}"
        )
    
    try:
        contents = await file.read()

        # Validate file size (max 10 MB)
        max_size_bytes = settings.max_file_size_mb * 1024 * 1024  # Convert MB to bytes
        if len(contents) > max_size_bytes:
            raise HTTPException(
                status_code=400,
                detail=f"File size exceeds maximum allowed size of {settings.max_file_size_mb} MB."
            )
        
        if not contents:
            raise HTTPException(status_code=400, detail="Uploaded file is empty.")

        stored = storage_service.upload_document(
            file_bytes=contents,
            filename=file.filename,
            user_id=user_id,
            is_company_doc=is_company_doc_bool,
        )

        # Save or update document metadata in database.
        # We enforce UNIQUE(bucket_path), so if a document with the same
        # bucket_path already exists we update that record instead of inserting
        # a new one. This allows users to re‑upload/replace a document without
        # violating the unique constraint while keeping the canonical flat
        # storage path users/{user_id}/{filename}.
        existing = (
            db.query(Document)
            .filter(Document.bucket_path == stored.bucket_path)
            .first()
        )

        if existing:
            # Update existing metadata row
            existing.filename = file.filename
            existing.file_type = stored.file_type
            existing.file_size = stored.file_size
            existing.user_id = user_id
            existing.is_company_doc = is_company_doc_bool
            existing.category = normalized_category

            db_document = existing
        else:
            # Create new metadata row
            db_document = Document(
                filename=file.filename,  # Original filename from user
                file_type=stored.file_type,
                file_size=stored.file_size,
                bucket_path=stored.bucket_path,
                user_id=user_id,  # Google OAuth user ID - consistent across sessions
                is_company_doc=is_company_doc_bool,
                category=normalized_category,
            )
            db.add(db_document)
        
        db.commit()
        db.refresh(db_document)

        # Return response with database ID
        response = DocumentModel(
            id=db_document.id,
            filename=db_document.filename,
            file_type=db_document.file_type,
            file_size=db_document.file_size,
            bucket_path=db_document.bucket_path,
            user_id=db_document.user_id,
            is_company_doc=db_document.is_company_doc,
            uploaded_at=db_document.uploaded_at.isoformat() if db_document.uploaded_at else "",
            category=db_document.category,
        )

        return response
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error uploading document to storage: {exc}",
        )


@router.delete("/documents/{document_id}", response_model=dict)
async def delete_document(
    document_id: str,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Delete a document from both Google Cloud Storage and database.
    
    - Users can only delete their own documents (unless admin deleting company docs)
    - Company documents can only be deleted by admins
    """
    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized. Please check GCS configuration.",
        )

    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))

    try:
        # Get document from database
        db_document = db.query(Document).filter(Document.id == document_id).first()
        
        if not db_document:
            raise HTTPException(
                status_code=404,
                detail="Document not found.",
            )
        
        # Check permissions
        if db_document.is_company_doc and not is_admin:
            raise HTTPException(
                status_code=403,
                detail="Only admin users can delete company documents.",
            )
        
        if not db_document.is_company_doc and db_document.user_id != user_id:
            raise HTTPException(
                status_code=403,
                detail="You can only delete your own documents.",
            )
        
        # Delete from Google Cloud Storage using storage_service
        # This uses the same credentials and bucket configuration as upload
        # If document doesn't exist in GCS (e.g., deleted manually), still proceed with DB deletion
        try:
            deleted_from_gcs = storage_service.delete_document(db_document.bucket_path)
            if deleted_from_gcs:
                logger.info(f"Successfully deleted document from GCS: {db_document.bucket_path}")
            else:
                logger.warning(f"Document not found in GCS (may have been deleted manually), proceeding with DB deletion: {db_document.bucket_path}")
        except Exception as exc:
            # For non-404 errors, log but still proceed with DB deletion
            # This ensures database stays in sync even if GCS operations fail
            logger.warning(f"Error deleting blob from GCS {db_document.bucket_path}: {exc}. Proceeding with DB deletion.")
        
        # Delete from database (always do this, even if GCS deletion failed or document doesn't exist)
        db.delete(db_document)
        db.commit()
        
        return {
            "message": "Document deleted successfully",
            "document_id": document_id,
        }
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error deleting document: {exc}",
        )


@router.post("/documents/create", response_model=DocumentModel)
async def create_document(
    payload: CreateDocumentRequest,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Create a text/markdown document in-app and persist both content and metadata.

    - Accepts title, category/custom_category, content, and optional is_company_doc.
    - Normalizes category in the same way as upload.
    - Stores content in GCS using the same structured key convention as uploads.
    - Persists Document metadata so the item appears in the documents list.
    """
    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized. Please check GCS configuration.",
        )

    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))

    # Validate required fields
    title = (payload.title or "").strip()
    if not title:
        raise HTTPException(status_code=400, detail="Title is required.")

    content = (payload.content or "").strip()
    if not content:
        raise HTTPException(status_code=400, detail="Content is required.")

    # Normalize category (same rules as upload)
    normalized_category = (payload.category or "").strip()
    if normalized_category.lower() == "other" and payload.custom_category:
        normalized_category = payload.custom_category.strip()

    if not normalized_category:
        raise HTTPException(
            status_code=400,
            detail="Category is required.",
        )

    is_company_doc_bool = bool(payload.is_company_doc)
    if is_company_doc_bool and not is_admin:
        raise HTTPException(
            status_code=403,
            detail="Only admin users can create company documents.",
        )

    # Enforce size limit using configured max_file_size_mb
    content_bytes = content.encode("utf-8")
    max_size_bytes = settings.max_file_size_mb * 1024 * 1024
    if len(content_bytes) > max_size_bytes:
        raise HTTPException(
            status_code=400,
            detail=f"Content size exceeds maximum allowed size of {settings.max_file_size_mb} MB.",
        )

    # Generate a reasonable filename from title (used as display name as well)
    safe_title = "".join(ch if ch.isalnum() or ch in (" ", "-", "_") else "_" for ch in title)
    safe_title = "_".join(safe_title.split())  # collapse whitespace to underscores
    if not safe_title:
        safe_title = "document"
    # Store created documents as plain text files so they are always saved with
    # a .txt extension instead of .md.
    filename = f"{safe_title}.txt"

    try:
        stored = storage_service.upload_document(
            file_bytes=content_bytes,
            filename=filename,
            user_id=user_id,
            is_company_doc=is_company_doc_bool,
        )

        db_document = Document(
            filename=filename,
            file_type=stored.file_type,
            file_size=stored.file_size,
            bucket_path=stored.bucket_path,
            user_id=user_id,
            is_company_doc=is_company_doc_bool,
            category=normalized_category,
        )

        db.add(db_document)
        db.commit()
        db.refresh(db_document)

        return DocumentModel(
            id=db_document.id,
            filename=db_document.filename,
            file_type=db_document.file_type,
            file_size=db_document.file_size,
            bucket_path=db_document.bucket_path,
            user_id=db_document.user_id,
            is_company_doc=db_document.is_company_doc,
            uploaded_at=db_document.uploaded_at.isoformat() if db_document.uploaded_at else "",
            category=db_document.category,
        )
    except HTTPException:
        raise
    except Exception as exc:
        db.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error creating document: {exc}",
        )


@router.get("/documents/{document_id}/status")
async def check_document_status(
    document_id: str,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Check if a document is available in both bucket and database.
    
    Returns:
        {
            "available": bool,
            "exists_in_storage": bool,
            "exists_in_db": bool
        }
    """
    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized.",
        )

    user_id = token.get("userId") or token.get("email")
    
    try:
        # Check database
        db_document = db.query(Document).filter(Document.id == document_id).first()
        exists_in_db = db_document is not None
        
        # Check storage if document exists in DB
        exists_in_storage = False
        if exists_in_db:
            try:
                exists_in_storage = storage_service.document_exists(db_document.bucket_path)
            except Exception as exc:
                logger.warning(f"Error checking storage for document {document_id}: {exc}")
                exists_in_storage = False
        
        # Document is available only if it exists in both
        available = exists_in_db and exists_in_storage
        
        return {
            "available": available,
            "exists_in_storage": exists_in_storage,
            "exists_in_db": exists_in_db,
        }
    except Exception as exc:
        logger.error(f"Error checking document status for {document_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error checking document status: {exc}",
        )


@router.get("/documents/{document_id:path}/view-url", response_model=ViewUrlResponse)
async def get_document_view_url(
    document_id: str,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Get a signed URL for viewing a document from Google Cloud Storage.
    
    - Allows all authenticated users to access any document
    - Generates a time-limited signed URL from GCS
    - Returns the signed URL with expiration time
    - Handles both database documents and bucket-only documents
    """
    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized. Please check GCS configuration.",
        )

    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))

    try:
        # Try to get document from database first
        db_document = db.query(Document).filter(Document.id == document_id).first()
        bucket_path = None
        is_company_doc = False
        doc_user_id = None
        
        if db_document:
            # Document exists in database
            bucket_path = db_document.bucket_path
            is_company_doc = db_document.is_company_doc
            doc_user_id = db_document.user_id
            logger.info(f"Found document in database: id={document_id}, bucket_path={bucket_path}")
        else:
            # Document might only exist in bucket (bucket-only document)
            # The document_id from bucket documents can be:
            # 1. The path (from _blob_to_document: blob.name) - e.g., "users/user123/doc456/file.pdf"
            # 2. The full bucket_path (from DocumentModel) - e.g., "gs://bucket-name/users/user123/doc456/file.pdf"
            # Construct the full bucket_path
            if document_id.startswith("gs://"):
                bucket_path = document_id
                # Extract gcs_path from bucket_path - use split to be more robust
                if f"gs://{settings.gcs_bucket_name}/" in bucket_path:
                    gcs_path = bucket_path.split(f"gs://{settings.gcs_bucket_name}/", 1)[1]
                else:
                    # Try to extract path after gs://bucket-name/
                    parts = bucket_path.split("/", 3)
                    gcs_path = parts[3] if len(parts) > 3 else bucket_path
            else:
                # document_id is the path relative to bucket root (blob.name format)
                gcs_path = document_id
                bucket_path = f"gs://{settings.gcs_bucket_name}/{gcs_path}"
            
            logger.info(f"Looking up bucket-only document: document_id={document_id}, gcs_path={gcs_path}, bucket_path={bucket_path}")
            
            # Check if document exists in bucket - try both formats
            exists = storage_service.document_exists(bucket_path)
            if not exists:
                # Try with just the gcs_path
                logger.info(
                    f"Document not found with bucket_path, trying gcs_path directly: {gcs_path}"
                )
                exists = storage_service.document_exists(gcs_path)
                if exists:
                    # Update bucket_path to use the format that works
                    bucket_path = f"gs://{settings.gcs_bucket_name}/{gcs_path}"

            if not exists:
                logger.warning(
                    f"Document not found in bucket: document_id={document_id}, gcs_path={gcs_path}, bucket_path={bucket_path}"
                )
                raise HTTPException(
                    status_code=404,
                    detail=f"Document not found in storage: {gcs_path}",
                )

            # Determine if it's a company doc based on path
            # Treat both "documents/company/" and "company/" as company documents
            is_company_doc = gcs_path.startswith("documents/company/") or gcs_path.startswith("company/")
            
            # Extract user_id from path if it's a user document
            if gcs_path.startswith("users/"):
                parts = gcs_path.split("/")
                if len(parts) > 1:
                    doc_user_id = parts[1]
        
        # Allow all authenticated users to access any document
        # All documents in the bucket are accessible to any authenticated user
        has_access = True
        
        # Generate signed URL (expires in 1 hour)
        expiration_seconds = 3600
        signed_url = storage_service.get_signed_url(
            bucket_path,
            expiration_seconds=expiration_seconds
        )
        
        return ViewUrlResponse(
            url=signed_url,
            expires_in=expiration_seconds
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.error(f"Error generating view URL for document {document_id}: {exc}")
        raise HTTPException(
            status_code=500,
            detail=f"Error generating view URL: {exc}",
        )


