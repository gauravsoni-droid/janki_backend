"""
Google Agent Builder service - Dialogflow CX integration.
"""
import os
import json
from typing import Optional
from google.oauth2 import service_account
from app.config import settings
import logging

logger = logging.getLogger(__name__)


class GoogleAgentService:
    """Service for interacting with Google Agent Builder."""
    
    def __init__(self):
        """Initialize Google Agent Builder service."""
        try:
            self.project_id = settings.google_cloud_project_id
            self.location = settings.vertex_ai_agent_location
            self.agent_id = settings.vertex_ai_agent_id
            
            # Store credentials for later use
            self.credentials = None
            if settings.google_application_credentials:
                cred_value = settings.google_application_credentials.strip()
                # Check if it's a JSON string (starts with {) - for cloud platforms
                if cred_value.startswith("{"):
                    try:
                        cred_dict = json.loads(cred_value)
                        logger.info("Using service account credentials from JSON environment variable")
                        self.credentials = service_account.Credentials.from_service_account_info(
                            cred_dict,
                            scopes=["https://www.googleapis.com/auth/cloud-platform"]
                        )
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse credentials JSON: {str(e)}")
                # Otherwise, treat as file path
                elif os.path.exists(cred_value):
                    logger.info(f"Using service account credentials from: {cred_value}")
                    self.credentials = service_account.Credentials.from_service_account_file(
                        cred_value,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                else:
                    logger.warning(f"Credentials file not found at: {cred_value}")
            
            if not self.credentials:
                logger.info("Will use Application Default Credentials")
            
            logger.info(f"Initialized Google Agent Builder Service - Project: {self.project_id}, Location: {self.location}, Agent ID: {self.agent_id}")
            
        except Exception as e:
            logger.error(f"Error initializing Google Agent Builder Service: {str(e)}")
            raise
    
    async def send_message(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> dict:
        """
        Send a message to the Google Agent Builder agent and get a response.
        Uses Dialogflow CX API.
        """
        return await self._send_message_dialogflow_cx(message, conversation_id, user_id)
    
    async def _send_message_dialogflow_cx(
        self,
        message: str,
        conversation_id: Optional[str] = None,
        user_id: Optional[str] = None
    ) -> dict:
        """Send message using Dialogflow CX API via REST."""
        import httpx
        
        session_id = conversation_id or f"session_{user_id or 'default'}"
        access_token = self._get_access_token()
        
        # Dialogflow CX REST API endpoint format
        # For regional endpoints: https://{location}-dialogflow.googleapis.com/v3beta1/...
        url = f"https://{self.location}-dialogflow.googleapis.com/v3beta1/projects/{self.project_id}/locations/{self.location}/agents/{self.agent_id}/sessions/{session_id}:detectIntent"
        
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }
        
        payload = {
            "queryInput": {
                "text": {
                    "text": message
                },
                "languageCode": "en"
            }
        }
        
        logger.info(f"Sending message to Dialogflow CX: {url}")
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            # Extract response
            query_result = data.get("queryResult", {})
            response_messages = query_result.get("responseMessages", [])
            
            response_text = "No response"
            for msg in response_messages:
                if msg.get("text") and msg["text"].get("text"):
                    response_text = msg["text"]["text"][0]
                    break
            
            return {
                "response": response_text,
                "intent": query_result.get("intent", {}).get("displayName"),
                "confidence": query_result.get("intentDetectionConfidence"),
                "conversation_id": session_id,
                "sources": []
            }
    
    def _get_access_token(self) -> str:
        """Get access token for REST API calls."""
        from google.auth.transport.requests import Request
        from google.oauth2 import service_account
        
        try:
            if self.credentials:
                credentials = self.credentials
            elif settings.google_application_credentials:
                cred_value = settings.google_application_credentials.strip()
                # Check if it's a JSON string (starts with {) - for cloud platforms
                if cred_value.startswith("{"):
                    try:
                        cred_dict = json.loads(cred_value)
                        credentials = service_account.Credentials.from_service_account_info(
                            cred_dict,
                            scopes=["https://www.googleapis.com/auth/cloud-platform"]
                        )
                    except json.JSONDecodeError as e:
                        raise Exception(f"Failed to parse credentials JSON: {str(e)}")
                # Otherwise, treat as file path
                elif os.path.exists(cred_value):
                    credentials = service_account.Credentials.from_service_account_file(
                        cred_value,
                        scopes=["https://www.googleapis.com/auth/cloud-platform"]
                    )
                else:
                    # Fall back to Application Default Credentials instead of raising error
                    logger.warning(f"Credentials file not found at: {cred_value}, falling back to ADC")
                    from google.auth import default
                    credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            else:
                from google.auth import default
                credentials, _ = default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
            
            credentials.refresh(Request())
            return credentials.token
        except Exception as e:
            logger.error(f"Error getting access token: {str(e)}")
            raise Exception(f"Failed to get access token: {str(e)}")


# Singleton instance
vertex_service = GoogleAgentService()
