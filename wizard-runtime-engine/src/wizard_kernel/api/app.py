from contextlib import asynccontextmanager
from fastapi import FastAPI
from wizard_kernel.api import routes_health, routes_investigations


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield  # Phase 3+: startup / teardown hooks


def create_app() -> FastAPI:
    app = FastAPI(
        title="Wizard Investigation Kernel",
        version="0.1.0",
        description="Evidence-driven runtime for autonomous repository verification.",
        lifespan=lifespan,
    )
    app.include_router(routes_health.router)
    app.include_router(routes_investigations.router)
    return app


app = create_app()
