"""«Табло удачи» — a three-window football scoreboard («777» in spirit, not
in look). Same monetization shape as «21: Добавленное время»:
config.lucky_board_free_per_day free spins a day, then spins bought for
Telegram Stars one at a time (shop product "lucky_board:1" through the
regular StarsInvoice → deliver_payment flow, at most
config.lucky_board_paid_daily_limit a local day) and banked on the user.

Guard rails (agreed with the owner, they keep it away from gambling):
- no stakes: the price of a spin is fixed, there is nothing to raise;
- paid-spin prizes are account-bound only — skill tokens, shards (N → one
  token), the board's cosmetics and badge. Never coins or cards, which can
  leave the account (trades, auction, club market, selling);
  `validate_outcomes` refuses an admin table that breaks this;
- the odds are open: `status` returns the exact percentages of the very
  table `_roll` uses.

Everything random happens here, under the user row lock, in one
transaction with the attempt it spends. A retried spin with the same
Idempotency-Key returns the stored spin (UNIQUE (user_id, idempotency_key)).
"""
import random
from datetime import datetime, time, timedelta, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.badge import Badge, UserBadge
from app.models.enums import TransactionType
from app.models.game_config import GameConfig
from app.models.lucky_board import LuckyBoardSpin
from app.models.monetization import Cosmetic
from app.models.pack import StarsInvoice
from app.models.user import User
from app.schemas.badge import BadgeOut
from app.schemas.lucky_board import (
    LuckyBoardOutcomeOut, LuckyBoardPrizeOut, LuckyBoardSideOut, LuckyBoardSpinOut, LuckyBoardStatusOut,
    LuckyBoardTokenOut,
)
from app.schemas.monetization import CosmeticOut
from app.services import card_skill_service, cosmetic_service
from app.services.card_skill_catalog import SKILL_DEFINITIONS
from app.services.game_config_service import get_config
from app.services.wallet_service import credit_coins, lock_user_for_update

PRODUCT = "lucky_board:1"
RELATED = "lucky_board_spin"
SYMBOLS = ("ball", "boot", "glove", "cup", "flag", "whistle")
# Triple outcomes show their own symbol three times.
TRIPLES = ("cup", "ball", "glove", "boot")
OUTCOME_CODES = (*TRIPLES, "pair", "miss")
SIDES = ("free", "paid")
PRIZE_KEYS = ("coins", "tokens", "shards", "cosmetic")

_rng = random.SystemRandom()


# --- Day / hour counters ---------------------------------------------------


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _next_local_midnight_utc() -> datetime:
    tomorrow = local_today() + timedelta(days=1)
    return datetime.combine(tomorrow, time.min, tzinfo=app_timezone()).astimezone(timezone.utc)


def _is_today(moment: Optional[datetime]) -> bool:
    return moment is not None and local_today(moment) == local_today()


def _today_counters(user: User) -> tuple[int, int]:
    """(free used, paid bought) today without mutating the user."""
    if not _is_today(user.lucky_board_day_reset_at):
        return 0, 0
    return user.lucky_board_free_used_today, user.lucky_board_paid_bought_today


def _ensure_daily_reset(db: AsyncSession, user: User) -> None:
    if not _is_today(user.lucky_board_day_reset_at):
        user.lucky_board_free_used_today = 0
        user.lucky_board_paid_bought_today = 0
        user.lucky_board_day_reset_at = _now()
        db.add(user)


def _hour_window_open(user: User) -> bool:
    started = user.lucky_board_hour_started_at
    return started is None or _now() - ensure_aware(started) >= timedelta(hours=1)


def _hourly_remaining(user: User, limit: int) -> int:
    """Spins left this hour; a limit of 0 means no hourly cap (reported as 0)."""
    if limit <= 0:
        return 0
    if _hour_window_open(user):
        return limit
    return max(0, limit - user.lucky_board_hourly_attempts)


def _take_hourly_attempt(db: AsyncSession, user: User, limit: int) -> None:
    if limit <= 0:
        return  # no hourly cap
    if _hour_window_open(user):
        user.lucky_board_hourly_attempts = 0
        user.lucky_board_hour_started_at = _now()
    if user.lucky_board_hourly_attempts >= limit:
        remaining = timedelta(hours=1) - (_now() - ensure_aware(user.lucky_board_hour_started_at))
        raise ConflictError(
            "Табло остывает — лимит запусков на этот час исчерпан",
            details={
                "reason": "hourly_limit", "hourly_limit": limit,
                "retry_after_seconds": max(0, int(remaining.total_seconds())),
            },
        )
    user.lucky_board_hourly_attempts += 1
    db.add(user)


def _require_enabled(config: GameConfig) -> None:
    if not config.lucky_board_enabled:
        raise ConflictError("«Табло удачи» сейчас недоступно", details={"reason": "disabled"})


# --- The table ---------------------------------------------------------------


def _side(raw: object) -> dict:
    raw = raw if isinstance(raw, dict) else {}
    return {
        "coins": int(raw.get("coins") or 0), "tokens": int(raw.get("tokens") or 0),
        "shards": int(raw.get("shards") or 0), "cosmetic": bool(raw.get("cosmetic")),
    }


def validate_outcomes(raw: object) -> list[dict]:
    """Admin input → the normalized table. Exactly the six outcomes, weights
    >= 0 with a positive total per side, and a paid side that never pays
    coins (paid prizes must stay on the account). Raises ValueError."""
    if not isinstance(raw, list):
        raise ValueError("ожидается список исходов")
    by_code: dict[str, dict] = {}
    for item in raw:
        if not isinstance(item, dict) or item.get("code") not in OUTCOME_CODES:
            raise ValueError(f"неизвестный исход: {item!r}")
        code = item["code"]
        if code in by_code:
            raise ValueError(f"исход «{code}» указан дважды")
        row = {"code": code, "label": str(item.get("label") or code)[:32]}
        for side in SIDES:
            weight = int(item.get(f"{side}_weight") or 0)
            if weight < 0:
                raise ValueError(f"вес не может быть отрицательным ({code})")
            row[f"{side}_weight"] = weight
            prize = _side(item.get(side))
            if any(prize[k] < 0 for k in ("coins", "tokens", "shards")):
                raise ValueError(f"приз не может быть отрицательным ({code})")
            row[side] = prize
        if row["paid"]["coins"]:
            raise ValueError("платный спин не может давать монеты — только жетоны, осколки и косметику")
        if row["free"]["cosmetic"]:
            raise ValueError("косметика табло — только приз платного спина")
        by_code[code] = row
    missing = [c for c in OUTCOME_CODES if c not in by_code]
    if missing:
        raise ValueError("не хватает исходов: " + ", ".join(missing))
    for side in SIDES:
        if sum(r[f"{side}_weight"] for r in by_code.values()) <= 0:
            raise ValueError(f"сумма весов ({side}) должна быть больше нуля")
    return [by_code[c] for c in OUTCOME_CODES]


def _table(config: GameConfig) -> list[dict]:
    try:
        return validate_outcomes(config.lucky_board_outcomes)
    except ValueError:
        from app.models.game_config import LUCKY_BOARD_DEFAULT_OUTCOMES

        return validate_outcomes(LUCKY_BOARD_DEFAULT_OUTCOMES)


def odds(table: list[dict], side: str) -> dict[str, float]:
    total = sum(r[f"{side}_weight"] for r in table)
    return {r["code"]: (r[f"{side}_weight"] / total if total else 0.0) for r in table}


def _roll(table: list[dict], side: str) -> dict:
    return _rng.choices(table, weights=[r[f"{side}_weight"] for r in table], k=1)[0]


def reels_for(code: str) -> list[str]:
    """Three symbols that show `code`: a triple, exactly two alike, or all
    three different."""
    if code in TRIPLES:
        return [code] * 3
    if code == "pair":
        a, b = _rng.sample(SYMBOLS, 2)
        reels = [a, a, b]
        _rng.shuffle(reels)
        return reels
    return _rng.sample(SYMBOLS, 3)


# --- Status ------------------------------------------------------------------


async def _bound_prize_pool(db: AsyncSession, config: GameConfig, user_id: int) -> list[tuple[str, int]]:
    """Pool cosmetics (active) and the badge the player doesn't own yet."""
    pool: list[tuple[str, int]] = []
    ids = [int(i) for i in (config.lucky_board_cosmetic_ids or []) if isinstance(i, (int, str)) and str(i).isdigit()]
    if ids:
        owned = await cosmetic_service.owned_ids(db, user_id)
        rows = (await db.execute(select(Cosmetic.id).where(Cosmetic.id.in_(ids), Cosmetic.is_active.is_(True)))).scalars()
        pool += [("cosmetic", cid) for cid in rows if cid not in owned]
    if config.lucky_board_badge_id:
        badge = await db.get(Badge, config.lucky_board_badge_id)
        has = (await db.execute(select(UserBadge.id).where(
            UserBadge.user_id == user_id, UserBadge.badge_id == config.lucky_board_badge_id,
        ))).first()
        if badge is not None and not has:
            pool.append(("badge", badge.id))
    return pool


async def get_status(db: AsyncSession, user: User, config: Optional[GameConfig] = None) -> LuckyBoardStatusOut:
    config = config or await get_config(db)
    table = _table(config)
    free_used, paid_bought = _today_counters(user)
    free_odds, paid_odds = odds(table, "free"), odds(table, "paid")
    hourly_remaining = _hourly_remaining(user, config.lucky_board_hourly_limit)
    hour_resets_at = None
    if config.lucky_board_hourly_limit > 0 and hourly_remaining == 0 and user.lucky_board_hour_started_at is not None:
        hour_resets_at = ensure_aware(user.lucky_board_hour_started_at) + timedelta(hours=1)
    return LuckyBoardStatusOut(
        enabled=config.lucky_board_enabled,
        free_per_day=config.lucky_board_free_per_day,
        free_remaining=max(0, config.lucky_board_free_per_day - free_used),
        paid_spins=user.lucky_board_paid_spins,
        paid_bought_today=paid_bought,
        paid_daily_limit=config.lucky_board_paid_daily_limit,
        stars_cost=config.lucky_board_stars_cost,
        hourly_limit=config.lucky_board_hourly_limit,
        hourly_remaining=hourly_remaining,
        hour_resets_at=hour_resets_at,
        shards=user.lucky_board_shards,
        shards_per_token=config.lucky_board_shards_per_token,
        next_reset_at=_next_local_midnight_utc(),
        symbols=list(SYMBOLS),
        outcomes=[
            LuckyBoardOutcomeOut(
                code=r["code"], label=r["label"], symbol=r["code"] if r["code"] in TRIPLES else None,
                free_pct=round(free_odds[r["code"]] * 100, 2), paid_pct=round(paid_odds[r["code"]] * 100, 2),
                free=LuckyBoardSideOut(**r["free"]), paid=LuckyBoardSideOut(**r["paid"]),
            )
            for r in table
        ],
        cosmetics_left=len(await _bound_prize_pool(db, config, user.id)),
    )


# --- Spinning ----------------------------------------------------------------


async def _random_skill_code(db: AsyncSession) -> str:
    table = await card_skill_service.pack_token_drop_table(db)
    if not table:
        raise ConflictError("Жетоны навыков сейчас недоступны", details={"reason": "no_skills"})
    return card_skill_service.pick_pack_token(table)[0]


def _merge(tokens: list[dict], code: str, quantity: int) -> None:
    for t in tokens:
        if t["skill_code"] == code:
            t["quantity"] += quantity
            return
    tokens.append({"skill_code": code, "quantity": quantity})


async def _grant(
    db: AsyncSession, config: GameConfig, user: User, spin: LuckyBoardSpin, row: dict,
) -> dict:
    """Pays `row`'s prize for spin.source inside the caller's transaction
    (user row locked). Returns the snapshot stored on the spin."""
    side = row[spin.source]
    prize: dict = {"coins": 0, "tokens": [], "shards": 0, "crafted_tokens": [], "cosmetic_id": None,
                   "badge_id": None, "blocked": False}
    if spin.source == "free" and user.game_rewards_blocked:
        prize["blocked"] = True
        return prize
    reason = f"«Табло удачи»: {row['label']}"

    if spin.source == "free" and side["coins"] > 0:
        await credit_coins(
            db, user, side["coins"], TransactionType.lucky_board_reward, reason,
            related_object_type=RELATED, related_object_id=spin.id,
        )
        prize["coins"] = side["coins"]

    if side["tokens"] > 0:
        code = await _random_skill_code(db)
        await card_skill_service.grant_tokens(
            db, user, code, side["tokens"], "grant_lucky_board",
            related_object_type=RELATED, related_object_id=spin.id, reason=reason,
        )
        _merge(prize["tokens"], code, side["tokens"])

    shards = side["shards"]
    if side["cosmetic"] and spin.source == "paid":
        pool = await _bound_prize_pool(db, config, user.id)
        if pool:
            kind, item_id = _rng.choice(pool)
            if kind == "cosmetic":
                await cosmetic_service.grant(db, user.id, item_id, "lucky_board")
                prize["cosmetic_id"] = item_id
            else:
                db.add(UserBadge(user_id=user.id, badge_id=item_id))
                user.active_badge_id = item_id
                prize["badge_id"] = item_id
            shards = 0  # the shards are the fallback for a full collection

    if shards > 0:
        prize["shards"] = shards
        user.lucky_board_shards += shards
        per_token = config.lucky_board_shards_per_token
        while per_token > 0 and user.lucky_board_shards >= per_token:
            user.lucky_board_shards -= per_token
            code = await _random_skill_code(db)
            await card_skill_service.grant_tokens(
                db, user, code, 1, "grant_lucky_board",
                related_object_type=RELATED, related_object_id=spin.id, reason="«Табло удачи»: осколки собраны в жетон",
            )
            _merge(prize["crafted_tokens"], code, 1)
    db.add(user)
    return prize


def _tokens_out(raw: list) -> list[LuckyBoardTokenOut]:
    out = []
    for t in raw or []:
        definition = SKILL_DEFINITIONS.get(t["skill_code"])
        out.append(LuckyBoardTokenOut(
            skill_code=t["skill_code"], skill_name=definition.name if definition else t["skill_code"],
            skill_icon=definition.icon if definition else "✨", quantity=int(t["quantity"]),
        ))
    return out


async def _spin_out(db: AsyncSession, config: GameConfig, user: User, spin: LuckyBoardSpin) -> LuckyBoardSpinOut:
    raw = spin.prize or {}
    cosmetic = await db.get(Cosmetic, raw["cosmetic_id"]) if raw.get("cosmetic_id") else None
    badge = await db.get(Badge, raw["badge_id"]) if raw.get("badge_id") else None
    labels = {r["code"]: r["label"] for r in _table(config)}
    return LuckyBoardSpinOut(
        id=spin.id, source=spin.source, outcome=spin.outcome, label=labels.get(spin.outcome, spin.outcome),
        reels=list(spin.reels),
        prize=LuckyBoardPrizeOut(
            coins=int(raw.get("coins") or 0), tokens=_tokens_out(raw.get("tokens")),
            shards=int(raw.get("shards") or 0), crafted_tokens=_tokens_out(raw.get("crafted_tokens")),
            cosmetic=CosmeticOut.model_validate(cosmetic) if cosmetic else None,
            badge=BadgeOut.model_validate(badge) if badge else None,
            blocked=bool(raw.get("blocked")),
        ),
        new_balance=user.balance,
        status=await get_status(db, user, config),
    )


async def _spin_by_key(db: AsyncSession, user_id: int, key: str) -> Optional[LuckyBoardSpin]:
    return (await db.execute(select(LuckyBoardSpin).where(
        LuckyBoardSpin.user_id == user_id, LuckyBoardSpin.idempotency_key == key,
    ))).scalar_one_or_none()


def _consume_spin(config: GameConfig, user: User) -> str:
    if user.lucky_board_free_used_today < config.lucky_board_free_per_day:
        user.lucky_board_free_used_today += 1
        return "free"
    if user.lucky_board_paid_spins > 0:
        user.lucky_board_paid_spins -= 1
        return "paid"
    raise ConflictError(
        "Запуски на сегодня закончились",
        details={"reason": "no_spins", "next_reset_at": _next_local_midnight_utc().isoformat()},
    )


async def spin(db: AsyncSession, user: User, idempotency_key: Optional[str] = None) -> LuckyBoardSpinOut:
    """Spends one spin (free first, then a bought one) and pays its prize —
    all in one transaction under the user row lock."""
    config = await get_config(db)
    _require_enabled(config)
    key = (idempotency_key or "").strip()[:64] or None
    locked = await lock_user_for_update(db, user.id)

    if key is not None:
        existing = await _spin_by_key(db, locked.id, key)
        if existing is not None:
            return await _spin_out(db, config, locked, existing)

    _ensure_daily_reset(db, locked)
    _take_hourly_attempt(db, locked, config.lucky_board_hourly_limit)
    source = _consume_spin(config, locked)

    table = _table(config)
    row = _roll(table, source)
    spin_row = LuckyBoardSpin(
        user_id=locked.id, source=source, outcome=row["code"], reels=reels_for(row["code"]), prize={},
        idempotency_key=key,
    )
    db.add(spin_row)
    try:
        await db.flush()
    except IntegrityError:
        # Same key raced past the check (only without real row locks).
        await db.rollback()
        existing = await _spin_by_key(db, user.id, key) if key else None
        if existing is None:
            raise
        fresh = await db.get(User, user.id)
        return await _spin_out(db, config, fresh, existing)

    spin_row.prize = await _grant(db, config, locked, spin_row, row)
    db.add(spin_row)
    await db.commit()
    return await _spin_out(db, config, locked, spin_row)


# --- Stars (shop product "lucky_board:1") -------------------------------------


async def stars_order(db: AsyncSession, user: User) -> tuple[str, int, str, str]:
    config = await get_config(db)
    _require_enabled(config)
    if config.lucky_board_paid_daily_limit <= 0 or config.lucky_board_stars_cost <= 0:
        raise ConflictError("Платные запуски сейчас не продаются")
    _, paid_bought = _today_counters(user)
    if paid_bought >= config.lucky_board_paid_daily_limit:
        raise ConflictError(
            "Лимит платных запусков на сегодня исчерпан",
            details={"reason": "paid_limit", "next_reset_at": _next_local_midnight_utc().isoformat()},
        )
    return (
        PRODUCT, config.lucky_board_stars_cost, "«Табло удачи»: запуск",
        "Один запуск «Табло удачи». Призы платного запуска — жетоны навыков, осколки и косметика табло; "
        "они остаются на твоём аккаунте. Шансы указаны в игре.",
    )


async def validate_stars(db: AsyncSession, invoice: StarsInvoice) -> tuple[bool, str]:
    """pre_checkout_query: the last chance to refuse before Telegram charges,
    so the daily cap and the price are checked here (delivery never refuses)."""
    config = await get_config(db)
    if not config.lucky_board_enabled or config.lucky_board_paid_daily_limit <= 0:
        return False, "«Табло удачи» сейчас недоступно"
    if invoice.stars_amount != config.lucky_board_stars_cost:
        return False, "Цена изменилась — открой табло заново"
    user = await db.get(User, invoice.user_id)
    if user is None:
        return False, "Unknown order"
    _, paid_bought = _today_counters(user)
    if paid_bought >= config.lucky_board_paid_daily_limit:
        return False, "Лимит платных запусков на сегодня исчерпан"
    return True, ""


async def deliver_stars(db: AsyncSession, user: User) -> dict:
    """Banks one bought spin. Runs under stars_payment_service's invoice row
    lock + completed_at check (once per invoice). The caller commits."""
    locked = await lock_user_for_update(db, user.id)
    _ensure_daily_reset(db, locked)
    locked.lucky_board_paid_bought_today += 1
    locked.lucky_board_paid_spins += 1
    db.add(locked)
    return {"kind": "lucky_board", "paid_spins": locked.lucky_board_paid_spins}


# --- Admin estimate -------------------------------------------------------------


def expected_value(config: GameConfig) -> dict[str, dict[str, float]]:
    """Per side: average coins, skill tokens (shards counted at
    1/shards_per_token, the cosmetic outcome counted as its fallback shards)."""
    table = _table(config)
    per_token = config.lucky_board_shards_per_token or 0
    out = {}
    for side in SIDES:
        p = odds(table, side)
        coins = sum(p[r["code"]] * r[side]["coins"] for r in table)
        shards = sum(p[r["code"]] * r[side]["shards"] for r in table)
        tokens = sum(p[r["code"]] * r[side]["tokens"] for r in table)
        cosmetic = sum(p[r["code"]] for r in table if r[side]["cosmetic"])
        out[side] = {
            "coins": round(coins, 2), "tokens": round(tokens + (shards / per_token if per_token else 0), 3),
            "shards": round(shards, 3), "cosmetic_chance": round(cosmetic, 4),
        }
    return out
