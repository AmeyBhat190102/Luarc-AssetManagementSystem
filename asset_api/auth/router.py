from fastapi import APIRouter
from schemas import UserRegisterRequest, UserLoginRequest, TokenResponse, UserOut
from auth.service import create_user, authenticate_user, create_access_token

router = APIRouter(prefix="/auth", tags=["Auth"])


@router.post("/register", response_model=UserOut, status_code=201)
def register(body: UserRegisterRequest):
    """
    Register a new user. Returns the created user object.
    Raises 409 if the email is already taken.
    """
    user = create_user(email=body.email, plain_password=body.password)
    return user


@router.post("/login", response_model=TokenResponse)
def login(body: UserLoginRequest):
    """
    Authenticate with email and password.
    Returns a signed JWT access token on success.
    """
    user = authenticate_user(email=body.email, plain_password=body.password)
    token = create_access_token(user_id=user["id"], email=user["email"])
    return {"access_token": token}
