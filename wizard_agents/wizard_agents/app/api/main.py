"""FastAPI application entrypoint for the Wizard Agent System."""
from __future__ import annotations

from fastapi import FastAPI

from app.api.routes_explorer import router as explorer_router
from app.api.routes_health import router as health_router
from app.api.routes_verification import router as verification_router

app = FastAPI(
    title="Wizard Agent System",
    description="Explorer and Verification agents for the Wizard investigation pipeline.",
    version="0.1.0",
)

app.include_router(health_router)
app.include_router(explorer_router)
app.include_router(verification_router)
