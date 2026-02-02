"""
Document model for storing document metadata in SQLite database.
"""
from sqlalchemy import Column, String, Integer, Boolean, DateTime, Text
from sqlalchemy.sql import func
from app.database import Base
import uuid


class Document(Base):
    """
    Document model storing metadata for uploaded documents.
    
    Documents are stored in Google Cloud Storage, but metadata is stored here
    for quick retrieval and querying by user_id.
    """
    __tablename__ = "documents"

    # Primary key - using UUID as string
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # Document filename (original name from user)
    filename = Column(String, nullable=False, index=True)
    
    # File metadata
    file_type = Column(String, nullable=False)  # e.g., "application/pdf"
    file_size = Column(Integer, nullable=False)  # Size in bytes
    
    # Storage location
    bucket_path = Column(String, nullable=False, unique=True, index=True)  # Full GCS path
    
    # User association - Google user ID (sub from OAuth token)
    user_id = Column(String, nullable=False, index=True)
    
    # Document scope
    is_company_doc = Column(Boolean, default=False, nullable=False)
    
    # Timestamps
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)

    def __repr__(self):
        return f"<Document(id={self.id}, filename={self.filename}, user_id={self.user_id})>"

