from fastapi import APIRouter, Depends, File, Request, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependencies import get_current_admin
from app.core.exceptions import NotFoundError
from app.database import get_db
from app.models.monetization import Artifact
from app.models.user import User
from app.schemas.monetization import ArtifactGrantIn, ArtifactIn, ArtifactTopGiftIn, CosmeticIn, CosmeticOut, SeasonAdminOut, SeasonIn
from app.schemas.club_emblem import ClubEmblemItemIn, ClubEmblemItemOut
from app.schemas.club_quest import ClubQuestAdminOut, ClubQuestIn
from app.schemas.club_reward import ClubShopItemAdminOut, ClubShopItemIn
from app.services import (
    artifact_service,
    club_emblem_service,
    club_quest_service,
    club_shop_service,
    cosmetic_service,
    season_pass_service,
)
from app.services.admin_log_service import log_action
from app.services.image_service import (
    delete_artifact_image,
    delete_cosmetic_image,
    save_artifact_image,
    save_cosmetic_image,
)

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


@router.post("/cosmetics/{cosmetic_id}/image", response_model=CosmeticOut)
async def upload_cosmetic_image(
    cosmetic_id: int, request: Request, file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    path = await save_cosmetic_image(file, f"cosmetic-{cosmetic_id}")
    out, old = await cosmetic_service.admin_set_image(db, cosmetic_id, path)
    await log_action(db, admin.id, "upload_cosmetic_image", "cosmetic", cosmetic_id, new_value={"image_path": path},
                     ip_address=_ip(request))
    await db.commit()
    if old and old != path:
        delete_cosmetic_image(old)
    return out


@router.delete("/cosmetics/{cosmetic_id}/image", response_model=CosmeticOut)
async def delete_cosmetic_image_endpoint(
    cosmetic_id: int, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out, old = await cosmetic_service.admin_set_image(db, cosmetic_id, None)
    await log_action(db, admin.id, "delete_cosmetic_image", "cosmetic", cosmetic_id, ip_address=_ip(request))
    await db.commit()
    delete_cosmetic_image(old)
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


@router.post("/artifacts/{artifact_id}/gift-top-donors")
async def gift_artifact_to_top_donors(
    artifact_id: int, payload: ArtifactTopGiftIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await artifact_service.gift_to_top_donors(db, artifact_id, payload.top, payload.message)
    await log_action(db, admin.id, "gift_artifact_top_donors", "artifact", artifact_id,
                     new_value={**payload.model_dump(), **out}, ip_address=_ip(request))
    await db.commit()
    return out


# --- club emblem constructor catalog ---------------------------------------------------


@router.get("/club-emblem-items", response_model=list[ClubEmblemItemOut])
async def list_club_emblem_items(db: AsyncSession = Depends(get_db)):
    return await club_emblem_service.admin_list(db)


@router.put("/club-emblem-items/{item_id}", response_model=ClubEmblemItemOut)
async def update_club_emblem_item(
    item_id: int, payload: ClubEmblemItemIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await club_emblem_service.admin_update(db, item_id, payload)
    await log_action(db, admin.id, "update_club_emblem_item", "club_emblem_item", item_id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


# --- «Клубный магазин» ----------------------------------------------------------------


@router.get("/club-shop-items", response_model=list[ClubShopItemAdminOut])
async def list_club_shop_items(db: AsyncSession = Depends(get_db)):
    return await club_shop_service.admin_list(db)


@router.post("/club-shop-items", response_model=ClubShopItemAdminOut)
async def create_club_shop_item(
    payload: ClubShopItemIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await club_shop_service.admin_save(db, None, payload)
    await log_action(db, admin.id, "create_club_shop_item", "club_shop_item", out.id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/club-shop-items/{item_id}", response_model=ClubShopItemAdminOut)
async def update_club_shop_item(
    item_id: int, payload: ClubShopItemIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await club_shop_service.admin_save(db, item_id, payload)
    await log_action(db, admin.id, "update_club_shop_item", "club_shop_item", item_id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


# --- «Задания недели» клуба ---------------------------------------------------------


@router.get("/club-quests", response_model=list[ClubQuestAdminOut])
async def list_club_quests(db: AsyncSession = Depends(get_db)):
    return await club_quest_service.admin_list(db)


@router.post("/club-quests", response_model=ClubQuestAdminOut)
async def create_club_quest(
    payload: ClubQuestIn, request: Request, db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await club_quest_service.admin_save(db, None, payload)
    await log_action(db, admin.id, "create_club_quest", "club_quest_template", out.id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out


@router.put("/club-quests/{template_id}", response_model=ClubQuestAdminOut)
async def update_club_quest(
    template_id: int, payload: ClubQuestIn, request: Request,
    db: AsyncSession = Depends(get_db), admin: User = Depends(get_current_admin),
):
    out = await club_quest_service.admin_save(db, template_id, payload)
    await log_action(db, admin.id, "update_club_quest", "club_quest_template", template_id,
                     new_value=payload.model_dump(mode="json"), ip_address=_ip(request))
    await db.commit()
    return out
