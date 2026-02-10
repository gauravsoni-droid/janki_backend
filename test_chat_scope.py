"""
Test script for chat endpoint with scope filtering.
Tests the scope-based document filtering functionality.
"""
import requests
import json
import sys

BASE_URL = "http://localhost:8000"
ENDPOINT = f"{BASE_URL}/api/v1/chat"

def test_chat_scope(auth_token: str):
    """Test chat endpoint with different scopes."""
    headers = {
        "Authorization": f"Bearer {auth_token}",
        "Content-Type": "application/json"
    }
    
    # Test MY scope
    print("\n=== Testing MY scope ===")
    payload = {
        "message": "What documents do I have?",
        "scope": "MY"
    }
    response = requests.post(ENDPOINT, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {data.get('response', '')[:100]}...")
        print(f"Sources: {data.get('sources', [])}")
    else:
        print(f"Error: {response.text}")
    
    # Test COMPANY scope
    print("\n=== Testing COMPANY scope ===")
    payload = {
        "message": "What company documents are available?",
        "scope": "COMPANY"
    }
    response = requests.post(ENDPOINT, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {data.get('response', '')[:100]}...")
        print(f"Sources: {data.get('sources', [])}")
    else:
        print(f"Error: {response.text}")
    
    # Test ALL scope
    print("\n=== Testing ALL scope ===")
    payload = {
        "message": "What documents are available?",
        "scope": "ALL"
    }
    response = requests.post(ENDPOINT, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 200:
        data = response.json()
        print(f"Response: {data.get('response', '')[:100]}...")
        print(f"Sources: {data.get('sources', [])}")
    else:
        print(f"Error: {response.text}")
    
    # Test invalid scope
    print("\n=== Testing invalid scope ===")
    payload = {
        "message": "Test message",
        "scope": "INVALID"
    }
    response = requests.post(ENDPOINT, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    if response.status_code == 400:
        print("✓ Correctly rejected invalid scope")
    else:
        print(f"Unexpected response: {response.text}")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python test_chat_scope.py <auth_token>")
        print("\nTo get an auth token:")
        print("1. Log in to the frontend")
        print("2. Open browser dev tools -> Application -> Local Storage")
        print("3. Find 'nextauth.session.token' and copy the backendToken value")
        sys.exit(1)
    
    auth_token = sys.argv[1]
    test_chat_scope(auth_token)

