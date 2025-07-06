"""Main FastAPI application module."""

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.api.health_check import router as health_router
from app.config.settings import settings
from app.db.init_db import close_engine, init_models


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncGenerator[None, None]:
    """Manage application lifespan events."""
    # Startup
    if settings.environment == "development":
        await init_models()
    yield
    # Shutdown
    await close_engine()


app = FastAPI(
    title="Project Backend",
    version="0.1.0",
    description="Backend service with health-check endpoint",
    validate_response=True, #type validation of pydantic output
    lifespan=lifespan,
)

app.include_router(health_router)

