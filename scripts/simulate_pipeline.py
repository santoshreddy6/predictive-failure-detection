#!/usr/bin/env python3
"""
simulate_pipeline.py
────────────────────
Simulates a CI/CD pipeline locally:
  1. Runs the sample-app tests and collects logs
  2. Sends logs to the predictor service
  3. Prints the risk decision
  4. Exits 0 (ALLOW/WARN) or 1 (BLOCK)

Usage:
    python scripts/simulate_pipeline.py
    python scripts/simulate_pipeline.py --inject-errors   # force risky logs
"""

import subprocess
import requests
import json
import sys
import argparse
import os

PREDICTOR_URL = os.getenv("PREDICTOR_URL", "http://localhost:8000")

# ── Healthy log sample ────────────────────────────────────────────────────────
HEALTHY_LOGS = """
Step 1/5: Checking out code... done
Step 2/5: Installing dependencies...
  Installing fastapi==0.111.0 ... done
  Installing pytest==8.2.0 ... done
Step 3/5: Running tests...
  test_add_positive PASSED
  test_add_negative PASSED
  test_divide_normal PASSED
  test_divide_by_zero PASSED
  test_add_zero PASSED
  5 tests passed in 0.42s
Step 4/5: Building Docker image...
  Successfully built a1b2c3d4e5f6
Step 5/5: Build successful.
"""

# ── Risky log sample ──────────────────────────────────────────────────────────
RISKY_LOGS = """
Step 1/5: Checking out code... done
Step 2/5: Installing dependencies...
  ERROR: Could not install packages due to dependency error
  npm ERR! code ERESOLVE
Step 3/5: Running tests...
  test_add_positive PASSED
  test_divide_normal FAILED - AssertionError: expected 5.0 got 4.9
  test_divide_by_zero FAILED - did not raise exception
  2 tests failed, 3 passed
  Connection timeout while uploading test results
Step 4/5: Building Docker image...
  Error: permission denied while trying to connect to the Docker daemon
  Build failed. Exit code 1
Step 5/5: Fatal error encountered. Pipeline aborted.
"""


def run_real_tests() -> str:
    """Run the actual pytest suite and capture output."""
    print("▶ Running real tests against sample-app...")
    result = subprocess.run(
        ["python", "-m", "pytest", "sample-app/tests/", "-v", "--tb=short"],
        capture_output=True, text=True,
        cwd=os.path.join(os.path.dirname(__file__), "..")
    )
    return result.stdout + result.stderr


def analyze(logs: str, branch: str = "local", commit: str = "local-test") -> dict:
    """Send logs to the predictor and return the parsed response."""
    payload = {
        "logs": logs,
        "pipeline_id": "local-simulation",
        "branch": branch,
        "commit_sha": commit,
    }
    try:
        resp = requests.post(f"{PREDICTOR_URL}/analyze", json=payload, timeout=10)
        resp.raise_for_status()
        return resp.json()
    except requests.exceptions.ConnectionError:
        print(f"\n❌ Cannot reach predictor at {PREDICTOR_URL}")
        print("   Start it with:  docker compose up predictor")
        sys.exit(2)


def print_result(result: dict):
    decision = result["decision"]
    score    = result["risk_score"]
    summary  = result["summary"]
    matched  = result["matched_patterns"]
    safe     = result["safe_patterns"]

    icons = {"ALLOW": "✅", "WARN": "⚠️", "BLOCK": "🚨"}
    print("\n" + "═" * 55)
    print(f"  {icons[decision]}  DECISION: {decision}   (Risk Score: {score}/100)")
    print("═" * 55)
    print(f"  {summary}")

    if matched:
        print("\n  ── Risk Patterns Detected ──")
        for p in matched:
            print(f"    [{p['weight_contribution']:+d}]  {p['label']}  (×{p['count']})")

    if safe:
        print("\n  ── Safe Patterns Detected ──")
        for p in safe:
            print(f"    [{p['weight_contribution']:+d}]  {p['label']}  (×{p['count']})")

    print()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--inject-errors", action="store_true", help="Use risky log sample")
    parser.add_argument("--real-tests",    action="store_true", help="Run actual pytest suite")
    args = parser.parse_args()

    if args.real_tests:
        logs = run_real_tests()
        print("▶ Captured test logs. Sending to predictor...\n")
    elif args.inject_errors:
        print("▶ Using RISKY log sample (--inject-errors)...\n")
        logs = RISKY_LOGS
    else:
        print("▶ Using HEALTHY log sample (default)...\n")
        logs = HEALTHY_LOGS

    result = analyze(logs)
    print_result(result)

    # Exit code mirrors decision: BLOCK → 1, else → 0
    sys.exit(1 if result["decision"] == "BLOCK" else 0)


if __name__ == "__main__":
    main()
