"""
Application configuration using Pydantic Settings.
"""
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
import os


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # Google Cloud Configuration
    google_cloud_project_id: str
    google_cloud_location: str = "us-central1"
    google_application_credentials: str = ""
    # Name of the Google Cloud Storage bucket for documents (required for documents APIs).
    # Kept optional (default empty) so the server can still boot without documents configured.
    gcs_bucket_name: str = ""
    
    # Google OAuth Configuration
    google_oauth_client_id: str = ""  # OAuth Client ID for token verification (e.g., "931247202536-umuto0b7bo9j74s684gan29q8qpi3rs1.apps.googleusercontent.com")
    
    # Vertex AI Agent Configuration
    vertex_ai_agent_id: str
    vertex_ai_agent_location: str = "us-central1"
    
    # API Configuration
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    cors_origins: str = "http://localhost:3000"
    
    # NextAuth Secret
    nextauth_secret: str
    
    # Document Upload Configuration
    max_file_size_mb: int = 10  # Maximum file size in MB
    allowed_file_extensions: str = ".pdf,.docx,.txt,.md"  # Comma-separated list
    
    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=False,
        extra="ignore"  # Ignore extra fields in .env file that aren't defined in Settings
    )
    
    @property
    def cors_origins_list(self) -> List[str]:
        """Convert comma-separated CORS origins to list."""
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()

