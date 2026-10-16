"""«Артефакты»: shop collectibles (models/monetization.py Artifact), each
meant for the player's club or for «Мой игрок». A player may own many
copies of one artifact and give copies to friends, but only ONE copy of an
artifact can be active (copies never stack) and at most
GameConfig.artifact_slots copies in total; everything else stands on the
shelf for show. Effects are small and capped on the sum of what is active
(artifact_max_opp_pct / artifact_max_stat):

Club («Карьера тренера», career_service):
- opp_home_pct — the opponent is N% weaker in your home matches;
- team_boost_pct — your team plays N% stronger.
«Мой игрок»:
- attack / defense — +N in every match (my_player_service.match_stats);
- opp_home_pct — the opponent is N% weaker in home matches of «Карьера
  игрока» (player_career_service._play_round);
- xp_bonus_pct / freshness_regen — same as «Имущество».

An artifact tied to a stadium (`stadium_id`) uses `stadium_effect_value`
instead when its owner also has a card of that stadium."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import NotificationType, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import Artifact, UserArtifact
from app.models.stadium import Stadium
from app.models.user import User
from app.models.user_stadium_card import UserStadiumCard
from app.services.game_config_service import get_config
from app.services.wallet_service import debit_coins, lock_user_for_update

TARGETS = {"club": "Для клуба", "my_player": "Для Моего игрока"}
# effect code -> label template ({v} = value).
EFFECTS = {
    "none": "",
    "opp_home_pct": "−{v}% к силе соперника в домашних матчах",
    "team_boost_pct": "+{v}% к силе команды",
    "attack": "+{v} к атаке",
    "defense": "+{v} к защите",
    "xp_bonus_pct": "+{v}% опыта",
    "freshness_regen": "+{v} свежести в час",
}
# Which effects make sense for which target.
TARGET_EFFECTS = {
    "club": {"none", "opp_home_pct", "team_boost_pct"},
    "my_player": {"none", "opp_home_pct", "attack", "defense", "xp_bonus_pct", "freshness_regen"},
}
_PCT_EFFECTS = {"opp_home_pct", "team_boost_pct"}
_STAT_EFFECTS = {"attack", "defense"}


def label(effect: str, value: int) -> str:
    template = EFFECTS.get(effect or "none", "")
    return template.format(v=value) if template and value > 0 else ""


async def _stadium_ids(db: AsyncSession, user_id: int) -> set[int]:
    rows = await db.execute(select(UserStadiumCard.stadium_id).where(UserStadiumCard.user_id == user_id).distinct())
    return {r[0] for r in rows.all()}


def _value(artifact: Artifact, stadiums: set[int]) -> int:
    if artifact.stadium_id and artifact.stadium_id in stadiums and artifact.stadium_effect_value > 0:
        return artifact.stadium_effect_value
    return artifact.effect_value


def _cap(effect: str, total: int, config: GameConfig) -> int:
    if effect in _PCT_EFFECTS:
        return min(total, config.artifact_max_opp_pct)
    if effect in _STAT_EFFECTS:
        return min(total, config.artifact_max_stat)
    return total


async def _copies(db: AsyncSession, user_id: int) -> list[UserArtifact]:
    return list((await db.execute(
        select(UserArtifact).where(UserArtifact.user_id == user_id).order_by(UserArtifact.id)
    )).scalars())


async def effects_of(
    db: AsyncSession, user_id: int, target: str = "my_player", config: Optional[GameConfig] = None,
) -> dict[str, int]:
    """Summed, capped effects of the active artifacts for `target` ({} when off)."""
    config = config or await db.get(GameConfig, 1)
    if config is None or not config.artifacts_enabled:
        return {}
    active = (await db.execute(
        select(UserArtifact).join(Artifact, Artifact.id == UserArtifact.artifact_id)
        .where(UserArtifact.user_id == user_id, UserArtifact.equipped.is_(True), Artifact.target == target)
    )).scalars().all()
    if not active:
        return {}
    stadiums = await _stadium_ids(db, user_id)
    totals: dict[str, int] = {}
    seen: set[int] = set()
    for row in active:
        a = row.artifact
        if a.id in seen or a.effect == "none":  # one copy per artifact, never stacked
            continue
        seen.add(a.id)
        totals[a.effect] = totals.get(a.effect, 0) + _value(a, stadiums)
    return {k: _cap(k, v, config) for k, v in totals.items() if v > 0}


def _artifact_out(a: Artifact, stadium_name: Optional[str], stadiums: set[int]) -> dict:
    return {
        "id": a.id, "name": a.name, "description": a.description, "image_path": a.image_path, "icon": a.icon,
        "rarity": a.rarity, "target": a.target, "target_label": TARGETS.get(a.target, ""),
        "effect": a.effect, "effect_value": a.effect_value, "effect_label": label(a.effect, a.effect_value),
        "stadium_id": a.stadium_id, "stadium_name": stadium_name,
        "stadium_label": label(a.effect, a.stadium_effect_value) if a.stadium_id and a.stadium_effect_value else "",
        "stadium_owned": bool(a.stadium_id and a.stadium_id in stadiums),
        "active_label": label(a.effect, _value(a, stadiums)),
        "coins_price": a.coins_price, "stars_price": a.stars_price,
        "max_supply": a.max_supply, "left": None if a.max_supply is None else max(0, a.max_supply - a.sold_count),
    }


async def _stadium_names(db: AsyncSession, artifacts) -> dict[int, str]:
    ids = {a.stadium_id for a in artifacts if a.stadium_id}
    if not ids:
        return {}
    rows = await db.execute(select(Stadium.id, Stadium.display_name).where(Stadium.id.in_(ids)))
    return {i: n for i, n in rows.all()}


async def catalog(db: AsyncSession, user: User) -> dict:
    """Shop (active artifacts), the shelf (every owned copy) and the active
    effects per target."""
    config = await get_config(db)
    if not config.artifacts_enabled:
        return {"enabled": False, "slots": config.artifact_slots, "active_count": 0, "shop": [], "shelf": [],
                "effects": {"club": [], "my_player": []}, "balance": user.balance}
    copies = await _copies(db, user.id)
    shop = (await db.execute(
        select(Artifact).where(Artifact.is_active.is_(True)).order_by(Artifact.sort_order, Artifact.id)
    )).scalars().all()
    names = await _stadium_names(db, [*shop, *(c.artifact for c in copies)])
    stadiums = await _stadium_ids(db, user.id)
    owned_count: dict[int, int] = {}
    for c in copies:
        owned_count[c.artifact_id] = owned_count.get(c.artifact_id, 0) + 1
    effects = {}
    for target in TARGETS:
        totals = await effects_of(db, user.id, target, config)
        effects[target] = [{"effect": k, "value": v, "label": label(k, v)} for k, v in totals.items()]
    return {
        "enabled": True,
        "slots": config.artifact_slots,
        "active_count": sum(1 for c in copies if c.equipped),
        "shop": [{**_artifact_out(a, names.get(a.stadium_id), stadiums), "owned_count": owned_count.get(a.id, 0)}
                 for a in shop],
        "shelf": [
            {
                "copy_id": c.id, "serial_number": c.serial_number, "equipped": c.equipped, "source": c.source,
                "artifact": _artifact_out(c.artifact, names.get(c.artifact.stadium_id), stadiums),
            }
            for c in sorted(copies, key=lambda c: (not c.equipped, c.artifact.sort_order, c.artifact_id, c.serial_number))
        ],
        "effects": effects,
        "balance": user.balance,
    }


def _check_enabled(config: GameConfig) -> None:
    if not config.artifacts_enabled:
        raise ConflictError("Артефакты сейчас недоступны")


async def _lock_artifact(db: AsyncSession, artifact_id: int) -> Artifact:
    artifact = (await db.execute(
        select(Artifact).where(Artifact.id == artifact_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if artifact is None:
        raise NotFoundError("Артефакт не найден")
    return artifact


def _check_buyable(artifact: Optional[Artifact]) -> Artifact:
    if artifact is None:
        raise NotFoundError("Артефакт не найден")
    if not artifact.is_active:
        raise ConflictError("Этот артефакт не продаётся")
    if artifact.max_supply is not None and artifact.sold_count >= artifact.max_supply:
        raise ConflictError("Тираж этого артефакта распродан")
    return artifact


def _can_activate(copies: list[UserArtifact], artifact_id: int, slots: int) -> bool:
    active = [c for c in copies if c.equipped]
    return len(active) < slots and all(c.artifact_id != artifact_id for c in active)


async def grant(db: AsyncSession, user_id: int, artifact_id: int, source: str, *, force_supply: bool = False) -> UserArtifact:
    """Gives one new numbered copy (serial = sale order; the artifact row is
    locked so serials are unique and max_supply holds). It goes straight
    into an active slot when one is free and no copy of it is active yet;
    otherwise onto the shelf. The caller commits."""
    artifact = await _lock_artifact(db, artifact_id)
    if not force_supply and artifact.max_supply is not None and artifact.sold_count >= artifact.max_supply:
        raise ConflictError("Тираж этого артефакта распродан")
    artifact.sold_count += 1
    if artifact.max_supply is not None and artifact.sold_count > artifact.max_supply:
        artifact.max_supply = artifact.sold_count  # a paid order that raced the last copy
    config = await get_config(db)
    row = UserArtifact(
        user_id=user_id, artifact_id=artifact.id, serial_number=artifact.sold_count, source=source,
        equipped=_can_activate(await _copies(db, user_id), artifact.id, config.artifact_slots),
    )
    db.add(row)
    await db.flush()
    return row


async def buy_with_coins(db: AsyncSession, user: User, artifact_id: int) -> dict:
    config = await get_config(db)
    _check_enabled(config)
    locked = await lock_user_for_update(db, user.id)
    artifact = _check_buyable(await _lock_artifact(db, artifact_id))
    if artifact.coins_price <= 0:
        raise ConflictError("Этот артефакт продаётся только за звёзды")
    await debit_coins(
        db, locked, artifact.coins_price, TransactionType.artifact_purchase, f"Артефакт «{artifact.name}»",
        related_object_type="artifact", related_object_id=artifact.id,
    )
    await grant(db, locked.id, artifact.id, "coins")
    await db.commit()
    await db.refresh(locked)
    return await catalog(db, locked)


async def _own_copy(db: AsyncSession, user_id: int, copy_id: int) -> UserArtifact:
    row = (await db.execute(
        select(UserArtifact).where(UserArtifact.id == copy_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if row is None or row.user_id != user_id:
        raise NotFoundError("Этого артефакта у тебя нет")
    return row


async def set_active(db: AsyncSession, user: User, copy_id: int, active: bool) -> dict:
    """Puts a copy into an active slot (or back on the shelf). The user row
    lock serializes a player's own slot changes."""
    config = await get_config(db)
    _check_enabled(config)
    await lock_user_for_update(db, user.id)
    row = await _own_copy(db, user.id, copy_id)
    if active and not row.equipped:
        copies = await _copies(db, user.id)
        if any(c.equipped and c.artifact_id == row.artifact_id for c in copies):
            raise ConflictError("Копия этого артефакта уже активна — копии не суммируются")
        if sum(1 for c in copies if c.equipped) >= config.artifact_slots:
            raise ConflictError(f"Активных артефактов может быть не больше {config.artifact_slots} — сначала убери один на полку")
    row.equipped = active
    await db.commit()
    return await catalog(db, user)


async def gift(db: AsyncSession, user: User, copy_id: int, recipient_id: int) -> dict:
    """Gives one owned copy to a friend; it lands on their shelf (or in a
    free slot) and they get a notification."""
    from app.services import friend_service
    from app.services.notification_service import notify

    _check_enabled(await get_config(db))
    if recipient_id == user.id:
        raise ConflictError("Нельзя подарить самому себе")
    if recipient_id not in await friend_service.friend_ids(db, user.id):
        raise ForbiddenError("Дарить артефакты можно только друзьям")
    first, second = sorted((user.id, recipient_id))
    await lock_user_for_update(db, first)
    await lock_user_for_update(db, second)
    row = await _own_copy(db, user.id, copy_id)
    config = await get_config(db)
    row.equipped = False
    row.user_id = recipient_id
    row.gifted_by_id = user.id
    row.source = "gift"
    theirs = [c for c in await _copies(db, recipient_id) if c.id != row.id]
    row.equipped = _can_activate(theirs, row.artifact_id, config.artifact_slots)
    await notify(
        db, recipient_id, NotificationType.admin_message, "Тебе подарили артефакт",
        f"{user.full_display_name()} подарил(а) тебе артефакт «{row.artifact.name}» №{row.serial_number}.",
        related_object_type="user_artifact", related_object_id=row.id,
    )
    await db.commit()
    return await catalog(db, user)


# --- Stars ("artifact:<id>", see shop_product_service) ---------------------------------


async def stars_order(db: AsyncSession, user: User, artifact_id: int) -> tuple[str, int, str, str]:
    _check_enabled(await get_config(db))
    artifact = _check_buyable(await db.get(Artifact, artifact_id))
    if artifact.stars_price <= 0:
        raise ConflictError("Этот артефакт продаётся только за монеты")
    effect = label(artifact.effect, artifact.effect_value)
    return (
        f"artifact:{artifact.id}", artifact.stars_price, artifact.name,
        f"Артефакт ({TARGETS.get(artifact.target, '').lower()}){': ' + effect if effect else ''}. "
        + (artifact.description or ""),
    )


async def validate_stars(db: AsyncSession, user_id: int, artifact_id: int, stars_amount: int) -> tuple[bool, str]:
    if not (await get_config(db)).artifacts_enabled:
        return False, "Артефакты сейчас недоступны"
    artifact = await db.get(Artifact, artifact_id)
    if artifact is None or artifact.stars_price != stars_amount:
        return False, "Этот артефакт больше не продаётся"
    try:
        _check_buyable(artifact)
    except (ConflictError, NotFoundError) as exc:
        return False, exc.message
    return True, ""


async def deliver_stars(db: AsyncSession, user: User, artifact_id: int) -> dict:
    """Already paid: a copy is delivered even if the edition sold out in
    the meantime (pre-checkout enforces the supply). The caller commits."""
    row = await grant(db, user.id, artifact_id, "stars", force_supply=True)
    artifact = await db.get(Artifact, artifact_id)
    return {"kind": "artifact", "name": artifact.name if artifact else "Артефакт", "serial_number": row.serial_number}


# --- admin ----------------------------------------------------------------------------


def admin_out(a: Artifact) -> dict:
    return {
        "id": a.id, "name": a.name, "description": a.description, "image_path": a.image_path, "icon": a.icon,
        "rarity": a.rarity, "target": a.target, "effect": a.effect, "effect_value": a.effect_value,
        "stadium_id": a.stadium_id, "stadium_effect_value": a.stadium_effect_value, "coins_price": a.coins_price,
        "stars_price": a.stars_price, "max_supply": a.max_supply, "sold_count": a.sold_count, "is_active": a.is_active,
        "sort_order": a.sort_order,
    }


async def admin_list(db: AsyncSession) -> list[dict]:
    rows = (await db.execute(select(Artifact).order_by(Artifact.sort_order, Artifact.id))).scalars().all()
    return [admin_out(a) for a in rows]


async def admin_save(db: AsyncSession, data: dict, artifact_id: Optional[int] = None) -> dict:
    target = data.get("target", "my_player")
    if target not in TARGETS:
        raise ConflictError("Неизвестное назначение")
    if data.get("effect", "none") not in TARGET_EFFECTS[target]:
        raise ConflictError(f"Этот эффект не подходит для назначения «{TARGETS[target]}»")
    if data.get("stadium_id") and await db.get(Stadium, data["stadium_id"]) is None:
        raise ConflictError("Стадион не найден")
    if artifact_id is None:
        artifact = Artifact()
        db.add(artifact)
    else:
        artifact = await db.get(Artifact, artifact_id)
        if artifact is None:
            raise NotFoundError("Артефакт не найден")
    for key, value in data.items():
        setattr(artifact, key, value)
    await db.commit()
    await db.refresh(artifact)
    return admin_out(artifact)


async def admin_grant(db: AsyncSession, artifact_id: int, user_id: int) -> dict:
    if await db.get(User, user_id) is None:
        raise NotFoundError("Игрок не найден")
    row = await grant(db, user_id, artifact_id, "admin", force_supply=True)
    await db.commit()
    return {"user_id": user_id, "artifact_id": artifact_id, "serial_number": row.serial_number}
