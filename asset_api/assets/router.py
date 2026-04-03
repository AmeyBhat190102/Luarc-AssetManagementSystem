from fastapi import APIRouter, Depends
from schemas import AssetOut, AssetCreateRequest, ClaimOut, ClaimResponse
from auth.dependencies import get_current_user
from assets.service import (
    create_asset,
    get_all_assets,
    get_asset_by_id,
    claim_asset,
    get_user_claims,
)

router = APIRouter(tags=["Assets"])


# ─── Asset Pool Endpoints ─────────────────────────────────────────────────────

@router.post("/assets", response_model=AssetOut, status_code=201)
def create(body: AssetCreateRequest, user=Depends(get_current_user)):
    """
    Create a new asset (coupon/voucher pool).
    Requires authentication. Raises 409 if the asset code already exists.
    """
    return create_asset(
        code=body.code,
        description=body.description,
        total_quantity=body.total_quantity,
    )

@router.get("/assets", response_model=list[AssetOut])
def list_assets(user=Depends(get_current_user)):
    """
    Returns the full global asset pool with current availability state.
    Requires authentication.
    """
    return get_all_assets()


@router.get("/assets/{asset_id}", response_model=AssetOut)
def get_asset(asset_id: int, user=Depends(get_current_user)):
    """
    Returns a single asset by ID.
    Requires authentication.
    """
    return get_asset_by_id(asset_id)


# ─── Claim Endpoint ───────────────────────────────────────────────────────────

@router.post("/assets/{asset_id}/claim", response_model=ClaimResponse, status_code=201)
def claim(asset_id: int, user=Depends(get_current_user)):
    """
    Claim an asset for the authenticated user.

    Internally uses SELECT ... FOR UPDATE to lock the asset row,
    ensuring no two concurrent requests can over-claim the same asset.

    Raises:
        404 if the asset does not exist.
        409 if the asset is exhausted or already claimed by this user.
    """
    result = claim_asset(asset_id=asset_id, user_id=user["id"])
    return {
        "message": "Asset claimed successfully.",
        "claim_id": result["claim_id"],
        "asset_code": result["asset_code"],
    }


# ─── User History Endpoint ────────────────────────────────────────────────────

@router.get("/users/me/claims", response_model=list[ClaimOut])
def my_claims(user=Depends(get_current_user)):
    """
    Returns the authenticated user's full claim history,
    joined with asset details.
    """
    return get_user_claims(user_id=user["id"])
