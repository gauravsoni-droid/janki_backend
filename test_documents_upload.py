"""
Basic manual test script for the document upload endpoint.

This mirrors the pattern used in test_auth_endpoint.py and can be run
against a running backend to validate Story 1.1 behaviour:

- Valid upload with category succeeds.
- Unsupported file types are rejected.
- Oversized files are rejected.
"""
import os
import sys
from typing import Tuple

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def _get_test_token() -> str:
    """
    Fetch a backend token from environment.

    This avoids hardcoding any credentials and lets you re-use a token
    obtained via the normal auth flow (e.g., from the frontend).
    """
    token = os.getenv("BACKEND_BEARER_TOKEN", "")
    if not token:
        print("[WARN] BACKEND_BEARER_TOKEN not set; cannot fully test auth-protected upload.")
    return token


def _make_headers() -> dict:
    token = _get_test_token()
    headers = {"Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_happy_path() -> Tuple[bool, str]:
    """Validate a small text file uploads successfully with a category."""
    print("== Test: Happy path upload ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents"

    files = {"file": ("sample.txt", b"hello world", "text/plain")}
    data = {
        "category": "Backend",
        "custom_category": "",
        "is_company_doc": "false",
    }

    resp = requests.post(url, headers=_make_headers(), files=files, data=data, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")

    return resp.status_code == 200, "happy-path"


def test_unsupported_type() -> Tuple[bool, str]:
    """Validate unsupported file types are rejected with 400."""
    print("== Test: Unsupported file type ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents"

    files = {"file": ("image.exe", b"fake-binary", "application/octet-stream")}
    data = {
        "category": "Backend",
        "custom_category": "",
        "is_company_doc": "false",
    }

    resp = requests.post(url, headers=_make_headers(), files=files, data=data, timeout=10)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")

    return resp.status_code == 400, "unsupported-type"


def test_oversized_file() -> Tuple[bool, str]:
    """
    Validate oversized files are rejected.

    Uses a payload slightly larger than the configured max_file_size_mb.
    """
    print("== Test: Oversized file ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents"

    # Default max_file_size_mb is 10; use ~11MB buffer
    oversized_bytes = b"x" * (11 * 1024 * 1024)
    files = {"file": ("big.txt", oversized_bytes, "text/plain")}
    data = {
        "category": "Backend",
        "custom_category": "",
        "is_company_doc": "false",
    }

    resp = requests.post(url, headers=_make_headers(), files=files, data=data, timeout=60)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")

    # Either FastAPI or the backend validation should return 400
    return resp.status_code == 400, "oversized-file"


def main() -> int:
    print("=" * 60)
    print("Testing Documents Upload Endpoint")
    print("=" * 60)

    tests = [test_happy_path, test_unsupported_type, test_oversized_file]
    all_ok = True

    for fn in tests:
        ok, name = fn()
        prefix = "[OK]" if ok else "[FAIL]"
        print(f"{prefix} {name}")
        all_ok = all_ok and ok
        print("-" * 40)

    print("=" * 60)
    print("Result:", "ALL PASSED" if all_ok else "SOME TESTS FAILED")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())


