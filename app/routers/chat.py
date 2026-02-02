"""
Chat API endpoints.
"""
from fastapi import APIRouter, HTTPException, Depends, Header
from typing import Optional
from pydantic import BaseModel
from app.services.vertex_service import vertex_service as google_agent_service
from jose import jwt, JWTError
from app.config import settings


router = APIRouter()


class ChatRequest(BaseModel):
    """Chat message request model."""
    message: str
    conversation_id: Optional[str] = None
    scope: Optional[str] = "ALL"


class ChatResponse(BaseModel):
    """Chat response model."""
    response: str
    conversation_id: str
    message_id: str
    sources: list = []


async def verify_token(authorization: Optional[str] = Header(None)):
    """Verify backend JWT token (from /api/v1/auth/verify)."""
    import logging
    import json
    from datetime import datetime
    logger = logging.getLogger(__name__)
    
    # #region agent log
    try:
        debug_payload = {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": "H5",
            "location": "chat.py:verify_token:entry",
            "message": "verify_token called",
            "data": {
                "has_authorization": bool(authorization),
                "auth_header_length": len(authorization) if authorization else 0,
                "auth_starts_with_bearer": authorization.startswith("Bearer ") if authorization else False,
            },
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
        }
        with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_payload) + "\n")
    except Exception:
        pass
    # #endregion
    
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
        
        logger.info(f"Token verified successfully for user: {payload.get('email') or payload.get('userId')}")
        
        # #region agent log
        try:
            debug_payload = {
                "sessionId": "debug-session",
                "runId": "pre-fix",
                "hypothesisId": "H5",
                "location": "chat.py:verify_token:success",
                "message": "Token verified successfully",
                "data": {
                    "has_userId": bool(payload.get("userId")),
                    "has_email": bool(payload.get("email")),
                },
                "timestamp": int(datetime.utcnow().timestamp() * 1000),
            }
            with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
                f.write(json.dumps(debug_payload) + "\n")
        except Exception:
            pass
        # #endregion
        
        return payload
    except jwt.ExpiredSignatureError:
        logger.warning("Token expired")
        raise HTTPException(status_code=401, detail="Token expired")
    except JWTError as e:
        logger.warning(f"Token verification failed: {str(e)}")
        raise HTTPException(status_code=401, detail=f"Invalid token: {str(e)}")


@router.post("/chat", response_model=ChatResponse)
async def send_chat_message(
    request: ChatRequest,
    token: dict = Depends(verify_token)
):
    """
    Send a chat message to the Google Agent Builder agent.
    
    Args:
        request: Chat request with message and conversation ID
        token: Verified JWT token from NextAuth
        
    Returns:
        Chat response from Google Agent Builder
    """
    try:
        user_id = token.get("userId") or token.get("email")
        
        # Send message to Google Agent Builder
        result = await google_agent_service.send_message(
            message=request.message,
            conversation_id=request.conversation_id,
            user_id=user_id
        )
        
        return ChatResponse(
            response=result["response"],
            conversation_id=result["conversation_id"],
            message_id=f"msg_{hash(result['conversation_id'] + request.message)}",
            sources=result.get("sources", [])
        )
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error processing chat message: {str(e)}"
        )

