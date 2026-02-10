"""
Chat API endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional, List
from pydantic import BaseModel
from sqlalchemy.orm import Session
from sqlalchemy import desc
from app.services.vertex_service import vertex_service as google_agent_service
from app.database import get_db
from app.models.document import Document
from app.models.chat_message import ChatMessage
from app.models.chat_session import ChatSession
from jose import jwt, JWTError
from app.config import settings
import logging
import json
import time

logger = logging.getLogger(__name__)

router = APIRouter()


class DocumentSource(BaseModel):
    """Source document reference."""
    document_id: str
    title: str
    author: Optional[str] = None


class ChatRequest(BaseModel):
    """Chat message request model."""
    message: str
    conversation_id: Optional[str] = None
    scope: str = "ALL"  # "MY" | "COMPANY" | "ALL"


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    conversation_id: str
    message_id: str
    sources: List[DocumentSource] = []


class ConversationSummary(BaseModel):
    """Lightweight conversation summary for sidebar listing."""

    id: str
    user_id: str
    title: str
    knowledge_scope: str
    created_at: str
    updated_at: str
    message_preview: Optional[str] = None
    is_pinned: bool = False


class ConversationListResponse(BaseModel):
    conversations: List[ConversationSummary]
    total: int


class ChatMessageOut(BaseModel):
    """Chat message payload returned to frontend."""

    id: str
    conversation_id: str
    role: str
    content: str
    created_at: str
    sources: Optional[list] = None


async def verify_token(authorization: Optional[str] = Header(None)):
    """Verify backend JWT token (from /api/v1/auth/verify)."""
    logger = logging.getLogger(__name__)
    
    if not authorization:
        logger.warning("Authorization header missing")
        raise HTTPException(status_code=401, detail="Authorization header missing")
    
    try:
        token = authorization.replace("Bearer ", "")
        if not token or token == "Bearer":
            logger.warning("Empty token received")
            raise HTTPException(status_code=401, detail="Token is empty")
        
        # Verify token with NextAuth secret (same secret used to sign backend tokens)
        payload = jwt.decode(token, settings.nextauth_secret, algorithms=["HS256"])
        
        # Check if token has required fields
        if not payload.get("userId") and not payload.get("email"):
            logger.warning(f"Token missing user info: {payload.keys()}")
            raise HTTPException(status_code=401, detail="Invalid token: missing user information")
        logger.info(
            "Token verified successfully for user: %s",
            payload.get("email") or payload.get("userId"),
        )
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


def get_scoped_document_ids(
    db: Session,
    user_id: str,
    scope: str
) -> List[str]:
    """
    Get document IDs based on knowledge scope.
    
    Args:
        db: Database session
        user_id: Current user ID
        scope: Knowledge scope ("MY", "COMPANY", "ALL")
        
    Returns:
        List of document IDs matching the scope
    """
    scope_upper = scope.upper()
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
    
    documents = query.all()

    # region agent log
    try:
        ts_ms = int(time.time() * 1000)
        with open(
            r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log",
            "a",
            encoding="utf-8",
        ) as f:
            f.write(
                json.dumps(
                    {
                        "id": f"log_{ts_ms}_scope_docs",
                        "timestamp": ts_ms,
                        "runId": "pre-fix-1",
                        "hypothesisId": "H1",
                        "location": "backend/app/routers/chat.py:get_scoped_document_ids",
                        "message": "Scoped documents fetched",
                        "data": {
                            "user_id": user_id,
                            "scope": scope_upper,
                            "count": len(documents),
                        },
                    }
                )
                + "\n"
            )
    except Exception:
        # Never block chat flow on debug logging
        pass
    # endregion

    return [doc.id for doc in documents]


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db)
    ):
    """
    Send a chat message to the Google Agent Builder agent with scope-based document filtering.
    
    Args:
        request: Chat request with message, conversation ID, and scope
        token: Verified JWT token from NextAuth
        db: Database session
        
    Returns:
        Chat response from Google Agent Builder with sources
    """
    try:
        user_id = token.get("userId") or token.get("email")
        company_id = token.get("companyId")  # Optional, for future use

        # Validate scope
        scope_upper = request.scope.upper()
        if scope_upper not in ["MY", "COMPANY", "ALL"]:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid scope: {request.scope}. Must be one of: MY, COMPANY, ALL",
            )

        # region agent log
        try:
            ts_ms = int(time.time() * 1000)
            with open(
                r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log",
                "a",
                encoding="utf-8",
            ) as f:
                f.write(
                    json.dumps(
                        {
                            "id": f"log_{ts_ms}_incoming",
                            "timestamp": ts_ms,
                            "runId": "pre-fix-1",
                            "hypothesisId": "H2",
                            "location": "backend/app/routers/chat.py:send_chat_message",
                            "message": "Incoming chat request",
                            "data": {
                                "user_id": user_id,
                                "scope": scope_upper,
                                "has_conversation_id": bool(request.conversation_id),
                            },
                        }
                    )
                    + "\n"
                )
        except Exception:
            pass
        # endregion

        # Resolve or create chat session for this message
        session_id: Optional[str] = request.conversation_id
        session: Optional[ChatSession] = None

        if not session_id:
            # First message of a brand new chat: create session with title from user message
            title = (request.message or "").strip()
            if len(title) > 80:
                title = title[:80]
            if not title:
                title = "New chat"

            session = ChatSession(
                user_id=user_id,
                title=title,
                knowledge_scope=scope_upper,
                scope=scope_upper,
            )
            db.add(session)
            db.flush()  # populate session.id without committing
            session_id = session.id
        else:
            # Ensure session belongs to this user
            session = (
                db.query(ChatSession)
                .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
                .first()
            )
            if not session:
                raise HTTPException(status_code=404, detail="Chat session not found.")

        # Get candidate document IDs based on scope
        candidate_document_ids = get_scoped_document_ids(db, user_id, scope_upper)

        if not candidate_document_ids:
            # region agent log
            try:
                ts_ms = int(time.time() * 1000)
                with open(
                    r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log",
                    "a",
                    encoding="utf-8",
                ) as f:
                    f.write(
                        json.dumps(
                            {
                                "id": f"log_{ts_ms}_no_docs",
                                "timestamp": ts_ms,
                                "runId": "pre-fix-1",
                                "hypothesisId": "H3",
                                "location": "backend/app/routers/chat.py:send_chat_message",
                                "message": "No documents for scope; using empty_message",
                                "data": {
                                    "user_id": user_id,
                                    "scope": scope_upper,
                                    "session_id": session_id,
                                },
                            }
                        )
                        + "\n"
                    )
            except Exception:
                pass
            # endregion
            # No documents available for this scope; respond with helpful message
            empty_message = (
                "You haven't uploaded any documents yet for this knowledge scope. "
                "Upload documents to get personalized answers."
            )
            if scope_upper == "MY":
                empty_message = (
                    "You haven't uploaded any documents yet. "
                    "Upload documents to get personalized answers."
                )
            elif scope_upper == "COMPANY":
                empty_message = "No company documents are available at this time."

            # Persist user and assistant messages under this session
            user_msg = ChatMessage(
                user_id=user_id,
                company_id=company_id,
                session_id=session_id,
                role="user",
                content=request.message,
                scope=scope_upper,
            )
            db.add(user_msg)

            assistant_msg = ChatMessage(
                user_id=user_id,
                company_id=company_id,
                session_id=session_id,
                role="assistant",
                content=empty_message,
                scope=scope_upper,
                sources=[],
            )
            db.add(assistant_msg)
            db.commit()

            return ChatResponse(
                response=empty_message,
                conversation_id=session_id,
                message_id=f"msg_{hash(session_id + request.message)}",
                sources=[],
            )

        # Send message to Google Agent Builder with document context.
        # We use the chat session ID as the external conversation identifier so that
        # each chat session maps 1:1 to an Agent Builder session.
        result = await google_agent_service.send_message(
            message=request.message,
            conversation_id=session_id,
            user_id=user_id,
        )

        # Map document IDs to document metadata for sources
        sources: List[DocumentSource] = []

        # If vertex_service returns sources (list of document IDs), map them
        if result.get("sources") and isinstance(result["sources"], list):
            source_docs = (
                db.query(Document).filter(Document.id.in_(result["sources"])).all()
            )
            sources = [
                DocumentSource(
                    document_id=doc.id,
                    title=doc.filename,
                    author="Company" if doc.is_company_doc else doc.user_id,
                )
                for doc in source_docs
            ]

        # Persist chat messages under the resolved session
        user_msg = ChatMessage(
            user_id=user_id,
            company_id=company_id,
            session_id=session_id,
            role="user",
            content=request.message,
            scope=scope_upper,
        )
        db.add(user_msg)

        assistant_msg = ChatMessage(
            user_id=user_id,
            company_id=company_id,
            session_id=session_id,
            role="assistant",
            content=result["response"],
            scope=scope_upper,
            sources=[
                {
                    "document_id": s.document_id,
                    "title": s.title,
                    "author": s.author,
                }
                for s in sources
            ]
            if sources
            else [],
        )
        db.add(assistant_msg)
        db.commit()

        return ChatResponse(
            response=result["response"],
            conversation_id=session_id,
            message_id=f"msg_{hash(session_id + request.message)}",
            sources=sources,
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing chat message: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, detail=f"Error processing chat message: {str(e)}"
        )


@router.get("/chat/sessions", response_model=ConversationListResponse)
async def list_chat_sessions(
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    List chat sessions for the current user.
    Pinned chats are returned first, then others by created_at DESC.
    """
    user_id = token.get("userId") or token.get("email")

    sessions = (
        db.query(ChatSession)
        .filter(ChatSession.user_id == user_id)
        .order_by(desc(ChatSession.is_pinned), desc(ChatSession.created_at))
        .all()
    )

    # For each session, get the most recent message content as a preview
    summaries: List[ConversationSummary] = []
    for s in sessions:
        last_msg = (
            db.query(ChatMessage)
            .filter(ChatMessage.session_id == s.id)
            .order_by(desc(ChatMessage.created_at))
            .first()
        )
        preview = last_msg.content if last_msg is not None else None

        summaries.append(
            ConversationSummary(
                id=s.id,
                user_id=s.user_id,
                title=s.title,
                knowledge_scope=s.knowledge_scope,
                created_at=s.created_at.isoformat() if s.created_at else "",
                updated_at=s.updated_at.isoformat() if s.updated_at else "",
                message_preview=preview,
                is_pinned=bool(getattr(s, "is_pinned", False)),
            )
        )

    return ConversationListResponse(conversations=summaries, total=len(summaries))


@router.get("/chat/sessions/{session_id}/messages", response_model=List[ChatMessageOut])
async def get_chat_session_messages(
    session_id: str,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Get all messages for a given chat session, in chronological order.
    Sessions are strictly per-user; users cannot access others' sessions.
    """
    user_id = token.get("userId") or token.get("email")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    messages = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session_id)
        .order_by(ChatMessage.created_at.asc())
        .all()
    )

    result: List[ChatMessageOut] = []
    for m in messages:
        role_upper = "USER" if m.role.lower() == "user" else "ASSISTANT"
        result.append(
            ChatMessageOut(
                id=m.id,
                conversation_id=session_id,
                role=role_upper,
                content=m.content,
                created_at=m.created_at.isoformat() if m.created_at else "",
                sources=m.sources or None,
            )
        )

    return result


class ChatSessionUpdateRequest(BaseModel):
    """Update payload for chat session: rename and/or pin/unpin."""

    title: Optional[str] = None
    is_pinned: Optional[bool] = None


@router.patch("/chat/sessions/{session_id}", response_model=ConversationSummary)
async def update_chat_session(
    session_id: str,
    payload: ChatSessionUpdateRequest,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Update a chat session's mutable properties (title, pin state).
    """
    user_id = token.get("userId") or token.get("email")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    if payload.title is not None:
        new_title = payload.title.strip()[:80] or session.title
        session.title = new_title

    if payload.is_pinned is not None:
        session.is_pinned = bool(payload.is_pinned)

    db.add(session)
    db.commit()
    db.refresh(session)

    # Build latest preview
    last_msg = (
        db.query(ChatMessage)
        .filter(ChatMessage.session_id == session.id)
        .order_by(desc(ChatMessage.created_at))
        .first()
    )
    preview = last_msg.content if last_msg is not None else None

    return ConversationSummary(
        id=session.id,
        user_id=session.user_id,
        title=session.title,
        knowledge_scope=session.knowledge_scope,
        created_at=session.created_at.isoformat() if session.created_at else "",
        updated_at=session.updated_at.isoformat() if session.updated_at else "",
        message_preview=preview,
        is_pinned=bool(getattr(session, "is_pinned", False)),
    )


@router.delete("/chat/sessions/{session_id}", response_model=dict)
async def delete_chat_session(
    session_id: str,
    token: dict = Depends(verify_token),
    db: Session = Depends(get_db),
):
    """
    Delete a chat session and all of its messages for the current user.
    """
    user_id = token.get("userId") or token.get("email")

    session = (
        db.query(ChatSession)
        .filter(ChatSession.id == session_id, ChatSession.user_id == user_id)
        .first()
    )
    if not session:
        raise HTTPException(status_code=404, detail="Chat session not found.")

    # Delete messages first, then the session
    db.query(ChatMessage).where(ChatMessage.session_id == session_id).delete()
    db.delete(session)
    db.commit()

    return {"status": "ok", "message": "Chat session deleted"}

