import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from wizard_kernel.api import routes_health, routes_investigations
from wizard_kernel.api.deps import get_manager

log = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    # ── Startup: restore persisted investigations from disk ──────────────────
    manager = get_manager()
    restored = manager.restore()
    log.info("kernel ready — %d investigations restored from disk", restored)
    if restored == 0:
        log.info("(no prior investigations found — clean start)")
    log.warning(
        "MULTI-WORKER NOTICE: run with --workers 1 (default). "
        "State is in-process + disk. Multi-worker needs a shared store."
    )
    yield
    # ── Shutdown ─────────────────────────────────────────────────────────────


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
