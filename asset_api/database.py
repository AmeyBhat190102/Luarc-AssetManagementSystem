from contextlib import contextmanager
from threading import Semaphore
from psycopg2.pool import ThreadedConnectionPool # type: ignore
from config import settings
import structlog

logger = structlog.get_logger(__name__)

# Initialized at app startup via init_pool()
_pool: ThreadedConnectionPool | None = None
_semaphore: Semaphore | None = None


def init_pool():
    """Call once at application startup."""
    global _pool, _semaphore

    logger.info("db.pool.init", min_conn=settings.DB_MIN_CONN, max_conn=settings.DB_MAX_CONN)
    _pool = ThreadedConnectionPool(
        minconn=settings.DB_MIN_CONN,
        maxconn=settings.DB_MAX_CONN,
        dsn=settings.DATABASE_URL,
    )
    # Semaphore caps concurrent checkouts to DB_MAX_CONN.
    # Threads beyond that limit block here instead of crashing
    # with "connection pool exhausted".
    _semaphore = Semaphore(settings.DB_MAX_CONN)
    logger.info("db.pool.ready")


def close_pool():
    """Call on application shutdown."""
    global _pool, _semaphore
    if _pool:
        _pool.closeall()
        _pool = None
        _semaphore = None
        logger.info("db.pool.closed")


@contextmanager
def get_db():
    """
    Context manager that checks out a connection from the pool,
    yields it, and handles commit/rollback/return automatically.

    A semaphore gates entry so threads block and wait for a free
    connection rather than crashing with pool exhausted errors.

    Usage:
        with get_db() as conn:
            with conn.cursor() as cur:
                cur.execute(...)
    """
    if _pool is None or _semaphore is None:
        raise RuntimeError("Connection pool is not initialized. Call init_pool() first.")

    _semaphore.acquire()
    conn = _pool.getconn()
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        _pool.putconn(conn)
        _semaphore.release()
