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
    """Return 422 validation errors in a consistent JSON format."""
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={
            "detail": exc.errors(),
            "body": str(exc.body) if hasattr(exc, "body") else None,
        },
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

