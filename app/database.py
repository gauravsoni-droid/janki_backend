"""
Database configuration and session management using SQLAlchemy.
"""
from sqlalchemy import create_engine, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool
import os

# Database URL - SQLite for development
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./janki.db")

# Create engine with SQLite-specific configuration
if DATABASE_URL.startswith("sqlite"):
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
        echo=False  # Set to True for SQL query logging
    )
else:
    engine = create_engine(DATABASE_URL)

# Create session factory
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Base class for models
Base = declarative_base()


def get_db():
    """
    Dependency function to get database session.
    Use this in FastAPI route dependencies.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """
    Initialize database by creating all tables and running safe, idempotent
    schema migrations.

    Currently this will:
    - Ensure the `documents` table exists
    - Add the `category` column to `documents` if it is missing (for
      databases created before this field was added).
    """
    # Create any missing tables first
    Base.metadata.create_all(bind=engine)

    # Lightweight migrations for SQLite
    if DATABASE_URL.startswith("sqlite"):
        with engine.connect() as conn:
            # Ensure `category` column exists on documents
            result = conn.execute(text("PRAGMA table_info(documents);"))
            existing_columns = {row[1] for row in result}  # row[1] = column name

            if "category" not in existing_columns:
                conn.execute(
                    text("ALTER TABLE documents ADD COLUMN category VARCHAR;")
                )
                conn.commit()

            # Ensure new columns exist on chat_sessions table for sessionized chat
            result = conn.execute(text("PRAGMA table_info(chat_sessions);"))
            chat_session_columns = {row[1] for row in result}

            if chat_session_columns:
                # Table already exists, backfill any missing columns.
                if "knowledge_scope" not in chat_session_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_sessions "
                            "ADD COLUMN knowledge_scope VARCHAR DEFAULT 'ALL';"
                        )
                    )
                if "created_at" not in chat_session_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_sessions "
                            "ADD COLUMN created_at DATETIME;"
                        )
                    )
                if "updated_at" not in chat_session_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_sessions "
                            'ADD COLUMN updated_at DATETIME;'
                        )
                    )
                if "is_pinned" not in chat_session_columns:
                    conn.execute(
                        text(
                            "ALTER TABLE chat_sessions "
                            "ADD COLUMN is_pinned BOOLEAN DEFAULT 0;"
                        )
                    )
                conn.commit()
