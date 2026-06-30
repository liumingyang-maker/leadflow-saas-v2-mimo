#!/usr/bin/env python3
"""Staging environment smoke test script.

Runs a series of checks against a running staging environment to verify
it's functioning correctly.

Usage:
    python scripts/staging_smoke.py [--base-url URL] [--dry-run]
"""

from __future__ import annotations

import argparse
import sys
import urllib.request
from urllib.error import URLError


def check_endpoint(url: str, *, expect_status: int = 200, timeout: int = 10) -> tuple[bool, str]:
    """Check if an endpoint returns the expected status code."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.getcode()
            if status == expect_status:
                return True, f"OK ({status})"
            return False, f"Expected {expect_status}, got {status}"
    except URLError as e:
        return False, f"Error: {e}"
    except Exception as e:
        return False, f"Error: {e}"


def check_security_headers(url: str) -> tuple[bool, list[str]]:
    """Check if security headers are present."""
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=10) as resp:
            headers = resp.headers
            missing = []
            required = [
                "X-Content-Type-Options",
                "X-Frame-Options",
                "Referrer-Policy",
                "Content-Security-Policy",
            ]
            for header in required:
                if header not in headers:
                    missing.append(header)
            if missing:
                return False, missing
            return True, []
    except Exception as e:
        return False, [f"Error: {e}"]


def main() -> int:
    parser = argparse.ArgumentParser(description="Staging smoke tests")
    parser.add_argument(
        "--base-url",
        default="http://localhost:5000",
        help="Base URL of the staging environment",
    )
    parser.add_argument("--dry-run", action="store_true", help="Only show what would be tested")
    args = parser.parse_args()

    print("=" * 60)
    print("Staging Environment Smoke Tests")
    print("=" * 60)
    print(f"\nTarget: {args.base_url}")

    if args.dry_run:
        print("\n[DRY RUN] Would test:")
        print("  - Health endpoints (/health/live, /health/ready)")
        print("  - Login page accessibility")
        print("  - Security headers")
        print("  - Database connectivity (via /health/ready)")
        return 0

    passed = 0
    failed = 0
    total = 0

    # Test 1: Health live endpoint
    total += 1
    print(f"\n[{total}] Health live endpoint...")
    ok, msg = check_endpoint(f"{args.base_url}/health/live")
    if ok:
        print(f"  ✓ {msg}")
        passed += 1
    else:
        print(f"  ✗ {msg}")
        failed += 1

    # Test 2: Health ready endpoint (tests DB connectivity)
    total += 1
    print(f"\n[{total}] Health ready endpoint (DB check)...")
    ok, msg = check_endpoint(f"{args.base_url}/health/ready")
    if ok:
        print(f"  ✓ {msg}")
        passed += 1
    else:
        print(f"  ✗ {msg}")
        failed += 1

    # Test 3: Login page
    total += 1
    print(f"\n[{total}] Login page...")
    ok, msg = check_endpoint(f"{args.base_url}/login")
    if ok:
        print(f"  ✓ {msg}")
        passed += 1
    else:
        print(f"  ✗ {msg}")
        failed += 1

    # Test 4: Security headers
    total += 1
    print(f"\n[{total}] Security headers...")
    ok, missing = check_security_headers(f"{args.base_url}/health/live")
    if ok:
        print("  ✓ All required headers present")
        passed += 1
    else:
        print(f"  ✗ Missing headers: {', '.join(missing)}")
        failed += 1

    # Summary
    print("\n" + "=" * 60)
    print(f"Results: {passed}/{total} passed, {failed} failed")
    print("=" * 60)

    if failed > 0:
        print("\n✗ Staging smoke tests FAILED")
        return 1

    print("\n✓ Staging smoke tests PASSED")
    return 0


if __name__ == "__main__":
    sys.exit(main())
