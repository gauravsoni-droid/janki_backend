"""
FastAPI main application entry point.
"""
import logging
import json
from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routers import chat, auth, documents
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Janki Chatbot API",
    description="FastAPI backend for Janki chatbot with Google Agent Builder integration",
    version="1.0.0"
)

# CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Exception handler for 422 validation errors
@app.exception_handler(RequestValidationError)
async def validation_exception_handler(request: Request, exc: RequestValidationError):
    """Log 422 validation errors with full request details."""
    # #region agent log
    try:
        # Get request body if available
        body = None
        try:
            if hasattr(request, "_body"):
                body = request._body
            elif hasattr(request, "body"):
                body = await request.body()
        except Exception:
            pass
        
        # Get headers
        headers = dict(request.headers)
        
        # Get form data if multipart
        form_data = {}
        try:
            if request.headers.get("content-type", "").startswith("multipart/form-data"):
                form_data = {"content_type": "multipart/form-data", "note": "form data in body"}
        except Exception:
            pass
        
        debug_payload = {
            "sessionId": "debug-session",
            "runId": "pre-fix",
            "hypothesisId": "H1-H5",
            "location": "main.py:validation_exception_handler",
            "message": "422 Validation Error caught",
            "data": {
                "path": str(request.url.path),
                "method": request.method,
                "headers": {k: v for k, v in headers.items() if k.lower() not in ["authorization", "cookie"]},
                "content_type": headers.get("content-type", "missing"),
                "body_size": len(body) if body else 0,
                "body_preview": str(body)[:200] if body else None,
                "form_data_note": form_data,
                "validation_errors": exc.errors() if hasattr(exc, "errors") else str(exc),
                "error_count": len(exc.errors()) if hasattr(exc, "errors") else 0,
            },
            "timestamp": int(datetime.utcnow().timestamp() * 1000),
        }
        with open(r"c:\Users\Kinjal Cloudus\Desktop\janki_bmad\.cursor\debug.log", "a", encoding="utf-8") as f:
            f.write(json.dumps(debug_payload) + "\n")
    except Exception:
        pass
    # #endregion
    
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": str(exc.body) if hasattr(exc, "body") else None},
    )

# Include routers
app.include_router(auth.router, prefix="/api/v1", tags=["auth"])
app.include_router(chat.router, prefix="/api/v1", tags=["chat"])
app.include_router(documents.router, prefix="/api/v1", tags=["documents"])


@app.on_event("startup")
async def startup_event():
    """Log configuration on startup and initialize database."""
    logger.info("=" * 60)
    logger.info("Starting Janki Chatbot API")
    logger.info("=" * 60)
    logger.info(f"Project ID: {settings.google_cloud_project_id}")
    logger.info(f"Location: {settings.vertex_ai_agent_location}")
    logger.info(f"Agent ID: {settings.vertex_ai_agent_id}")
    logger.info(f"API running on: http://{settings.api_host}:{settings.api_port}")
    logger.info("=" * 60)
    
    # Initialize database tables
    from app.database import init_db
    init_db()
    logger.info("Database initialized successfully")
    logger.info("=" * 60)
    logger.info("Connected to Google Agent Builder")
    logger.info("=" * 60)


@app.get("/")
async def root():
    """Health check endpoint."""
    return {
        "message": "Janki Chatbot API is running",
        "status": "ok",
        "project_id": settings.google_cloud_project_id,
        "agent_id": settings.vertex_ai_agent_id
    }


@app.get("/health")
async def health():
    """Health check endpoint."""
    return {"status": "healthy"}

