from fastapi import HTTPException, status
from database import get_db
import structlog

logger = structlog.get_logger(__name__)


# ─── Asset Queries ────────────────────────────────────────────────────────────

def create_asset(code: str, description: str | None, total_quantity: int) -> dict:
    log = logger.bind(code=code, total_quantity=total_quantity)
    log.debug("assets.create.attempt")
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO assets (code, description, total_quantity)
                    VALUES (%s, %s, %s)
                    RETURNING id, code, description, status,
                              total_quantity, claimed_quantity, created_at
                    """,
                    (code, description, total_quantity),
                )
                row = cur.fetchone()
                log.info("assets.create.success", asset_id=row[0])
                return _row_to_asset(row)
            except Exception as e:
                if "unique" in str(e).lower():
                    log.warning("assets.create.conflict", code=code)
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail=f"An asset with code '{code}' already exists.",
                    )
                log.error("assets.create.error", exc_info=True)
                raise


def get_all_assets() -> list[dict]:
    logger.debug("assets.list")
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, description, status,
                       total_quantity, claimed_quantity, created_at
                FROM assets
                ORDER BY created_at DESC
                """
            )
            rows = cur.fetchall()
            return [_row_to_asset(r) for r in rows]


def get_asset_by_id(asset_id: int) -> dict:
    logger.debug("assets.get", asset_id=asset_id)
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT id, code, description, status,
                       total_quantity, claimed_quantity, created_at
                FROM assets
                WHERE id = %s
                """,
                (asset_id,),
            )
            row = cur.fetchone()
            if not row:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Asset {asset_id} not found.",
                )
            return _row_to_asset(row)


def _row_to_asset(row: tuple) -> dict:
    """Map a raw assets row tuple to a dict, computing available_quantity."""
    return {
        "id": row[0],
        "code": row[1],
        "description": row[2],
        "status": row[3],
        "total_quantity": row[4],
        "claimed_quantity": row[5],
        "available_quantity": row[4] - row[5],   # total - claimed
        "created_at": row[6],
    }


# ─── Claim (Critical Section) ─────────────────────────────────────────────────

def claim_asset(asset_id: int, user_id: int) -> dict:
    """
    Claim an asset for a user.

    Concurrency strategy: SELECT ... FOR UPDATE acquires a row-level lock
    on the specific asset row at the start of the transaction. Any other
    session trying to claim the same asset will block here until we
    COMMIT or ROLLBACK, eliminating the read-check-write race condition.
    """
    log = logger.bind(asset_id=asset_id, user_id=user_id)
    log.debug("assets.claim.attempt")
    with get_db() as conn:
        with conn.cursor() as cur:

            # ── Step 1: Lock the row ──────────────────────────────────────────
            cur.execute(
                """
                SELECT id, code, status, total_quantity, claimed_quantity
                FROM assets
                WHERE id = %s
                FOR UPDATE
                """,
                (asset_id,),
            )
            asset = cur.fetchone()

            if not asset:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Asset {asset_id} not found.",
                )

            _, code, asset_status, total_qty, claimed_qty = asset

            # ── Step 2: Business rule checks (while lock is held) ─────────────
            if asset_status != "available":
                log.warning("assets.claim.exhausted_or_unavailable", asset_code=code, asset_status=asset_status)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Asset '{code}' is not available (status: {asset_status}).",
                )

            if claimed_qty >= total_qty:
                log.warning("assets.claim.exhausted", asset_code=code)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"Asset '{code}' is fully claimed. No units remaining.",
                )

            # ── Step 3: Check if user already claimed this asset ──────────────
            cur.execute(
                "SELECT id FROM claims WHERE user_id = %s AND asset_id = %s",
                (user_id, asset_id),
            )
            if cur.fetchone():
                log.warning("assets.claim.duplicate", asset_code=code)
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=f"You have already claimed asset '{code}'.",
                )

            # ── Step 4: Insert claim record ───────────────────────────────────
            cur.execute(
                """
                INSERT INTO claims (user_id, asset_id, status)
                VALUES (%s, %s, 'active')
                RETURNING id
                """,
                (user_id, asset_id),
            )
            claim_id = cur.fetchone()[0]

            # ── Step 5: Increment claimed_quantity atomically in the DB ──────
            # Do NOT compute new values in Python — let the DB do it.
            # If two threads both read claimed_qty=9 and both compute
            # new_claimed=10 in Python, both try to set status='exhausted'
            # on a row already exhausted → CheckViolation crash.
            # Doing it in SQL means the DB evaluates claimed_quantity
            # at the moment of the UPDATE, after the lock is held.
            cur.execute(
                """
                UPDATE assets
                SET claimed_quantity = claimed_quantity + 1,
                    status = CASE
                        WHEN claimed_quantity + 1 >= total_quantity THEN 'exhausted'
                        ELSE 'available'
                    END
                WHERE id = %s
                """,
                (asset_id,),
            )

            # ── COMMIT happens automatically in get_db() context manager ──────
            log.info("assets.claim.success", claim_id=claim_id, asset_code=code)            
            return {"claim_id": claim_id, "asset_code": code}


# ─── User Claim History (JOIN Query) ─────────────────────────────────────────

def get_user_claims(user_id: int) -> list[dict]:
    """
    Returns a user's full claim history with asset details.
    Performs an INNER JOIN between claims and assets.
    """
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    c.id            AS claim_id,
                    c.claimed_at,
                    c.status        AS claim_status,
                    a.id            AS asset_id,
                    a.code          AS asset_code,
                    a.description   AS asset_description,
                    a.status        AS asset_status
                FROM claims c
                INNER JOIN assets a ON a.id = c.asset_id
                WHERE c.user_id = %s
                ORDER BY c.claimed_at DESC
                """,
                (user_id,),
            )
            rows = cur.fetchall()
            return [
                {
                    "claim_id":          r[0],
                    "claimed_at":        r[1],
                    "claim_status":      r[2],
                    "asset_id":          r[3],
                    "asset_code":        r[4],
                    "asset_description": r[5],
                    "asset_status":      r[6],
                }
                for r in rows
            ]
