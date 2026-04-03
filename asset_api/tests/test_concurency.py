"""
Concurrency test for the Asset Claiming system.

What this proves:
  - 50 threads all try to claim the same asset simultaneously
  - The asset only has 10 units
  - After all threads finish, exactly 10 claims exist — no more, no less
  - The asset's claimed_quantity is exactly 10
  - The asset status flipped to 'exhausted'

How to run:
  1. Make sure your DB is running and schema is applied
  2. From the asset_api directory:
        python test_concurrency.py
"""

import sys
import threading
import uuid

import psycopg2
import requests

# ── Config ────────────────────────────────────────────────────────────────────

BASE_URL       = "http://localhost:8000"
DATABASE_URL   = "placeholder-url"

TOTAL_UNITS    = 10   # how many units the asset has
TOTAL_THREADS  = 50   # how many users try to claim simultaneously

# ── Helpers ───────────────────────────────────────────────────────────────────

def register_and_login(email: str, password: str = "Test@1234") -> str:
    """Register a user and return their JWT token."""
    requests.post(f"{BASE_URL}/auth/register", json={"email": email, "password": password})
    resp = requests.post(f"{BASE_URL}/auth/login", json={"email": email, "password": password})
    resp.raise_for_status()
    return resp.json()["access_token"]


def create_test_asset(token: str, code: str, total_quantity: int) -> int:
    """Create an asset and return its ID."""
    resp = requests.post(
        f"{BASE_URL}/assets",
        json={"code": code, "description": "Concurrency test asset", "total_quantity": total_quantity},
        headers={"Authorization": f"Bearer {token}"},
    )
    resp.raise_for_status()
    return resp.json()["id"]


def claim_asset(token: str, asset_id: int, results: list, index: int):
    """Try to claim an asset. Store the HTTP status code in results[index]."""
    try:
        resp = requests.post(
            f"{BASE_URL}/assets/{asset_id}/claim",
            headers={"Authorization": f"Bearer {token}"},
        )
        results[index] = resp.status_code
    except Exception as e:
        results[index] = f"ERROR: {e}"


def get_db_state(asset_id: int) -> dict:
    """Directly query the DB to get ground truth — bypasses the API entirely."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()

    cur.execute(
        "SELECT claimed_quantity, total_quantity, status FROM assets WHERE id = %s",
        (asset_id,)
    )
    claimed_qty, total_qty, status = cur.fetchone()

    cur.execute(
        "SELECT COUNT(*) FROM claims WHERE asset_id = %s",
        (asset_id,)
    )
    claim_count = cur.fetchone()[0]

    cur.close()
    conn.close()

    return {
        "claimed_quantity": claimed_qty,
        "total_quantity": total_qty,
        "status": status,
        "claim_rows_in_db": claim_count,
    }


def cleanup(asset_id: int):
    """Remove test data from DB so reruns are clean."""
    conn = psycopg2.connect(DATABASE_URL)
    cur = conn.cursor()
    cur.execute("DELETE FROM claims WHERE asset_id = %s", (asset_id,))
    cur.execute("DELETE FROM assets WHERE id = %s", (asset_id,))
    conn.commit()
    cur.close()
    conn.close()

# ── Test ──────────────────────────────────────────────────────────────────────

def run_test():
    print("\n" + "="*60)
    print("  CONCURRENCY TEST — Asset Claiming")
    print("="*60)
    print(f"  Asset units   : {TOTAL_UNITS}")
    print(f"  Threads       : {TOTAL_THREADS}")
    print(f"  Expected wins : {TOTAL_UNITS}")
    print(f"  Expected fails: {TOTAL_THREADS - TOTAL_UNITS}")
    print("="*60 + "\n")

    # Step 1: Create one admin user to create the asset
    admin_email = f"admin_{uuid.uuid4().hex[:8]}@test.com"
    print(f"[1/5] Registering admin user: {admin_email}")
    admin_token = register_and_login(admin_email)

    # Step 2: Create the test asset
    asset_code = f"TEST-CONCURRENT-{uuid.uuid4().hex[:6].upper()}"
    print(f"[2/5] Creating asset: {asset_code} with {TOTAL_UNITS} units")
    asset_id = create_test_asset(admin_token, asset_code, TOTAL_UNITS)
    print(f"      Asset ID: {asset_id}")

    # Step 3: Create 50 unique users (each user can only claim once)
    print(f"[3/5] Registering {TOTAL_THREADS} unique users...")
    tokens = []
    for i in range(TOTAL_THREADS):
        email = f"user_{uuid.uuid4().hex[:8]}@test.com"
        token = register_and_login(email)
        tokens.append(token)
    print(f"      Done — {TOTAL_THREADS} users ready")

    # Step 4: Fire all claim requests simultaneously
    print(f"[4/5] Firing {TOTAL_THREADS} concurrent claim requests...")
    results = [None] * TOTAL_THREADS
    threads = []

    for i in range(TOTAL_THREADS):
        t = threading.Thread(target=claim_asset, args=(tokens[i], asset_id, results, i))
        threads.append(t)

    # Start all threads as close together as possible
    for t in threads:
        t.start()

    # Wait for all to finish
    for t in threads:
        t.join()

    print("      All threads completed")

    # Step 5: Verify results
    print(f"[5/5] Verifying results...\n")

    successful = [r for r in results if r == 201]
    failed_409 = [r for r in results if r == 409]
    errors     = [r for r in results if r not in (201, 409)]

    db_state = get_db_state(asset_id)

    print(f"  API Results:")
    print(f"    Successful claims (201) : {len(successful)}")
    print(f"    Rejected claims   (409) : {len(failed_409)}")
    print(f"    Errors                  : {len(errors)}")
    if errors:
        print(f"    Error details           : {errors}")

    print(f"\n  Database Ground Truth:")
    print(f"    claimed_quantity        : {db_state['claimed_quantity']}")
    print(f"    total_quantity          : {db_state['total_quantity']}")
    print(f"    status                  : {db_state['status']}")
    print(f"    actual claim rows in DB : {db_state['claim_rows_in_db']}")

    # ── Assertions ────────────────────────────────────────────────────────────
    print("\n" + "-"*60)
    all_passed = True

    def check(description: str, condition: bool):
        nonlocal all_passed
        print(f"{description}")
        if not condition:
            all_passed = False

    check(
        f"Exactly {TOTAL_UNITS} successful API responses (201)",
        len(successful) == TOTAL_UNITS
    )
    check(
        f"Exactly {TOTAL_THREADS - TOTAL_UNITS} rejected API responses (409)",
        len(failed_409) == TOTAL_THREADS - TOTAL_UNITS
    )
    check(
        f"No errors or unexpected status codes",
        len(errors) == 0
    )
    check(
        f"DB claimed_quantity == {TOTAL_UNITS} (no over-claiming)",
        db_state["claimed_quantity"] == TOTAL_UNITS
    )
    check(
        f"DB claim rows == {TOTAL_UNITS} (no duplicate rows)",
        db_state["claim_rows_in_db"] == TOTAL_UNITS
    )
    check(
        f"Asset status is 'exhausted'",
        db_state["status"] == "exhausted"
    )

    print("-"*60)

    if all_passed:
        print("\n ALL CHECKS PASSED — Concurrency handling is correct\n")
    else:
        print("\n SOME CHECKS FAILED — There is a concurrency bug\n")

    # Cleanup
    cleanup(asset_id)
    print("  Test data cleaned up from DB\n")

    return all_passed


if __name__ == "__main__":
    passed = run_test()
    sys.exit(0 if passed else 1)