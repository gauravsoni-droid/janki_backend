"""
Authentication API endpoints.
"""
import logging
import asyncio
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from google.auth.transport import requests
from google.oauth2 import id_token
from google.auth.exceptions import GoogleAuthError
from app.config import settings
from jose import jwt
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)


router = APIRouter()


class VerifyRequest(BaseModel):
    """Google token verification request."""
    google_token: str


class VerifyEmailRequest(BaseModel):
    """Alternative verification using email (fallback when id_token not available)."""
    email: str
    user_id: str


class VerifyResponse(BaseModel):
    """Token verification response."""
    token: str
    user: dict


@router.post("/auth/verify", response_model=VerifyResponse)
async def verify_google_token(request: VerifyRequest):
    """
    Verify Google OAuth token and return backend JWT.
    
    Args:
        request: Request with Google ID token
        
    Returns:
        Backend JWT token and user info
    """
    try:
        # Check if OAuth Client ID is configured
        if not settings.google_oauth_client_id:
            logger.error("Google OAuth Client ID not configured")
            raise HTTPException(
                status_code=500,
                detail="Google OAuth Client ID not configured. Please set GOOGLE_OAUTH_CLIENT_ID in environment variables."
            )
        
        logger.info(f"Verifying Google token with client ID: {settings.google_oauth_client_id[:20]}...")
        
        # Verify Google token using OAuth Client ID as audience
        # Handle clock skew by retrying with a small delay if token is "used too early"
        max_retries = 2
        retry_delay = 1.0  # 1 second delay
        idinfo = None
        
        for attempt in range(max_retries + 1):
            try:
                idinfo = id_token.verify_oauth2_token(
                    request.google_token,
                    requests.Request(),
                    settings.google_oauth_client_id  # Use OAuth Client ID, not project ID
                )
                logger.info("Google token verified successfully")
                break  # Success, exit retry loop
            except ValueError as e:
                error_msg = str(e)
                # Check if it's a clock skew issue ("Token used too early")
                if "Token used too early" in error_msg and attempt < max_retries:
                    logger.warning(f"Clock skew detected (attempt {attempt + 1}/{max_retries + 1}): {error_msg}")
                    logger.info(f"Waiting {retry_delay} seconds before retry...")
                    await asyncio.sleep(retry_delay)
                    continue  # Retry
                else:
                    logger.error(f"Google token verification failed (ValueError): {error_msg}")
                    raise HTTPException(
                        status_code=401,
                        detail=f"Invalid Google token: {error_msg}"
                    )
            except GoogleAuthError as e:
                logger.error(f"Google token verification failed (GoogleAuthError): {str(e)}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Google authentication error: {str(e)}"
                )
            except Exception as e:
                logger.error(f"Unexpected error during Google token verification: {type(e).__name__}: {str(e)}")
                raise HTTPException(
                    status_code=401,
                    detail=f"Token verification error: {str(e)}"
                )
        
        if idinfo is None:
            logger.error("Failed to verify token after all retries")
            raise HTTPException(
                status_code=401,
                detail="Failed to verify Google token after retries"
            )
        
        # Extract user info
        user_email = idinfo.get("email")
        user_id = idinfo.get("sub")
        
        logger.info(f"Extracted user info - Email: {user_email}, User ID: {user_id}")
        
        if not user_email:
            logger.warning("Email not found in token")
            raise HTTPException(status_code=400, detail="Email not found in token")
        
        # Check email domain (optional - you can remove this if not needed)
        allowed_domain = "@cloudusinfotech.com"
        if not user_email.endswith(allowed_domain):
            logger.warning(f"Email domain not allowed: {user_email}")
            raise HTTPException(
                status_code=403,
                detail=f"Email domain not allowed. Must be {allowed_domain}"
            )
        
        # Create backend JWT token
        try:
            payload = {
                "userId": user_id,
                "email": user_email,
                "isAdmin": False,  # You can implement admin logic here
                "exp": datetime.utcnow() + timedelta(days=1)
            }
            
            backend_token = jwt.encode(payload, settings.nextauth_secret, algorithm="HS256")
            logger.info(f"Backend JWT token created successfully for user: {user_email}")
        except Exception as e:
            logger.error(f"Error creating backend JWT token: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Error creating backend token: {str(e)}"
            )
        
        return VerifyResponse(
            token=backend_token,
            user={
                "id": user_id,
                "email": user_email,
                "is_admin": False
            }
        )
        
    except HTTPException:
        # Re-raise HTTPExceptions as-is
        raise
    except Exception as e:
        # Catch any other unexpected errors
        logger.exception(f"Unexpected error in verify_google_token: {type(e).__name__}: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )


@router.post("/auth/verify-email", response_model=VerifyResponse)
async def verify_with_email(request: VerifyEmailRequest):
    """
    Alternative verification using email (fallback when id_token not available).
    This is less secure but allows login when id_token is not provided by OAuth provider.
    
    Args:
        request: Request with user email and ID
        
    Returns:
        Backend JWT token and user info
    """
    try:
        user_email = request.email
        user_id = request.user_id
        
        if not user_email:
            raise HTTPException(status_code=400, detail="Email is required")
        
        # Check email domain
        allowed_domain = "@cloudusinfotech.com"
        if not user_email.endswith(allowed_domain):
            raise HTTPException(
                status_code=403,
                detail=f"Email domain not allowed. Must be {allowed_domain}"
            )
        
        # Create backend JWT token
        payload = {
            "userId": user_id,
            "email": user_email,
            "isAdmin": False,
            "exp": datetime.utcnow() + timedelta(days=1)
        }
        
        backend_token = jwt.encode(payload, settings.nextauth_secret, algorithm="HS256")
        
        return VerifyResponse(
            token=backend_token,
            user={
                "id": user_id,
                "email": user_email,
                "is_admin": False
            }
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error creating token: {str(e)}")

