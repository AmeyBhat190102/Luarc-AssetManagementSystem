from fastapi import FastAPI
from contextlib import asynccontextmanager
from database import init_pool, close_pool
from auth.router import router as auth_router
from assets.router import router as assets_router
from logging_config import setup_logging
import structlog

setup_logging()
log = structlog.get_logger()


@asynccontextmanager
async def lifespan(app: FastAPI):
    log.info("app.startup")
    init_pool()
    yield
    close_pool()
    log.info("app.shutdown")


app = FastAPI(
    title="Asset Management API",
    description="Coupon/voucher management with JWT auth and concurrency-safe claiming.",
    version="1.0.0",
    lifespan=lifespan,
)

app.include_router(auth_router)
app.include_router(assets_router)


@app.get("/health", tags=["Health"])
def health_check():
    log.debug("health check called")
    return {"status": "ok"}
