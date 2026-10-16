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
- attack / defense / match_rating — +N in every match (my_player_service.match_stats);
- skill_level — his card skill plays N levels higher (max level 3);
- shot_pp — his shots miss N percentage points less often, and dribble_pp —
  he wins N pp more stage-1 duels («обыгрыш 1 на 1») — both read by the
  match engine from the engine card's `boosts` («Карьера игрока»);
- opp_home_pct — the opponent is N% weaker in home matches of «Карьера
  игрока» (player_career_service._play_round);
- xp_bonus_pct / freshness_regen — same as «Имущество».

An artifact linked to a stadium, coach or player (`link_type`/`link_id`)
uses `link_effect_value` instead when its owner has a card of it (the
«This is Anfield» plaque + Энфилд, Ferguson's board + coach Ferguson).
Independently, `card_player_id` + `card_rating_bonus` add rating to every
card of that player in the owner's «Карьера тренера» squad (Maradona's
shirt → +3 to the owner's Maradona cards); see `card_bonuses`."""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.models.enums import NotificationType, TransactionType
from app.models.game_config import GameConfig
from app.models.card import UserCard
from app.models.coach import Coach
from app.models.monetization import Artifact, UserArtifact
from app.models.player import Player
from app.models.stadium import Stadium
from app.models.user import User
from app.models.user_coach_card import UserCoachCard
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
    "match_rating": "+{v} к рейтингу в матче",
    "skill_level": "+{v} к уровню навыка",
    "shot_pp": "+{v}% к точности удара",
    "dribble_pp": "+{v}% к обыгрышу 1 на 1",
    "xp_bonus_pct": "+{v}% опыта",
    "freshness_regen": "+{v} свежести в час",
}
# Which effects make sense for which target.
TARGET_EFFECTS = {
    "club": {"none", "opp_home_pct", "team_boost_pct"},
    "my_player": {
        "none", "opp_home_pct", "attack", "defense", "match_rating", "skill_level", "shot_pp", "dribble_pp",
        "xp_bonus_pct", "freshness_regen",
    },
}
_PCT_EFFECTS = {"opp_home_pct", "team_boost_pct", "shot_pp", "dribble_pp"}
_STAT_EFFECTS = {"attack", "defense", "match_rating", "skill_level"}


def label(effect: str, value: int) -> str:
    template = EFFECTS.get(effect or "none", "")
    return template.format(v=value) if template and value > 0 else ""


LINK_TYPES = {"stadium": "стадион", "coach": "тренер", "player": "игрок"}
_LINK_MODELS = {"stadium": (Stadium, Stadium.display_name), "coach": (Coach, Coach.display_name),
                "player": (Player, Player.display_name)}


async def _owned_links(db: AsyncSession, user_id: int, artifacts) -> dict[str, set[int]]:
    """Which of the linked stadiums / coaches / players the user has a card of."""
    wanted: dict[str, set[int]] = {}
    for a in artifacts:
        if a.link_type and a.link_id:
            wanted.setdefault(a.link_type, set()).add(a.link_id)
    owned: dict[str, set[int]] = {}
    for kind, ids in wanted.items():
        column, owner = {
            "stadium": (UserStadiumCard.stadium_id, UserStadiumCard.user_id),
            "coach": (UserCoachCard.coach_id, UserCoachCard.user_id),
            "player": (UserCard.player_id, UserCard.owner_id),
        }[kind]
        rows = await db.execute(select(column).where(owner == user_id, column.in_(ids)).distinct())
        owned[kind] = {r[0] for r in rows.all()}
    return owned


def _linked(artifact: Artifact, owned: dict[str, set[int]]) -> bool:
    return bool(artifact.link_type and artifact.link_id in owned.get(artifact.link_type, set()))


def _value(artifact: Artifact, owned: dict[str, set[int]]) -> int:
    if _linked(artifact, owned) and artifact.link_effect_value > 0:
        return artifact.link_effect_value
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


async def _active_artifacts(db: AsyncSession, user_id: int, target: Optional[str] = None) -> list[Artifact]:
    """One Artifact per active artifact (a second active copy never counts)."""
    query = (
        select(UserArtifact).join(Artifact, Artifact.id == UserArtifact.artifact_id)
        .where(UserArtifact.user_id == user_id, UserArtifact.equipped.is_(True))
    )
    if target is not None:
        query = query.where(Artifact.target == target)
    unique: dict[int, Artifact] = {}
    for row in (await db.execute(query)).scalars().all():
        unique.setdefault(row.artifact_id, row.artifact)
    return list(unique.values())


async def effects_of(
    db: AsyncSession, user_id: int, target: str = "my_player", config: Optional[GameConfig] = None,
) -> dict[str, int]:
    """Summed, capped effects of the active artifacts for `target` ({} when off)."""
    config = config or await db.get(GameConfig, 1)
    if config is None or not config.artifacts_enabled:
        return {}
    active = [a for a in await _active_artifacts(db, user_id, target) if a.effect != "none"]
    if not active:
        return {}
    owned = await _owned_links(db, user_id, active)
    totals: dict[str, int] = {}
    for a in active:
        totals[a.effect] = totals.get(a.effect, 0) + _value(a, owned)
    return {k: _cap(k, v, config) for k, v in totals.items() if v > 0}


async def card_bonuses(db: AsyncSession, user_id: int, config: Optional[GameConfig] = None) -> dict[int, int]:
    """{player_id: +rating} for the owner's cards, from active artifacts'
    card_player_id / card_rating_bonus (summed per player, capped)."""
    config = config or await db.get(GameConfig, 1)
    if config is None or not config.artifacts_enabled:
        return {}
    totals: dict[int, int] = {}
    for a in await _active_artifacts(db, user_id):
        if a.card_player_id and a.card_rating_bonus > 0:
            totals[a.card_player_id] = totals.get(a.card_player_id, 0) + a.card_rating_bonus
    return {pid: min(v, config.artifact_max_stat) for pid, v in totals.items()}


def _artifact_out(a: Artifact, names: dict, owned: dict[str, set[int]]) -> dict:
    link_name = names.get((a.link_type, a.link_id)) if a.link_type else None
    card_player = names.get(("player", a.card_player_id)) if a.card_player_id else None
    return {
        "id": a.id, "name": a.name, "description": a.description, "image_path": a.image_path, "icon": a.icon,
        "rarity": a.rarity, "target": a.target, "target_label": TARGETS.get(a.target, ""),
        "effect": a.effect, "effect_value": a.effect_value, "effect_label": label(a.effect, a.effect_value),
        "link_type": a.link_type, "link_kind": LINK_TYPES.get(a.link_type or "", ""), "link_name": link_name,
        "link_label": label(a.effect, a.link_effect_value) if a.link_type and a.link_effect_value else "",
        "link_owned": _linked(a, owned),
        "card_player_name": card_player,
        "card_label": f"+{a.card_rating_bonus} к рейтингу карточек «{card_player}»"
        if card_player and a.card_rating_bonus else "",
        "active_label": label(a.effect, _value(a, owned)),
        "coins_price": a.coins_price, "stars_price": a.stars_price,
        "max_supply": a.max_supply, "left": None if a.max_supply is None else max(0, a.max_supply - a.sold_count),
    }


async def _names(db: AsyncSession, artifacts) -> dict[tuple[str, int], str]:
    """Display names of every linked stadium / coach / player."""
    wanted: dict[str, set[int]] = {}
    for a in artifacts:
        if a.link_type and a.link_id:
            wanted.setdefault(a.link_type, set()).add(a.link_id)
        if a.card_player_id:
            wanted.setdefault("player", set()).add(a.card_player_id)
    names: dict[tuple[str, int], str] = {}
    for kind, ids in wanted.items():
        model, column = _LINK_MODELS[kind]
        rows = await db.execute(select(model.id, column).where(model.id.in_(ids)))
        names.update({(kind, i): n for i, n in rows.all()})
    return names


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
    every = [*shop, *(c.artifact for c in copies)]
    names = await _names(db, every)
    owned = await _owned_links(db, user.id, every)
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
        "shop": [{**_artifact_out(a, names, owned), "owned_count": owned_count.get(a.id, 0)} for a in shop],
        "shelf": [
            {
                "copy_id": c.id, "serial_number": c.serial_number, "equipped": c.equipped, "source": c.source,
                "artifact": _artifact_out(c.artifact, names, owned),
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
        "link_type": a.link_type, "link_id": a.link_id, "link_effect_value": a.link_effect_value,
        "card_player_id": a.card_player_id, "card_rating_bonus": a.card_rating_bonus, "coins_price": a.coins_price,
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
    if bool(data.get("link_type")) != bool(data.get("link_id")):
        raise ConflictError("Для связки выбери и тип, и кого именно")
    if data.get("link_type"):
        model, _ = _LINK_MODELS[data["link_type"]]
        if await db.get(model, data["link_id"]) is None:
            raise ConflictError("Связка: такой карточки нет")
    if data.get("card_player_id") and await db.get(Player, data["card_player_id"]) is None:
        raise ConflictError("Игрок для бонуса карточек не найден")
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
