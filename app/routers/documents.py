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


class DocumentListResponse(BaseModel):
    """Response model for a list of documents."""

    documents: List[DocumentModel]
    total: int


@router.get("/documents", response_model=DocumentListResponse)
async def list_documents(
    scope: Optional[str] = Query("ALL", description="MY | COMPANY | ALL"),
    limit: int = Query(100, ge=1, le=500),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    List documents from database based on knowledge scope.
    
    Documents are retrieved from SQLite database using user_id from Google OAuth token.
    The same user_id is used consistently across sessions.

    - scope=MY: only documents uploaded by the current user
    - scope=COMPANY: only company-wide documents (is_company_doc=True)
    - scope=ALL: both personal and company documents
    """
    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))
    scope_upper = (scope or "ALL").upper()

    try:
        # Build query based on scope
        query = db.query(Document)
        
        if scope_upper == "MY":
            # Only user's personal documents
            query = query.filter(Document.user_id == user_id, Document.is_company_doc == False)
        elif scope_upper == "COMPANY":
            # Only company documents
            query = query.filter(Document.is_company_doc == True)
        else:  # ALL
            # User's documents OR company documents
            query = query.filter(
                (Document.user_id == user_id) | (Document.is_company_doc == True)
            )
        
        # Order by upload date (newest first)
        query = query.order_by(Document.uploaded_at.desc())
        
        # Apply limit
        db_docs = query.limit(limit).all()
        
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
            )
            for doc in db_docs
        ]
        
        return DocumentListResponse(
            documents=documents,
            total=len(documents),
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Error listing documents from database: {exc}",
        )


@router.post("/documents", response_model=DocumentModel)
async def upload_document(
    file: UploadFile = File(...),
    is_company_doc: str = Form("false"),
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Upload a document to Google Cloud Storage and save metadata to database.

    - Uses userId from verified token (Google OAuth user ID) as the owner identifier.
    - The same user_id is used consistently when user logs in again.
    - Document metadata (filename, user_id, etc.) is stored in SQLite database.
    - If is_company_doc is True, only admins are allowed to upload.
    """
    # #region agent log
    # Debug log: entry into upload_document (hypotheses H1/H2/H3)
    try:
        debug_payload = {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": "H1-H3",
            "location": "documents.py:upload_document:entry",
            "message": "Entered upload_document endpoint",
            "data": {
                "is_company_doc": is_company_doc,
                "token_has_userId": bool(token.get("userId")),
                "token_has_email": bool(token.get("email")),
            },
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
        }
        with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_payload) + "\n")
    except Exception:
        # Best-effort logging; never block the request
        pass
    # #endregion

    if storage_service is None:
        raise HTTPException(
            status_code=500,
            detail="Storage service is not initialized. Please check GCS configuration.",
        )

    user_id = token.get("userId") or token.get("email")
    is_admin = bool(token.get("isAdmin"))
    
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

        # #region agent log
        # Debug log: before calling storage_service.upload_document (hypotheses H2/H3)
        try:
            debug_payload = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H2-H3",
                "location": "documents.py:upload_document:before_storage",
                "message": "About to call storage_service.upload_document",
                "data": {
                    "file_size": len(contents),
                    "file_name": file.filename,
                    "is_company_doc": is_company_doc_bool,
                    "user_id": token.get("userId") or token.get("email"),
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
            with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_payload) + "\n")
        except Exception:
            pass
        # #endregion

        # Upload to Google Cloud Storage
        stored = storage_service.upload_document(
            file_bytes=contents,
            filename=file.filename,
            user_id=user_id,
            is_company_doc=is_company_doc_bool,
        )

        # Save document metadata to database
        # Use original filename (not UUID-prefixed) for display
        db_document = Document(
            filename=file.filename,  # Original filename without UUID prefix
            file_type=stored.file_type,
            file_size=stored.file_size,
            bucket_path=stored.bucket_path,
            user_id=user_id,  # Google OAuth user ID - consistent across sessions
            is_company_doc=is_company_doc_bool,
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
        )

        # #region agent log
        # Debug log: successful upload_document exit (hypotheses H2/H3)
        try:
            debug_payload = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H2-H3",
                "location": "documents.py:upload_document:success",
                "message": "upload_document completed successfully",
                "data": {
                    "document_id": stored.id,
                    "bucket_path": stored.bucket_path,
                    "is_company_doc": stored.is_company_doc,
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
            with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_payload) + "\n")
        except Exception:
            pass
        # #endregion

        return response
    except HTTPException:
        raise
    except Exception as exc:
        # #region agent log
        # Debug log: error path in upload_document (hypotheses H2/H3)
        try:
            debug_payload = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H2-H3",
                "location": "documents.py:upload_document:error",
                "message": "Exception in upload_document",
                "data": {
                    "error": str(exc),
                    "exception_type": exc.__class__.__name__,
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
            with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_payload) + "\n")
        except Exception:
            pass
        # #endregion
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
        try:
            storage_service.delete_document(db_document.bucket_path)
            logger.info(f"Successfully deleted document from GCS: {db_document.bucket_path}")
        except Exception as exc:
            logger.error(f"Error deleting blob from GCS {db_document.bucket_path}: {exc}")
            # Raise error to inform user - don't silently fail
            raise HTTPException(
                status_code=500,
                detail=f"Failed to delete document from storage: {exc}. Document may still exist in Google Cloud Storage.",
            )
        
        # Delete from database
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


