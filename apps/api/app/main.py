import httpx
from fastapi import Depends, FastAPI, Response, status
from minio.error import MinioException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from urllib3.exceptions import HTTPError as Urllib3Error

from app.assets import router as assets_router
from app.auth import router as auth_router
from app.database import get_db
from app.documents import router as documents_router
from app.events import router as events_router
from app.ledger import LedgerClient, get_ledger_client, ledger_enabled
from app.storage import ObjectStorage, get_storage


app = FastAPI(
    title="FieldLedger API",
    version="0.3.0",
    description="Asset integrity, maintenance, off-chain evidence, and Fabric verification.",
)
app.include_router(auth_router, prefix="/api/v1")
app.include_router(assets_router, prefix="/api/v1")
app.include_router(events_router, prefix="/api/v1")
app.include_router(documents_router, prefix="/api/v1")


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
