from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.monetization import Artifact
from app.models.user import User
from app.schemas.monetization import ArtifactGrantIn, ArtifactIn, CosmeticIn, CosmeticOut, SeasonAdminOut, SeasonIn
from app.services import artifact_service, cosmetic_service, season_pass_service
from app.services.admin_log_service import log_action
from app.services.image_service import delete_artifact_image, save_artifact_image

router = APIRouter(prefix="/admin", tags=["admin"], dependencies=[Depends(get_current_admin)])


def _ip(request: Request):
    return request.client.host if request.client else None


@router.get("/cosmetics", response_model=list[CosmeticOut])
async def list_cosmetics(db: AsyncSession = Depends(get_db)):
    return await cosmetic_service.admin_list(db)


@router.post("/cosmetics", response_model=CosmeticOut)
async def create_cosmetic(
    payload: CosmeticIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await cosmetic_service.admin_create(db, payload)
    await log_action(db, admin.id, "create_cosmetic", "cosmetic", out.id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/cosmetics/{cosmetic_id}", response_model=CosmeticOut)
async def update_cosmetic(
    cosmetic_id: int, payload: CosmeticIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await cosmetic_service.admin_update(db, cosmetic_id, payload)
    await log_action(db, admin.id, "update_cosmetic", "cosmetic", cosmetic_id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.get("/seasons", response_model=list[SeasonAdminOut])
async def list_seasons(db: AsyncSession = Depends(get_db)):
    return await season_pass_service.admin_list(db)


@router.post("/seasons", response_model=SeasonAdminOut)
async def create_season(
    payload: SeasonIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await season_pass_service.admin_create(db, payload)
    await log_action(db, admin.id, "create_season", "season", out.id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/seasons/{season_id}", response_model=SeasonAdminOut)
async def update_season(
    season_id: int, payload: SeasonIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await season_pass_service.admin_update(db, season_id, payload)
    await log_action(db, admin.id, "update_season", "season", season_id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.get("/artifacts")
async def list_artifacts(db: AsyncSession = Depends(get_db)):
    return {
        "artifacts": await artifact_service.admin_list(db), "effects": artifact_service.EFFECTS,
        "targets": artifact_service.TARGETS,
        "target_effects": {k: sorted(v) for k, v in artifact_service.TARGET_EFFECTS.items()},
    }


@router.post("/artifacts")
async def create_artifact(
    payload: ArtifactIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await artifact_service.admin_save(db, payload.model_dump())
    await log_action(db, admin.id, "create_artifact", "artifact", out["id"], new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/artifacts/{artifact_id}")
async def update_artifact(
    artifact_id: int, payload: ArtifactIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await artifact_service.admin_save(db, payload.model_dump(), artifact_id)
    await log_action(db, admin.id, "update_artifact", "artifact", artifact_id, new_value=payload.model_dump(mode="json"),
                     ip_address=_ip(request))
    await db.commit()
    return out


@router.post("/artifacts/{artifact_id}/image")
async def upload_artifact_image(
    artifact_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None:
        raise NotFoundError("Артефакт не найден")
    old_path = artifact.image_path
    artifact.image_path = await save_artifact_image(file, artifact.name)
    delete_artifact_image(old_path)
    await log_action(db, admin.id, "upload_artifact_image", "artifact", artifact_id,
                     old_value={"image_path": old_path}, new_value={"image_path": artifact.image_path},
                     ip_address=_ip(request))
    await db.commit()
    await db.refresh(artifact)
    return artifact_service.admin_out(artifact)


@router.post("/artifacts/{artifact_id}/grant")
async def grant_artifact(
    artifact_id: int, payload: ArtifactGrantIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await artifact_service.admin_grant(db, artifact_id, payload.user_id)
    await log_action(db, admin.id, "grant_artifact", "artifact", artifact_id, new_value=out, ip_address=_ip(request))
    await db.commit()
    return out
