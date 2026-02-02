"""
Test script to diagnose authentication issues.
Run this to check if backend auth endpoint is working.
"""
import requests
import sys

BACKEND_URL = "http://localhost:8000"

def test_backend_auth():
    """Test if backend auth endpoint is accessible."""
    print("=" * 60)
    print("Testing Backend Auth Endpoint")
    print("=" * 60)
    
    # Test 1: Check if backend is running
    try:
        response = requests.get(f"{BACKEND_URL}/", timeout=5)
        print(f"[OK] Backend is running: {response.status_code}")
        print(f"   Response: {response.json()}")
    except Exception as e:
        print(f"[ERROR] Backend is NOT running: {e}")
        print("   Please start the backend server first!")
        return False
    
    # Test 2: Check auth endpoint exists
    try:
        # This should return 400 (bad request) not 404 (not found)
        response = requests.post(
            f"{BACKEND_URL}/api/v1/auth/verify",
            json={"google_token": "test"},
            timeout=5
        )
        if response.status_code == 400 or response.status_code == 401:
            print(f"[OK] Auth endpoint exists: {response.status_code}")
        else:
            print(f"[WARNING] Unexpected status: {response.status_code}")
            print(f"   Response: {response.text}")
    except Exception as e:
        print(f"[ERROR] Auth endpoint error: {e}")
        return False
    
    print("=" * 60)
    print("Backend auth endpoint is accessible!")
    print("=" * 60)
    return True

if __name__ == "__main__":
    success = test_backend_auth()
    sys.exit(0 if success else 1)

