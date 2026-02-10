"""
Chat message model for storing chat history in SQLite database.
"""
from sqlalchemy import Column, String, DateTime, Text, JSON
from sqlalchemy.sql import func
from app.database import Base
import uuid


class ChatMessage(Base):
    """
    Chat message model storing user and assistant messages.
    
    Messages are stored with scope context and source document references.
    """
    __tablename__ = "chat_messages"

    # Primary key - using UUID as string
    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    
    # User association - Google user ID (sub from OAuth token)
    user_id = Column(String, nullable=False, index=True)
    
    # Company association (optional, for future use)
    company_id = Column(String, nullable=True, index=True)
    
    # Conversation grouping (optional session ID)
    session_id = Column(String, nullable=True, index=True)
    
    # Message role: "user" or "assistant"
    role = Column(String, nullable=False, index=True)  # "user" | "assistant"
    
    # Message content (text/markdown for assistant)
    content = Column(Text, nullable=False)
    
    # Knowledge scope used for this message
    scope = Column(String, nullable=False)  # "MY" | "COMPANY" | "ALL"
    
    # Source documents (JSON array) - only for assistant messages
    sources = Column(JSON, nullable=True)  # [{"document_id": "...", "title": "...", "author": "..."}]
    
    # Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    def __repr__(self):
        return f"<ChatMessage(id={self.id}, user_id={self.user_id}, role={self.role}, scope={self.scope})>"

