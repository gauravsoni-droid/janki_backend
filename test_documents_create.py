"""
Manual test script for the create-document endpoint used in Story 1.2.

Run against a running backend to verify:
- Happy path: create text document with title/category/content.
- Validation of missing fields.
- Oversized content handling.
"""
import os
import sys
from typing import Tuple

import requests

BACKEND_URL = os.getenv("BACKEND_URL", "http://localhost:8000")


def _get_token() -> str:
    token = os.getenv("BACKEND_BEARER_TOKEN", "")
    if not token:
        print("[WARN] BACKEND_BEARER_TOKEN not set; requests will likely fail with 401.")
    return token


def _headers() -> dict:
    token = _get_token()
    headers = {"Accept": "application/json", "Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


def test_happy_path() -> Tuple[bool, str]:
    print("== Test: create document happy path ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents/create"
    payload = {
        "title": "My In-App Note",
        "category": "Backend",
        "custom_category": None,
        "content": "# Demo note\nThis was created via the create endpoint.",
        "is_company_doc": False,
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")
    return resp.status_code == 200, "happy-path"


def test_missing_title() -> Tuple[bool, str]:
    print("== Test: missing title validation ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents/create"
    payload = {
        "title": "",
        "category": "Backend",
        "custom_category": None,
        "content": "Some content",
        "is_company_doc": False,
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=15)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")
    return resp.status_code == 400, "missing-title"


def test_oversized_content() -> Tuple[bool, str]:
    print("== Test: oversized content validation ==")
    url = f"{BACKEND_URL}/api/v1/documents/documents/create"
    # Slightly above 11MB assuming default 10MB limit
    big_content = "x" * (11 * 1024 * 1024)
    payload = {
        "title": "Big Document",
        "category": "Backend",
        "custom_category": None,
        "content": big_content,
        "is_company_doc": False,
    }
    resp = requests.post(url, headers=_headers(), json=payload, timeout=60)
    print(f"Status: {resp.status_code}")
    print(f"Body  : {resp.text[:200]}")
    return resp.status_code == 400, "oversized-content"


def main() -> int:
    print("=" * 60)
    print("Testing Documents Create Endpoint")
    print("=" * 60)

    tests = [test_happy_path, test_missing_title, test_oversized_content]
    all_ok = True

    for fn in tests:
        ok, name = fn()
        prefix = "[OK]" if ok else "[FAIL]"
        print(f"{prefix} {name}")
        print("-" * 40)
        all_ok = all_ok and ok

    print("=" * 60)
    print("Result:", "ALL PASSED" if all_ok else "SOME TESTS FAILED")
    print("=" * 60)
    return 0 if all_ok else 1


if __name__ == "__main__":
    sys.exit(main())


