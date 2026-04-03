from datetime import datetime, timedelta, timezone
from jose import JWTError, jwt
from pwdlib import PasswordHash  # type: ignore
from pwdlib.hashers.bcrypt import BcryptHasher  # type: ignore
from fastapi import HTTPException, status
from database import get_db
from config import settings
import structlog

logger = structlog.get_logger(__name__)

pwd_context = PasswordHash((BcryptHasher(),))


# ─── Password Utilities ───────────────────────────────────────────────────────

def hash_password(plain: str) -> str:
    return pwd_context.hash(plain)


def verify_password(plain: str, hashed: str) -> bool:
    return pwd_context.verify(plain, hashed)


# ─── JWT Utilities ────────────────────────────────────────────────────────────

def create_access_token(user_id: int, email: str) -> str:
    expire = datetime.now(timezone.utc) + timedelta(
        minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES
    )
    payload = {"sub": str(user_id), "email": email, "exp": expire}
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.ALGORITHM)


def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        return payload
    except JWTError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token.",
            headers={"WWW-Authenticate": "Bearer"},
        )


# ─── User DB Operations ───────────────────────────────────────────────────────

def create_user(email: str, plain_password: str) -> dict:
    log = logger.bind(email=email)
    log.debug("auth.register.attempt")
    hashed = hash_password(plain_password)
    with get_db() as conn:
        with conn.cursor() as cur:
            try:
                cur.execute(
                    """
                    INSERT INTO users (email, hashed_password)
                    VALUES (%s, %s)
                    RETURNING id, email, created_at
                    """,
                    (email, hashed),
                )
                row = cur.fetchone()
                log.info("auth.register.success", user_id=row[0])
                return {"id": row[0], "email": row[1], "created_at": row[2]}
            except Exception as e:
                if "unique" in str(e).lower():
                    log.warning("auth.register.conflict")
                    raise HTTPException(
                        status_code=status.HTTP_409_CONFLICT,
                        detail="A user with this email already exists.",
                    )
                log.error("auth.register.error", exc_info=True)
                raise


def get_user_by_email(email: str) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, hashed_password, created_at FROM users WHERE email = %s",
                (email,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {
                "id": row[0],
                "email": row[1],
                "hashed_password": row[2],
                "created_at": row[3],
            }


def get_user_by_id(user_id: int) -> dict | None:
    with get_db() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, email, created_at FROM users WHERE id = %s",
                (user_id,),
            )
            row = cur.fetchone()
            if not row:
                return None
            return {"id": row[0], "email": row[1], "created_at": row[2]}


def authenticate_user(email: str, plain_password: str) -> dict:
    log = logger.bind(email=email)
    log.debug("auth.login.attempt")
    user = get_user_by_email(email)
    if not user:
        log.warning("auth.login.failed", reason="user_not_found")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    if not verify_password(plain_password, user["hashed_password"]):
        log.warning("auth.login.failed", reason="wrong_password", hash_prefix=user["hashed_password"][:10])
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password.",
        )
    log.info("auth.login.success", user_id=user["id"])
    return user
