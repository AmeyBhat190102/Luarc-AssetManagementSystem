from datetime import datetime
from pydantic import BaseModel, EmailStr


# ─── Auth ────────────────────────────────────────────────────────────────────

class UserRegisterRequest(BaseModel):
    email: EmailStr
    password: str


class UserLoginRequest(BaseModel):
    email: EmailStr
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserOut(BaseModel):
    id: int
    email: str
    created_at: datetime


# ─── Assets ──────────────────────────────────────────────────────────────────

class AssetCreateRequest(BaseModel):
    code: str
    description: str | None = None
    total_quantity: int


class AssetOut(BaseModel):
    id: int
    code: str
    description: str | None
    status: str
    total_quantity: int
    claimed_quantity: int
    available_quantity: int          # computed, not stored
    created_at: datetime


# ─── Claims ──────────────────────────────────────────────────────────────────

class ClaimOut(BaseModel):
    claim_id: int
    claimed_at: datetime
    claim_status: str  # always 'active'
    asset_id: int
    asset_code: str
    asset_description: str | None
    asset_status: str


class ClaimResponse(BaseModel):
    message: str
    claim_id: int
    asset_code: str
