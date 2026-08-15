import os
from pathlib import Path

import httpx
from fastapi import Depends, FastAPI, Request, Response, status
from fastapi.responses import RedirectResponse
from fastapi.staticfiles import StaticFiles
from minio.error import MinioException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from starlette.middleware.trustedhost import TrustedHostMiddleware
from urllib3.exceptions import HTTPError as Urllib3Error

from app.assets import router as assets_router
from app.auth import router as auth_router
from app.database import get_db
from app.documents import router as documents_router
from app.events import router as events_router
from app.ledger import LedgerClient, get_ledger_client, ledger_enabled
from app.ledger import router as ledger_router
from app.storage import ObjectStorage, get_storage
from app.telemetry import router as telemetry_router


STATIC_DIR = Path(__file__).parent / "static"
PUBLIC_DEMO = os.getenv("PUBLIC_DEMO_VIEWER", "false").lower() == "true"
app = FastAPI(
    title="FieldLedger API",
    version="0.6.0",
    description="Integridad de activos, mantenimiento y verificación con Fabric.",
    docs_url=None if PUBLIC_DEMO else "/docs",
    redoc_url=None if PUBLIC_DEMO else "/redoc",
    openapi_url=None if PUBLIC_DEMO else "/openapi.json",
)
app.add_middleware(
    TrustedHostMiddleware,
    allowed_hosts=[
        host.strip()
        for host in os.getenv(
            "TRUSTED_HOSTS", "127.0.0.1,localhost,testserver,api"
        ).split(",")
        if host.strip()
    ],
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")
app.include_router(telemetry_router, prefix="/api/v1")
app.include_router(ledger_router, prefix="/api/v1")


@app.middleware("http")
async def protect_web_ui(request: Request, call_next):
    response = await call_next(request)
    if request.url.path == "/" or request.url.path.startswith("/app"):
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; connect-src 'self'; img-src 'self' data:; "
            "style-src 'self'; script-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'; form-action 'self'"
        )
        response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "DENY"
    return response


@app.get("/health", tags=["health"])
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/ready", tags=["health"])
def ready(
    response: Response,
    db: Session = Depends(get_db),
    storage: ObjectStorage = Depends(get_storage),
    ledger: LedgerClient = Depends(get_ledger_client),
) -> dict[str, str]:
    try:
        db.execute(text("SELECT 1"))
        storage.ensure_bucket()
        if ledger_enabled():
            ledger.ready()
    except (
        SQLAlchemyError,
        MinioException,
        Urllib3Error,
        httpx.HTTPError,
        OSError,
        RuntimeError,
    ):
        response.status_code = status.HTTP_503_SERVICE_UNAVAILABLE
        return {"status": "not_ready"}
    return {"status": "ready"}


@app.get("/", include_in_schema=False)
def web_root() -> RedirectResponse:
    return RedirectResponse(url="/app/")


app.mount("/app", StaticFiles(directory=STATIC_DIR, html=True), name="web")
