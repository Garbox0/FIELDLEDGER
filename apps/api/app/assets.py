from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.auth import get_current_user, require_roles
from app.database import get_db
from app.ledger import enqueue
from app.models import AppRole, Asset, Organization, User
from app.schemas import AssetCreate, AssetRead, AssetUpdate


router = APIRouter(prefix="/assets", tags=["assets"])


def get_asset_or_404(asset_id: str, db: Session) -> Asset:
    asset = db.get(Asset, asset_id)
    if asset is None:
        raise HTTPException(status_code=404, detail="Asset not found")
    return asset


@router.post("", response_model=AssetRead, status_code=status.HTTP_201_CREATED)
def create_asset(
    payload: AssetCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Asset:
    asset = Asset(**payload.model_dump())
    organization = db.get(Organization, current_user.organization_id)
    if organization is None:
        raise HTTPException(status_code=409, detail="User organization is missing")
    db.add(asset)
    enqueue(
        db,
        operation_id=f"asset:{asset.asset_id}:create",
        aggregate_type="ASSET",
        aggregate_id=asset.asset_id,
        action="REGISTER_ASSET",
        organization=organization.name,
        payload={
            "assetId": asset.asset_id,
            "assetType": asset.asset_type,
            "name": asset.name,
            "site": asset.site,
            "serialNumber": asset.serial_number,
        },
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(status_code=409, detail="Asset already exists") from exc
    db.refresh(asset)
    return asset


@router.get("", response_model=list[AssetRead])
def list_assets(
    offset: int = Query(default=0, ge=0),
    limit: int = Query(default=100, ge=1, le=500),
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> list[Asset]:
    statement = select(Asset).order_by(Asset.asset_id).offset(offset).limit(limit)
    return list(db.scalars(statement))


@router.get("/{asset_id}", response_model=AssetRead)
def get_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(get_current_user),
) -> Asset:
    return get_asset_or_404(asset_id, db)


@router.patch("/{asset_id}", response_model=AssetRead)
def update_asset(
    asset_id: str,
    payload: AssetUpdate,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Asset:
    asset = get_asset_or_404(asset_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(asset, field, value)
    asset.updated_at = datetime.now(UTC)
    db.commit()
    db.refresh(asset)
    return asset


@router.delete("/{asset_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_asset(
    asset_id: str,
    db: Session = Depends(get_db),
    _current_user: User = Depends(require_roles(AppRole.ADMIN, AppRole.OPERATOR)),
) -> Response:
    db.delete(get_asset_or_404(asset_id, db))
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        raise HTTPException(
            status_code=409, detail="Assets with events cannot be deleted"
        ) from exc
    return Response(status_code=status.HTTP_204_NO_CONTENT)
