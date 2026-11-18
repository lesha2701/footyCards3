"""«Воспитанник Академии»: the life around the growing child
(prospect_service holds the core — age, rating, XP, purchases):

- talents: one pick from three at each of `spec_stages` (effects in
  GameConfig spec_effects: more XP of a kind, attack / defense);
- graduation at the last stage: the rating freezes (`final_rating`), the
  row turns "graduate" — he plays «Менеджер» as subject "graduate" — the
  owner gets `graduation_coins` and may start the next generation of the
  dynasty (+potential); the previous graduate retires to the hall;
- «Турнир набора»: the cohort (start week) competes by XP of each ISO week,
  `week_prizes` coins to the top, settled once (ledger key week:<week>);
- friends' duels in «Ответка» (ProspectDuel): each side plays its own match
  until `duel_hours`; the better result gets `duel_win_xp`, one who played
  against one who did not wins by walkover;
- gifts to a friend's prospect and the birthday box (Stars, delivered by
  prospect_service.deliver_stars_invoice);
- the bot's evening digest (sweep), once a day per user (ledger key
  notice:<day>);
- other game modes he may play (Пенальти, Штрафной, 1 на 1): `award_game`.

Every number comes from prospect_service.cfg (GameConfig.prospect).
"""
import hashlib
from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, or_, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import app_timezone, ensure_aware, local_today
from app.models.academy_prospect import AcademyProspect, ProspectDuel, ProspectLedger
from app.models.enums import NotificationType, TransactionType
from app.models.user import User
from app.services import prospect_service as ps
from app.services.game_config_service import get_config
from app.services.notification_service import notify
from app.services.wallet_service import credit_coins, lock_user_for_update

RELATED = "prospect"


def _name(user: Optional[User]) -> str:
    return (user.first_name or user.username or "Игрок") if user else "Игрок"


def _pick(seed: str, n: int) -> int:
    return int(hashlib.sha256(seed.encode()).hexdigest(), 16) % max(1, n)


# --- talents -------------------------------------------------------------------------------

def spec_picks_allowed(p: AcademyProspect, c: dict, today: date) -> int:
    stage = ps.stage_of(p, c, today)
    return sum(1 for s in c["spec_stages"] if stage >= int(s))


def spec_options(p: AcademyProspect, c: dict, today: date) -> list[str]:
    """Three talents to choose from when a pick is due, else []."""
    taken = list(p.specs or [])
    if len(taken) >= spec_picks_allowed(p, c, today):
        return []
    free = [code for code in ps.SPECS if code not in taken]
    out: list[str] = []
    seed = f"{p.id}:{len(taken)}"
    while free and len(out) < 3:
        out.append(free.pop(_pick(f"{seed}:{len(out)}", len(free))))
    return out


def _spec_out(code: str, c: dict) -> dict:
    return {"code": code, **ps.SPECS[code], "effects": dict(c["spec_effects"].get(code) or {})}


async def choose_spec(db: AsyncSession, user: User, code: str) -> dict:
    c = ps.cfg(await get_config(db))
    ps._require_enabled(c)
    p = await ps._locked(db, user.id)
    today = local_today()
    if code not in spec_options(p, c, today):
        raise ConflictError("Этот талант сейчас не выбрать")
    p.specs = [*(p.specs or []), code]
    flag_modified(p, "specs")
    ps._remember(p, today, f"spec:{code}", f"{ps.SPECS[code]['emoji']} Талант: {ps.SPECS[code]['name']}")
    db.add(p)
    await db.commit()
    return await ps.get_view(db, await db.get(User, user.id))


# --- graduation / dynasty / hall --------------------------------------------------------------

def can_graduate(p: AcademyProspect, c: dict, today: date) -> bool:
    return p.status == ps.GROWING and ps.stage_of(p, c, today) >= len(ps.STAGES) - 1


def _graduate_out(g: AcademyProspect, owner: Optional[User] = None) -> dict:
    return {
        "id": g.id, "name": g.name, "number": g.number, "position": g.position.value, "appearance": g.appearance or {},
        "rating": g.final_rating, "potential": g.potential, "generation": g.generation, "status": g.status,
        "graduated_at": ensure_aware(g.graduated_at).isoformat() if g.graduated_at else None,
        "specs": [{"code": code, **ps.SPECS[code]} for code in (g.specs or []) if code in ps.SPECS],
        "stats": {k: v for k, v in (g.stats or {}).items() if k != "stories"},
        "background": (g.cosmetics or {}).get("background") or "bg_yard",
        "owner": _name(owner) if owner is not None else None, "user_id": g.user_id,
    }


async def graduate(db: AsyncSession, user: User) -> dict:
    """«Выпускной»: freezes the rating, pays the owner, frees the slot for the
    next generation. The previous graduate retires; «Менеджер» moves his
    contracts over (manager_service.on_graduation)."""
    from app.services import manager_service

    config = await get_config(db)
    c = ps.cfg(config)
    ps._require_enabled(c)
    locked = await lock_user_for_update(db, user.id)
    p = await ps._locked(db, user.id)
    today = local_today()
    if not can_graduate(p, c, today):
        raise ConflictError(f"Выпускной — на ступени «{ps.STAGES[-1]['name']}»")
    reason = await manager_service.graduation_block(db, user.id)
    if reason:
        raise ConflictError(reason)
    now = datetime.now(timezone.utc)
    old = await ps.get_prospect(db, user.id, ps.GRADUATE)
    if old is not None:
        await manager_service.on_graduation(db, user.id, retired=True, now=now, carry=False)
        old.status = ps.RETIRED
        old.market_open = False
        db.add(old)
        await db.flush()
    await ps.refresh_academy_peak(db, p, config, c)
    p.status = ps.GRADUATE
    p.final_rating = ps.rating_of(p, c, today)
    p.graduated_at = now
    ps._remember(p, today, "graduation", f"🎓 Выпускной: рейтинг {p.final_rating}")
    db.add(p)
    await db.flush()
    await manager_service.on_graduation(db, user.id, retired=False, now=now)
    coins = int(c["graduation_coins"])
    if coins > 0:
        await credit_coins(db, locked, coins, TransactionType.game_reward, f"Выпускной воспитанника {p.name}",
                           related_object_type=RELATED, related_object_id=p.id)
    db.add_all([locked, ProspectLedger(user_id=user.id, kind="graduation", code=str(p.final_rating), coins=coins,
                                      idempotency_key=f"graduation:{p.id}")])
    await db.commit()
    return await ps.get_view(db, await db.get(User, user.id))


async def hall(db: AsyncSession, user_id: int, limit: int = 20) -> dict:
    mine = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status != ps.GROWING)
        .order_by(AcademyProspect.graduated_at.desc())
    )).scalars().all()
    top = (await db.execute(
        select(AcademyProspect, User).join(User, User.id == AcademyProspect.user_id)
        .where(AcademyProspect.status != ps.GROWING, User.is_banned.is_(False))
        .order_by(AcademyProspect.final_rating.desc(), AcademyProspect.graduated_at)
        .limit(limit)
    )).all()
    return {"mine": [_graduate_out(g) for g in mine], "top": [_graduate_out(g, u) for g, u in top]}


# --- «Турнир набора» (weekly XP of the cohort) ------------------------------------------------

def _xp_in(p: AcademyProspect, key: str) -> int:
    if p.week_key == key:
        return p.week_xp
    if p.last_week_key == key:
        return p.last_week_xp
    return 0


async def _cohort_rows(db: AsyncSession, p: AcademyProspect) -> list[AcademyProspect]:
    key = ps.cohort_key(p.created_at)
    start, end = ps._week_bounds(p.created_at)
    rows = (await db.execute(select(AcademyProspect).where(
        AcademyProspect.created_at >= start, AcademyProspect.created_at < end, AcademyProspect.status == ps.GROWING,
    ))).scalars().all()
    return [r for r in rows if ps.cohort_key(r.created_at) == key]


def _ranked(rows: list[AcademyProspect], key: str) -> list[AcademyProspect]:
    return sorted((r for r in rows if _xp_in(r, key) > 0), key=lambda r: (-_xp_in(r, key), r.user_id))


async def settle_week(db: AsyncSession, p: AcademyProspect, c: dict, today: date) -> int:
    """Pays the last finished week of this prospect's cohort (once per
    winner: ledger week:<week>). Returns how many prizes went out now."""
    prev = ps.week_key(today - timedelta(days=7))
    if ps.week_key(local_today(ensure_aware(p.created_at))) > prev:
        return 0  # the cohort started after that week
    prizes = [int(x) for x in c["week_prizes"]]
    paid = 0
    for place, row in enumerate(_ranked(await _cohort_rows(db, p), prev)[: len(prizes)], start=1):
        coins = prizes[place - 1]
        try:
            async with db.begin_nested():
                db.add(ProspectLedger(user_id=row.user_id, kind="week", code=prev, coins=coins, idempotency_key=f"week:{prev}"))
                await db.flush()
        except IntegrityError:
            continue
        winner = await lock_user_for_update(db, row.user_id)
        if coins > 0:
            await credit_coins(db, winner, coins, TransactionType.game_reward, f"Турнир набора {prev}: {place} место",
                               related_object_type=RELATED, related_object_id=row.id)
        await notify(db, row.user_id, NotificationType.prospect_event, f"🏆 Турнир набора: {place} место",
                     f"{row.name} — {place}-й по опыту за неделю в своём наборе. Приз: {coins} монет.",
                     related_object_type=RELATED, related_object_id=row.id)
        paid += 1
    return paid


async def week_out(db: AsyncSession, p: AcademyProspect, c: dict, today: date) -> dict:
    key = ps.week_key(today)
    rows = await _cohort_rows(db, p)
    ranked = _ranked(rows, key)
    owners = {u.id: u for u in (await db.execute(select(User).where(User.id.in_([r.user_id for r in ranked[:10]] or [0])))).scalars()}
    place = next((i + 1 for i, r in enumerate(ranked) if r.user_id == p.user_id), None)
    return {
        "key": key, "days_left": 7 - today.weekday(), "prizes": [int(x) for x in c["week_prizes"]],
        "my_xp": _xp_in(p, key), "place": place, "size": len(rows),
        "top": [{"place": i + 1, "name": r.name, "owner": _name(owners.get(r.user_id)), "xp": _xp_in(r, key),
                 "me": r.user_id == p.user_id} for i, r in enumerate(ranked[:10])],
    }


# --- duels ------------------------------------------------------------------------------------

async def _expire_duels(db: AsyncSession, now: datetime, user_id: Optional[int] = None) -> int:
    q = select(ProspectDuel).where(ProspectDuel.status == "open", ProspectDuel.expires_at < now)
    if user_id is not None:
        q = q.where(or_(ProspectDuel.challenger_id == user_id, ProspectDuel.opponent_id == user_id))
    done = 0
    for duel in (await db.execute(q.with_for_update(skip_locked=True))).scalars().all():
        await _settle_duel(db, duel, now, expired=True)
        done += 1
    return done


def _key(result: Optional[dict]) -> tuple:
    if not result:
        return (-1, -99, -99)
    return (int(bool(result.get("won"))), int(result["for"]) - int(result["against"]), int(result["for"]))


async def _settle_duel(db: AsyncSession, duel: ProspectDuel, now: datetime, expired: bool = False) -> None:
    c = ps.cfg(await get_config(db))
    a, b = _key(duel.challenger_result), _key(duel.opponent_result)
    winner = None
    if a > b and duel.challenger_result:
        winner = duel.challenger_id
    elif b > a and duel.opponent_result:
        winner = duel.opponent_id
    duel.winner_id = winner
    duel.status = "expired" if expired else "done"
    duel.settled_at = now
    db.add(duel)
    names = {}
    for uid in (duel.challenger_id, duel.opponent_id):
        pr = await ps.get_prospect(db, uid)
        names[uid] = pr.name if pr else "Воспитанник"
    xp = 0
    if winner is not None:
        p = (await db.execute(
            select(AcademyProspect).where(AcademyProspect.user_id == winner, AcademyProspect.status == ps.GROWING)
            .with_for_update().execution_options(populate_existing=True)
        )).scalar_one_or_none()
        if p is not None:
            config = await get_config(db)
            xp = ps.grant_xp(p, int(c["duel_win_xp"]), c, local_today(), await ps.bonus_pct(db, p, config, c), capped=False)
            stats = ps._stats(p)
            stats["duel_wins"] = int(stats.get("duel_wins", 0)) + 1
            ps._set_stats(p, stats)
            ps._remember(p, local_today(), "duel_win", "⚔️ Первая победа в дуэли с другом")
            db.add(p)

    def score(r: Optional[dict]) -> str:
        return f"{r['for']}:{r['against']}" if r else "не сыграл"

    line = f"{names[duel.challenger_id]} {score(duel.challenger_result)} · {names[duel.opponent_id]} {score(duel.opponent_result)}"
    for uid in (duel.challenger_id, duel.opponent_id):
        title = "⚔️ Дуэль: победа!" if uid == winner else "⚔️ Дуэль: ничья" if winner is None else "⚔️ Дуэль проиграна"
        body = line + (f". +{xp} опыта" if uid == winner and xp else "")
        await notify(db, uid, NotificationType.prospect_event, title, body, related_object_type=RELATED, related_object_id=duel.id)


async def create_duel(db: AsyncSession, user: User, opponent_id: int) -> dict:
    from app.services.friend_service import friend_ids

    c = ps.cfg(await get_config(db))
    ps._require_enabled(c)
    await lock_user_for_update(db, user.id)
    if opponent_id == user.id or opponent_id not in set(await friend_ids(db, user.id)):
        raise ConflictError("Вызвать можно только друга")
    mine, theirs = await ps.get_prospect(db, user.id), await ps.get_prospect(db, opponent_id)
    if mine is None:
        raise ConflictError("Сначала создай воспитанника")
    if theirs is None:
        raise ConflictError("У друга нет воспитанника")
    now = datetime.now(timezone.utc)
    await _expire_duels(db, now, user.id)
    pair = or_(
        (ProspectDuel.challenger_id == user.id) & (ProspectDuel.opponent_id == opponent_id),
        (ProspectDuel.challenger_id == opponent_id) & (ProspectDuel.opponent_id == user.id),
    )
    if (await db.execute(select(ProspectDuel.id).where(ProspectDuel.status == "open", pair))).first():
        raise ConflictError("С этим другом дуэль уже идёт")
    since = datetime.combine(local_today(), datetime.min.time(), tzinfo=app_timezone()).astimezone(timezone.utc)
    today_count = (await db.execute(select(func.count(ProspectDuel.id)).where(
        ProspectDuel.challenger_id == user.id, ProspectDuel.created_at >= since,
    ))).scalar_one()
    if today_count >= int(c["duels_per_day"]):
        raise ConflictError(f"Не больше {int(c['duels_per_day'])} вызовов в день")
    duel = ProspectDuel(challenger_id=user.id, opponent_id=opponent_id, expires_at=now + timedelta(hours=int(c["duel_hours"])))
    db.add(duel)
    await db.flush()
    await notify(db, opponent_id, NotificationType.prospect_event, "⚔️ Вызов на дуэль",
                 f"{_name(user)} вызывает {theirs.name} в «Ответку»: {mine.name} против {theirs.name}. "
                 f"Сыграй свой матч за {int(c['duel_hours'])} ч.", related_object_type=RELATED, related_object_id=duel.id)
    await db.commit()
    return {"duel_id": duel.id, "view": await ps.get_view(db, await db.get(User, user.id))}


async def take_duel_side(db: AsyncSession, user_id: int, duel_id: int) -> ProspectDuel:
    """«Ответка» start for a duel: the user's side must still be free. The
    caller sets the side's session id and commits."""
    duel = (await db.execute(
        select(ProspectDuel).where(ProspectDuel.id == duel_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if duel is None:
        raise NotFoundError("Дуэль не найдена")
    if user_id not in (duel.challenger_id, duel.opponent_id):
        raise ForbiddenError("Это не твоя дуэль")
    if duel.status != "open" or ensure_aware(duel.expires_at) < datetime.now(timezone.utc):
        raise ConflictError("Дуэль уже закончилась")
    side = "challenger" if user_id == duel.challenger_id else "opponent"
    if getattr(duel, f"{side}_session_id") is not None:
        raise ConflictError("Свой матч в этой дуэли ты уже начал")
    return duel


def set_duel_session(duel: ProspectDuel, user_id: int, session_id: int) -> None:
    side = "challenger" if user_id == duel.challenger_id else "opponent"
    setattr(duel, f"{side}_session_id", session_id)


async def record_duel(db: AsyncSession, user_id: int, duel_id: int, session_id: int, goals_for: int, goals_against: int,
                      won: bool) -> None:
    """At the «Ответка» claim (under the session lock): the side's result;
    both played → settled. The caller commits."""
    duel = (await db.execute(
        select(ProspectDuel).where(ProspectDuel.id == duel_id).with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if duel is None or duel.status != "open":
        return
    side = "challenger" if user_id == duel.challenger_id else "opponent" if user_id == duel.opponent_id else None
    if side is None or getattr(duel, f"{side}_session_id") != session_id or getattr(duel, f"{side}_result") is not None:
        return
    setattr(duel, f"{side}_result", {"for": int(goals_for), "against": int(goals_against), "won": bool(won)})
    db.add(duel)
    if duel.challenger_result is not None and duel.opponent_result is not None:
        await _settle_duel(db, duel, datetime.now(timezone.utc))


async def _duels_out(db: AsyncSession, user_id: int) -> list[dict]:
    rows = (await db.execute(
        select(ProspectDuel).where(or_(ProspectDuel.challenger_id == user_id, ProspectDuel.opponent_id == user_id))
        .order_by(ProspectDuel.id.desc()).limit(10)
    )).scalars().all()
    others = {r.opponent_id if r.challenger_id == user_id else r.challenger_id for r in rows}
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(others or {0})))).scalars()}
    pros = await ps.prospects_of(db, others)
    out = []
    for r in rows:
        mine_side = "challenger" if r.challenger_id == user_id else "opponent"
        other_side = "opponent" if mine_side == "challenger" else "challenger"
        other = r.opponent_id if mine_side == "challenger" else r.challenger_id
        out.append({
            "id": r.id, "status": r.status, "incoming": mine_side == "opponent", "friend": _name(users.get(other)),
            "friend_prospect": pros[other].name if other in pros else None,
            "mine": getattr(r, f"{mine_side}_result"), "theirs": getattr(r, f"{other_side}_result"),
            "can_play": r.status == "open" and getattr(r, f"{mine_side}_session_id") is None,
            "won": None if r.status == "open" else (r.winner_id == user_id if r.winner_id else None),
            "expires_at": ensure_aware(r.expires_at).isoformat(),
        })
    return out


async def _friends_out(db: AsyncSession, user_id: int, c: dict, today: date) -> list[dict]:
    from app.services.friend_service import friend_ids

    ids = set(await friend_ids(db, user_id))
    pros = await ps.prospects_of(db, ids)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(set(pros) or {0})))).scalars()}
    out = [{"user_id": uid, "owner": _name(users.get(uid)), "name": p.name, "rating": ps.rating_of(p, c, today),
            "age": ps.age_of(ps.age_days(p, today), c), "appearance": p.appearance or {}, "number": p.number}
           for uid, p in pros.items()]
    return sorted(out, key=lambda f: (-f["rating"], f["name"]))


# --- gifts / birthday ------------------------------------------------------------------------

async def deliver_gift(db: AsyncSession, buyer: User, kind: str, recipient_id: int, c: dict) -> None:
    """A friend's gift paid for in Stars; the payment is taken, so the
    friendship is not re-checked. No prospect any more → nothing to give."""
    p = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == recipient_id, AcademyProspect.status == ps.GROWING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if p is None:
        return
    now = datetime.now(timezone.utc)
    if kind == "training":
        p.extra_credits += 1
        what = "доп. тренировку"
    else:
        start = ensure_aware(p.coach_until) if ps.coach_active(p, now) else now
        p.coach_until = start + timedelta(days=int(c["coach_days"]))
        what = f"личного тренера на {int(c['coach_days'])} дн."
    ps._remember(p, local_today(), f"gift:{buyer.id}", f"🎁 Подарок от {_name(buyer)}")
    db.add(p)
    await notify(db, recipient_id, NotificationType.prospect_event, "🎁 Подарок воспитаннику",
                 f"{_name(buyer)} подарил {p.name} {what}", related_object_type=RELATED, related_object_id=p.id)


async def open_bday_box(db: AsyncSession, p: AcademyProspect, c: dict, today: date) -> dict:
    """The birthday box: XP and a cosmetic he doesn't have yet (coin items,
    out of season ones excluded). Once per age (ledger bday:<id>:<age>)."""
    config = await get_config(db)
    age = ps.age_of(ps.age_days(p, today), c)
    xp = ps.grant_xp(p, int(c["bday_xp"]), c, today, await ps.bonus_pct(db, p, config, c), capped=False)
    owned = set((p.cosmetics or {}).get("owned") or []) | {"bg_yard"}
    pool = [code for code, meta in ps.COSMETICS.items() if code not in owned and not meta.get("season")
            and int(c["cosmetics"].get(code, {}).get("coins", 0)) > 0]
    item = pool[_pick(f"bday:{p.id}:{age}", len(pool))] if pool else None
    if item:
        ps._give_cosmetic(p, item)
    ps._remember(p, today, f"bday:{age}", f"🎂 {age} лет: подарок на день рождения")
    db.add_all([p, ProspectLedger(user_id=p.user_id, kind="bday", code=item, idempotency_key=f"bday:{p.id}:{age}")])
    return {"xp": xp, "item": item}


# --- other modes -------------------------------------------------------------------------------

async def award_game(db: AsyncSession, user_id: int, goals: int, won: bool, mode: str) -> int:
    """XP for a rewarded game of Пенальти / Штрафной / 1 на 1 he played (the
    caller holds the session lock; the caller commits)."""
    config = await get_config(db)
    c = ps.cfg(config)
    p = (await db.execute(
        select(AcademyProspect).where(AcademyProspect.user_id == user_id, AcademyProspect.status == ps.GROWING)
        .with_for_update().execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if p is None or not c["enabled"]:
        return 0
    today = local_today()
    base = (ps.with_spec(p, c, "match_pct", int(c["game_match_xp"])) + ps.with_spec(p, c, "goal_pct", int(c["game_goal_xp"])) * max(0, goals)
            + (ps.with_spec(p, c, "win_pct", int(c["game_win_xp"])) if won else 0))
    gained = ps.grant_xp(p, base, c, today, await ps.bonus_pct(db, p, config, c), capped=True)
    stats = ps._stats(p)
    games = dict(stats.get("games") or {})
    games[mode] = int(games.get(mode, 0)) + 1
    stats["games"] = games
    ps._set_stats(p, stats)
    ps._remember(p, today, f"mode:{mode}", {"penalty": "🥅 Первая серия пенальти", "free_kick": "🎯 Первый штрафной",
                                            "one_on_one": "🏃 Первая атака 1 на 1"}.get(mode, "⚽ Новый режим"))
    db.add(p)
    return gained


# --- views ----------------------------------------------------------------------------------

async def view_extras(db: AsyncSession, user: User, c: dict, today: date) -> dict:
    """What the page shows with or without a growing child: the active
    graduate, the hall, duels and friends' prospects."""
    await _expire_duels(db, datetime.now(timezone.utc), user.id)
    await db.commit()
    grad = await ps.get_prospect(db, user.id, ps.GRADUATE)
    generations = (await db.execute(select(func.count(AcademyProspect.id)).where(AcademyProspect.user_id == user.id))).scalar_one()
    return {
        "graduate": _graduate_out(grad) if grad else None,
        "hall": await hall(db, user.id),
        "generations": generations,
        "duels": await _duels_out(db, user.id),
        "friends": await _friends_out(db, user.id, c, today),
        "duel_rules": {"hours": int(c["duel_hours"]), "per_day": int(c["duels_per_day"]), "win_xp": int(c["duel_win_xp"])},
        "gift_stars": {"training": int(c["gift_training_stars"]), "coach": int(c["gift_coach_stars"])},
        "graduation_coins": int(c["graduation_coins"]),
        # «Династия»: + peak rating of the next child (the one after this many).
        "dynasty_bonus": int(c["dynasty_peak_bonus"]),
        "next_dynasty_peak": ps.dynasty_peak(generations + 1, c),
    }


async def prospect_extras(db: AsyncSession, user: User, p: AcademyProspect, c: dict, today: date) -> dict:
    if await settle_week(db, p, c, today):
        await db.commit()
        await db.refresh(p)
    age = ps.age_of(ps.age_days(p, today), c)
    bday_open = ps.is_birthday(p, c, today) and (await db.execute(select(ProspectLedger.id).where(
        ProspectLedger.user_id == user.id, ProspectLedger.idempotency_key == f"bday:{p.id}:{age}",
    ))).scalar_one_or_none() is not None
    options = spec_options(p, c, today)
    return {
        "spec_pick": {"options": [_spec_out(code, c) for code in options], "number": len(p.specs or []) + 1} if options else None,
        "graduation": {"available": can_graduate(p, c, today), "stage": ps.STAGES[-1]["name"],
                       "coins": int(c["graduation_coins"])},
        "week": await week_out(db, p, c, today),
        "bday": {"today": ps.is_birthday(p, c, today), "opened": bday_open, "stars": int(c["bday_stars"]),
                 "xp": int(c["bday_xp"])},
        "game_xp": {"match": int(c["game_match_xp"]), "goal": int(c["game_goal_xp"]), "win": int(c["game_win_xp"])},
    }


# --- the bot's digest + sweeps -----------------------------------------------------------------

def _digest(p: AcademyProspect, c: dict, today: date) -> list[str]:
    lines = []
    days = ps.age_days(p, today)
    dpy = max(1, int(c["days_per_year"]))
    stage = ps.stage_of(p, c, today)
    if ps.is_birthday(p, c, today):
        lines.append(f"🎂 Сегодня {p.name} {ps.age_of(days, c)} лет!")
    stage_day = (int(c["stage_ages"][stage]) - int(c["start_age"])) * dpy
    if stage > 0 and days == stage_day:
        lines.append(f"{ps.STAGES[stage]['emoji']} Новая ступень: {ps.STAGES[stage]['name']}")
    if spec_options(p, c, today):
        lines.append("✨ Пора выбрать талант")
    if can_graduate(p, c, today):
        lines.append("🎓 Можно провести выпускной")
    if p.training_day != today:
        streak = p.training_streak if p.training_day == today - timedelta(days=1) else 0
        lines.append(f"🔥 Серия {streak} дн. — не прерви, тренировка ждёт" if streak >= 2 else "⚽ Тренировка ещё не сделана")
    if ps.current_story(p, c, today) is not None:
        lines.append("📖 Новая история ждёт решения")
    return lines


async def remind_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    """The evening digest: once a local day, after `notify_hour`, to users
    seen within `notify_active_days` (ledger notice:<day>)."""
    now = now or datetime.now(timezone.utc)
    c = ps.cfg(await get_config(db))
    if not c["enabled"] or now.astimezone(app_timezone()).hour < int(c["notify_hour"]):
        return 0
    today = local_today(now)
    since = now - timedelta(days=int(c["notify_active_days"]))
    done = set((await db.execute(select(ProspectLedger.user_id).where(
        ProspectLedger.kind == "notice", ProspectLedger.code == today.isoformat(),
    ))).scalars())
    rows = (await db.execute(
        select(AcademyProspect).join(User, User.id == AcademyProspect.user_id)
        .where(AcademyProspect.status == ps.GROWING, User.is_banned.is_(False), User.bot_blocked.is_(False),
               User.last_seen_at >= since)
    )).scalars().all()
    sent = 0
    for p in rows:
        if p.user_id in done:
            continue
        lines = _digest(p, c, today)
        if not lines:
            continue
        try:
            async with db.begin_nested():
                db.add(ProspectLedger(user_id=p.user_id, kind="notice", code=today.isoformat(),
                                      idempotency_key=f"notice:{today.isoformat()}"))
                await db.flush()
        except IntegrityError:
            continue
        await notify(db, p.user_id, NotificationType.prospect_event, f"🌱 {p.name}: новости дня", "\n".join(lines),
                     related_object_type=RELATED, related_object_id=p.id)
        sent += 1
    await db.commit()
    return sent


async def sweep(db: AsyncSession, now: Optional[datetime] = None) -> dict:
    """Bot loop: expired duels, last week's cohort prizes, the digest."""
    now = now or datetime.now(timezone.utc)
    c = ps.cfg(await get_config(db))
    if not c["enabled"]:
        return {"duels": 0, "prizes": 0, "reminders": 0}
    duels = await _expire_duels(db, now)
    await db.commit()
    today = local_today(now)
    prizes = 0
    seen: set[str] = set()
    for p in (await db.execute(select(AcademyProspect).where(AcademyProspect.status == ps.GROWING))).scalars().all():
        key = ps.cohort_key(p.created_at)
        if key in seen:
            continue
        seen.add(key)
        prizes += await settle_week(db, p, c, today)
        await db.commit()
    return {"duels": duels, "prizes": prizes, "reminders": await remind_due(db, now)}


# --- share / admin ----------------------------------------------------------------------------

TIERS = ("bronze", "bronze", "silver", "gold", "legend")


async def share_image(db: AsyncSession, user: User) -> tuple[bytes, str, str]:
    """(png, fingerprint, caption) of the growing child — or of the active
    graduate when there is none."""
    from app.config import get_settings
    from app.services import share_card_service

    c = ps.cfg(await get_config(db))
    today = local_today()
    p = await ps.get_prospect(db, user.id) or await ps.get_prospect(db, user.id, ps.GRADUATE)
    if p is None:
        raise NotFoundError("Сначала создай воспитанника")
    grad = p.status == ps.GRADUATE
    rating = ps.club_rating(p, c, today)
    stage = len(ps.STAGES) - 1 if grad else ps.stage_of(p, c, today)
    age = ps.age_of(ps.age_days(p, today), c)
    attack, defense = ps.atk_def_of(p, c, rating)
    label = "Выпускник Академии" if grad else f"{ps.STAGES[stage]['name']} · {age} лет"
    image = share_card_service.render_my_player(
        name=p.name, number=p.number, position=p.position.value, rating=rating, attack=attack, defense=defense,
        level=age, tier=TIERS[stage], tier_label=label, appearance=p.appearance or {},
        bot_username=get_settings().telegram_bot_username,
        title="Мой выпускник Академии!" if grad else "Мой воспитанник в Victor FC!",
        level_text=f"{p.generation}-е поколение" if p.generation > 1 else ("выпускник" if grad else f"{age} лет"),
    )
    fingerprint = f"prospect|{p.id}|{p.name}|{p.number}|{rating}|{label}|{attack}|{defense}|{sorted((p.appearance or {}).items())}"
    caption = (f"{p.name} окончил Академию с рейтингом {rating}! 🎓 Вырасти своего в Victor FC" if grad
               else f"Мой воспитанник {p.name}: {age} лет, {ps.STAGES[stage]['name'].lower()}, рейтинг {rating} 🌱 Вырасти своего в Victor FC")
    return image, fingerprint, caption


async def admin_stats(db: AsyncSession) -> dict:
    c = ps.cfg(await get_config(db))
    today = local_today()
    rows = (await db.execute(select(AcademyProspect))).scalars().all()
    growing = [r for r in rows if r.status == ps.GROWING]
    by_stage = [0] * len(ps.STAGES)
    for r in growing:
        by_stage[ps.stage_of(r, c, today)] += 1
    grads = [r for r in rows if r.status != ps.GROWING]
    stars = (await db.execute(select(func.coalesce(func.sum(ProspectLedger.stars), 0)))).scalar_one()
    coins = (await db.execute(select(func.coalesce(func.sum(ProspectLedger.coins), 0)).where(ProspectLedger.kind == "cosmetic"))).scalar_one()
    duels = (await db.execute(select(func.count(ProspectDuel.id)))).scalar_one()
    week_ago = today - timedelta(days=7)
    active = sum(1 for r in growing if r.training_day and r.training_day >= week_ago)
    return {
        "total": len(rows), "growing": len(growing), "graduates": len(grads),
        "by_stage": [{"stage": s["name"], "count": by_stage[i]} for i, s in enumerate(ps.STAGES)],
        "avg_graduate_rating": round(sum(g.final_rating or 0 for g in grads) / len(grads), 1) if grads else None,
        "active_week": active, "stars": int(stars), "coins_cosmetics": int(coins), "duels": int(duels),
    }
