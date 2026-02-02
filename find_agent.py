"""
Helper script to list Google Agent Builder agents and find correct location.
"""
import sys
import os

# Add parent directory to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.config import settings
from google.oauth2 import service_account


def list_agents():
    """List all Dialogflow CX agents in the project."""
    try:
        from google.cloud import dialogflowcx_v3beta1 as dialogflow
        
        # Initialize credentials
        credentials = None
        if settings.google_application_credentials:
            cred_path = settings.google_application_credentials.strip()
            if os.path.exists(cred_path):
                credentials = service_account.Credentials.from_service_account_file(
                    cred_path,
                    scopes=["https://www.googleapis.com/auth/cloud-platform"]
                )
        
        if credentials:
            client = dialogflow.AgentsClient(credentials=credentials)
        else:
            client = dialogflow.AgentsClient()
        
        # Common locations to check
        locations = ["us-central1", "us-east1", "us-west1", "europe-west1", "asia-southeast1", "global"]
        
        print("=" * 60)
        print("Searching for Google Agent Builder Agents")
        print("=" * 60)
        print(f"Project ID: {settings.google_cloud_project_id}")
        print()
        
        found_agents = []
        
        for location in locations:
            try:
                parent = f"projects/{settings.google_cloud_project_id}/locations/{location}"
                print(f"Checking location: {location}...")
                
                agents = client.list_agents(parent=parent)
                
                for agent in agents:
                    found_agents.append({
                        "name": agent.name,
                        "display_name": agent.display_name,
                        "location": location,
                        "agent_id": agent.name.split("/")[-1]
                    })
                    print(f"  Found agent: {agent.display_name}")
                    print(f"    Location: {location}")
                    print(f"    Agent ID: {agent.name.split('/')[-1]}")
                    print()
            except Exception as e:
                if "404" not in str(e) and "not found" not in str(e).lower():
                    print(f"  Error checking {location}: {str(e)}")
        
        if found_agents:
            print("=" * 60)
            print("Found Agents:")
            print("=" * 60)
            for agent in found_agents:
                print(f"Display Name: {agent['display_name']}")
                print(f"Location: {agent['location']}")
                print(f"Agent ID: {agent['agent_id']}")
                print()
            
            print("=" * 60)
            print("Update your .env file with:")
            print("=" * 60)
            if found_agents:
                first_agent = found_agents[0]
                print(f"VERTEX_AI_AGENT_LOCATION={first_agent['location']}")
                print(f"VERTEX_AI_AGENT_ID={first_agent['agent_id']}")
        else:
            print("No agents found in common locations.")
            print()
            print("Please check:")
            print("1. Your project ID is correct")
            print("2. You have Dialogflow CX agents created")
            print("3. Your service account has proper permissions")
            print("4. Check Google Cloud Console for agent location")
        
    except Exception as e:
        print(f"Error: {str(e)}")
        print()
        print("Make sure:")
        print("1. Credentials file path is correct in .env")
        print("2. Service account has Dialogflow API permissions")
        print("3. Dialogflow CX API is enabled in your project")


if __name__ == "__main__":
    list_agents()

