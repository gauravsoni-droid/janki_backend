"""
Chat session model for grouping chat messages into immutable sessions.
"""
from sqlalchemy import Column, String, DateTime, Boolean
from sqlalchemy.sql import func
from app.database import Base
import uuid


class ChatSession(Base):
    """
    Chat session representing a single ChatGPT-style conversation.

    - Each session is identified by a UUID string `id`
    - Sessions are per-user (`user_id`)
    - `title` is derived from the first user message (trimmed, max 80 chars)
    - `knowledge_scope` captures the scope used for this conversation
    - `scope` column is kept for backward compatibility with earlier schemas
    """

    __tablename__ = "chat_sessions"

    id = Column(String, primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String, nullable=False, index=True)
    title = Column(String(255), nullable=False, default="")
    # New canonical scope field for sessions
    knowledge_scope = Column(String, nullable=False, default="ALL")
    # Legacy column present in existing SQLite databases. We keep it mapped and
    # always mirror `knowledge_scope` into it to satisfy NOT NULL constraints.
    scope = Column(String, nullable=False, default="ALL")
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    # Whether this chat is pinned to the top of the sidebar for the user.
    is_pinned = Column(Boolean, nullable=False, default=False)

    def __repr__(self):
        return f"<ChatSession(id={self.id}, user_id={self.user_id}, title={self.title!r})>"


