"""«Лига друзей» of «Карьера игрока».

A player with a club invites friends (each with their own «Мой игрок» and
club); once at least two have joined, the owner starts it: every friend
plays for his club (its squad + his footballer), bots from the club list
fill the league to 8, single round-robin — 7 rounds at the career slots
(resolved with the league seasons). A match between two friends is a derby:
rewards x config.player_career_derby_multiplier and a head-to-head record.
Per match: coins (result, goals), XP, prestige, freshness, month/week
stats; at the end coins for places 1-3 (config.player_career_friends_rewards)
and the «Чемпион лиги друзей» trophy for a friend who wins it.
"""
import copy
import random
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from app.core.exceptions import ConflictError, ForbiddenError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.enums import NotificationType, TransactionType
from app.models.my_player import MyPlayer
from app.models.player_career import PlayerCareerFriendLeague, PlayerCareerFriendMember
from app.models.user import User
from app.services import my_player_service, player_career_clubs as pcc, tournament_match_engine, wallet_service
from app.services.career_service import build_schedule, double_round_robin, standings
from app.services.game_config_service import get_config
from app.services.notification_service import notify

TEAMS = 8
ROUNDS = TEAMS - 1
MAX_FRIENDS = TEAMS - 1
CHAMPION_TROPHY = "player_career_friends_champion"


def _name(user: User) -> str:
    return user.first_name or user.username or "Игрок"


async def _member_league(db: AsyncSession, user_id: int) -> Optional[PlayerCareerFriendLeague]:
    """The lobby/active league the player is in (owner or accepted)."""
    return (await db.execute(
        select(PlayerCareerFriendLeague).join(PlayerCareerFriendMember, PlayerCareerFriendMember.league_id == PlayerCareerFriendLeague.id)
        .where(PlayerCareerFriendMember.user_id == user_id, PlayerCareerFriendMember.status == "accepted",
               PlayerCareerFriendLeague.status.in_(("lobby", "active")))
        .order_by(PlayerCareerFriendLeague.id.desc()).limit(1)
    )).scalar_one_or_none()


async def _with_club(db: AsyncSession, user_ids: list[int]) -> dict[int, MyPlayer]:
    if not user_ids:
        return {}
    rows = (await db.execute(
        select(MyPlayer).where(MyPlayer.user_id.in_(user_ids), MyPlayer.club_key.is_not(None))
    )).scalars().all()
    return {mp.user_id: mp for mp in rows}


async def create(db: AsyncSession, user: User, invite_ids: list[int]) -> dict:
    from app.services.friend_service import friend_ids

    config = await get_config(db)
    await wallet_service.lock_user_for_update(db, user.id)
    if await _member_league(db, user.id):
        raise ConflictError("Ты уже в лиге друзей — доиграй её")
    if not (await _with_club(db, [user.id])):
        raise ConflictError("Сначала подпиши контракт с клубом")
    friends = set(await friend_ids(db, user.id))
    invite_ids = list(dict.fromkeys(i for i in invite_ids if i != user.id))
    if not invite_ids:
        raise ConflictError("Позови хотя бы одного друга")
    if len(invite_ids) > MAX_FRIENDS:
        raise ConflictError(f"В лиге не больше {MAX_FRIENDS} друзей")
    if any(i not in friends for i in invite_ids):
        raise ConflictError("Позвать можно только друзей")
    with_club = await _with_club(db, invite_ids)
    if any(i not in with_club for i in invite_ids):
        raise ConflictError("У кого-то из друзей ещё нет игрока с клубом")
    league = PlayerCareerFriendLeague(owner_id=user.id, status="lobby", state={})
    db.add(league)
    await db.flush()
    db.add(PlayerCareerFriendMember(league_id=league.id, user_id=user.id, status="accepted"))
    for uid in invite_ids:
        db.add(PlayerCareerFriendMember(league_id=league.id, user_id=uid, status="invited"))
        await notify(
            db, uid, NotificationType.player_career_event, "Приглашение в лигу друзей 🤝",
            f"{_name(user)} зовёт тебя в лигу друзей «Карьеры игрока» — 7 туров, дерби с друзьями",
            related_object_type="player_career_friend_league", related_object_id=league.id,
        )
    await db.commit()
    return await view(db, user, config)


async def respond(db: AsyncSession, user: User, league_id: int, accept: bool) -> dict:
    config = await get_config(db)
    await wallet_service.lock_user_for_update(db, user.id)
    member = (await db.execute(
        select(PlayerCareerFriendMember).where(PlayerCareerFriendMember.league_id == league_id, PlayerCareerFriendMember.user_id == user.id)
    )).scalar_one_or_none()
    league = await db.get(PlayerCareerFriendLeague, league_id)
    if member is None or league is None:
        raise NotFoundError("Приглашение не найдено")
    if league.status != "lobby" or member.status != "invited":
        raise ConflictError("Приглашение уже неактуально")
    if accept:
        if await _member_league(db, user.id):
            raise ConflictError("Ты уже в другой лиге друзей")
        if not (await _with_club(db, [user.id])):
            raise ConflictError("Сначала подпиши контракт с клубом")
    member.status = "accepted" if accept else "declined"
    await db.commit()
    return await view(db, user, config)


async def cancel(db: AsyncSession, user: User, league_id: int) -> dict:
    config = await get_config(db)
    league = await _lock(db, league_id)
    if league.owner_id != user.id:
        raise ForbiddenError("Отменить лигу может только тот, кто её создал")
    if league.status != "lobby":
        raise ConflictError("Начатую лигу отменить нельзя")
    league.status = "cancelled"
    await db.commit()
    return await view(db, user, config)


async def _lock(db: AsyncSession, league_id: int) -> PlayerCareerFriendLeague:
    league = (await db.execute(
        select(PlayerCareerFriendLeague).where(PlayerCareerFriendLeague.id == league_id).with_for_update()
        .execution_options(populate_existing=True)
    )).scalar_one_or_none()
    if league is None:
        raise NotFoundError("Лига не найдена")
    return league


def _team(index: int, club: dict, user_id: Optional[int], owner_name: Optional[str]) -> dict:
    rng = random.Random(pcc._seed(f"{club['key']}:{user_id}"))
    return {
        "index": index, "key": club["key"], "name": club["name"], "rating": club["rating"], "players": club["squad"],
        "user_id": user_id, "owner_name": owner_name,
        "mentality": rng.choice(["BALANCED", "ATTACKING", "DEFENSIVE"]), "playstyle": rng.choice(["CENTRAL_PLAY", "WING_PLAY", "POSSESSION"]),
    }


async def start(db: AsyncSession, user: User, league_id: int, now: Optional[datetime] = None) -> dict:
    config = await get_config(db)
    now = now or datetime.now(timezone.utc)
    await pcc.prepare(db, config)
    league = await _lock(db, league_id)
    if league.owner_id != user.id:
        raise ForbiddenError("Запустить лигу может только тот, кто её создал")
    if league.status != "lobby":
        raise ConflictError("Лига уже идёт")
    members = (await db.execute(
        select(PlayerCareerFriendMember).where(PlayerCareerFriendMember.league_id == league.id, PlayerCareerFriendMember.status == "accepted")
    )).scalars().all()
    if len(members) < 2:
        raise ConflictError("Нужен хотя бы один друг, принявший приглашение")
    ids = [m.user_id for m in members]
    mps = await _with_club(db, ids)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()}
    clubs = await pcc.club_catalog(db, config)
    teams, used, names = [], set(), set()
    for uid in ids:
        mp = mps.get(uid)
        club = pcc.find_club(clubs, mp.club_key) if mp else None
        if club is None:
            continue
        team = _team(len(teams), club, uid, _name(users[uid]) if uid in users else "Игрок")
        if team["name"] in names:
            team["name"] = f"{team['name']} ({team['owner_name']})"
        names.add(team["name"])
        used.add(club["key"])
        teams.append(team)
    if len(teams) < 2:
        raise ConflictError("Нужны хотя бы двое с клубами")
    average = sum(t["rating"] for t in teams) / len(teams)
    bots = sorted((c for c in clubs if c["key"] not in used and c["name"] not in names), key=lambda c: (abs(c["rating"] - average), c["key"]))
    for club in bots[: TEAMS - len(teams)]:
        teams.append(_team(len(teams), club, None, None))
    while len(teams) < TEAMS:
        filler = pcc.academy_fillers({"key": f"fl:{league.id}", "rating": round(average), "league": None, "level": None},
                                     1, names | {t["name"] for t in teams}, config)[0]
        teams.append(_team(len(teams), filler, None, None))
    league.state = {
        "teams": teams, "fixtures": double_round_robin(TEAMS)[:ROUNDS], "schedule": build_schedule(now)[:ROUNDS],
        "results": [], "players": {str(t["user_id"]): {"matches": 0, "goals": 0, "assists": 0, "rating_sum": 0.0}
                                   for t in teams if t["user_id"]},
        "derbies": [],
    }
    league.status = "active"
    league.started_at = now
    for t in teams:
        if t["user_id"] and t["user_id"] != user.id:
            await notify(
                db, t["user_id"], NotificationType.player_career_event, "Лига друзей началась! ⚽",
                f"{len([x for x in teams if x['user_id']])} друзей, 7 туров. Первый тур — скоро",
                related_object_type="player_career_friend_league", related_object_id=league.id,
            )
    await db.commit()
    return await view(db, user, config)


async def _play_round(db: AsyncSession, league: PlayerCareerFriendLeague, round_index: int, config) -> None:
    from app.services import player_career_cups as cups
    from app.services import player_career_life as life
    from app.services.player_career_service import _match_rating, _side

    state = copy.deepcopy(league.state)
    teams = state["teams"]
    cards = {}
    for t in teams:
        if t["user_id"]:
            cards[t["index"]] = await my_player_service.engine_card(db, t["user_id"], config)
    at = ensure_aware(datetime.fromisoformat(state["schedule"][round_index])) if round_index < len(state["schedule"]) else datetime.now(timezone.utc)
    rng = random.Random(league.id * 4099 + round_index)
    results = []
    for home, away in state["fixtures"][round_index]:
        side_h = _side(teams[home], cards.get(home), config)
        side_a = _side(teams[away], cards.get(away), config)
        match = tournament_match_engine.simulate_match(
            side_h[0], side_a[0], side_h[1], side_a[1], config, teams[home]["name"], teams[away]["name"],
        )
        entry = {"home": home, "away": away, "hs": match.score_a, "as": match.score_b}
        derby = bool(teams[home]["user_id"] and teams[away]["user_id"])
        if derby:
            entry["derby"] = True
            state["derbies"].append({"round": round_index, **entry})
        results.append(entry)
        for idx, side in ((home, "a"), (away, "b")):
            uid = teams[idx]["user_id"]
            card = cards.get(idx)
            if not uid or card is None:
                continue
            own, opp = (match.score_a, match.score_b) if side == "a" else (match.score_b, match.score_a)
            goals = sum(1 for e in match.event_log if e.get("event_type") == "goal" and e.get("team") == side
                        and (e.get("payload") or {}).get("shooter_id") == card.id)
            assists = sum(1 for e in match.event_log if e.get("event_type") == "goal" and e.get("team") == side
                          and (e.get("payload") or {}).get("assist_id") == card.id)
            line = my_player_service.category_of(card.player.position)
            rating = _match_rating(goals, assists, own, opp, rng, line)
            totals = state["players"].setdefault(str(uid), {"matches": 0, "goals": 0, "assists": 0, "rating_sum": 0.0})
            totals["matches"] += 1
            totals["goals"] += goals
            totals["assists"] += assists
            totals["rating_sum"] += rating
            multiplier = config.player_career_derby_multiplier if derby else 1
            reward = (config.player_career_match_reward_win if own > opp else config.player_career_match_reward_draw if own == opp else 0)
            reward = (reward + goals * config.player_career_goal_reward) * multiplier
            locked = await wallet_service.lock_user_for_update(db, uid)
            if reward > 0:
                await wallet_service.credit_coins(
                    db, locked, reward, TransactionType.player_career_reward,
                    f"Лига друзей, тур {round_index + 1}{' (дерби)' if derby else ''}",
                    related_object_type="player_career_friend_league", related_object_id=league.id,
                )
            mp = (await db.execute(
                select(MyPlayer).where(MyPlayer.user_id == uid).with_for_update().execution_options(populate_existing=True)
            )).scalar_one_or_none()
            if mp is not None:
                my_player_service.add_xp(
                    locked, config.player_career_match_xp, config,
                    bonus_pct=await my_player_service.xp_bonus_pct(db, uid) + life.career_xp_bonus(mp, config),
                )
                mp.reputation = (mp.reputation or 0) + goals * config.player_career_rep_per_goal \
                    + assists * config.player_career_rep_per_assist + (config.player_career_rep_per_win if own > opp else 0)
                fresh = my_player_service.freshness_now(mp, config, at, await my_player_service.regen_bonus(db, uid))
                my_player_service.set_freshness(mp, fresh - config.my_player_freshness_per_match, at)
            await cups.record_match(db, uid, at, goals, assists, rating, clean_sheet=opp == 0, line=line, won=own > opp)
            if derby:
                rival = teams[away if idx == home else home]
                verdict = "победа" if own > opp else "ничья" if own == opp else "поражение"
                await notify(
                    db, uid, NotificationType.player_career_event, f"Дерби с {rival['owner_name']}: {verdict}",
                    f"{own}:{opp} против «{rival['name']}»" + (f" · +{reward} монет" if reward else ""),
                    related_object_type="player_career_friend_league", related_object_id=league.id,
                )
    state["results"].append(results)
    league.state = state
    flag_modified(league, "state")
    league.rounds_played = round_index + 1
    if league.rounds_played >= ROUNDS:
        await _finish(db, league, config)


async def _finish(db: AsyncSession, league: PlayerCareerFriendLeague, config) -> None:
    from app.services.player_career_service import _grant_trophy

    state = league.state
    table = standings(state)
    teams = state["teams"]
    rewards = list(config.player_career_friends_rewards or [])
    champion = None
    for place, row in enumerate(table, start=1):
        team = teams[row["team_index"]]
        uid = team["user_id"]
        if not uid:
            continue
        coins = int(rewards[place - 1]) if place - 1 < len(rewards) else 0
        if coins > 0:
            locked = await wallet_service.lock_user_for_update(db, uid)
            await wallet_service.credit_coins(
                db, locked, coins, TransactionType.player_career_reward, f"Лига друзей: {place} место",
                related_object_type="player_career_friend_league", related_object_id=league.id,
            )
        if place == 1:
            champion = team
            await _grant_trophy(db, uid, CHAMPION_TROPHY, f"Лига друзей · «{team['name']}»")
        await notify(
            db, uid, NotificationType.player_career_event, f"Лига друзей завершена: {place} место",
            f"«{team['name']}» — {place} место" + (f" · +{coins} монет" if coins else ""),
            related_object_type="player_career_friend_league", related_object_id=league.id,
        )
    league.state = {**state, "champion": champion["owner_name"] if champion else None}
    flag_modified(league, "state")
    league.status = "finished"
    league.finished_at = datetime.now(timezone.utc)


async def resolve_league(db: AsyncSession, league_id: int, now: Optional[datetime] = None) -> int:
    from app.services.game_config_service import get_config as _get_config

    now = now or datetime.now(timezone.utc)
    config = await _get_config(db)
    league = await _lock(db, league_id)
    played = 0
    schedule = (league.state or {}).get("schedule") or []
    while league.status == "active" and league.rounds_played < ROUNDS:
        at = ensure_aware(datetime.fromisoformat(schedule[league.rounds_played])) if league.rounds_played < len(schedule) else None
        if at is None or at > now:
            break
        await _play_round(db, league, league.rounds_played, config)
        played += 1
    await db.commit()
    return played


async def resolve_all_due(db: AsyncSession, now: Optional[datetime] = None) -> int:
    ids = (await db.execute(select(PlayerCareerFriendLeague.id).where(PlayerCareerFriendLeague.status == "active"))).scalars().all()
    return sum([await resolve_league(db, league_id, now) for league_id in ids])


def _league_out(league: PlayerCareerFriendLeague, members: list, users: dict, viewer_id: int) -> dict:
    state = league.state or {}
    teams = state.get("teams") or []
    table = standings(state) if teams else []
    schedule = state.get("schedule") or []
    players = state.get("players") or {}
    h2h: dict[str, dict] = {}
    for d in state.get("derbies") or []:
        a, b = teams[d["home"]], teams[d["away"]]
        for me, them, gf, ga in ((a, b, d["hs"], d["as"]), (b, a, d["as"], d["hs"])):
            if me["user_id"] != viewer_id:
                continue
            row = h2h.setdefault(str(them["user_id"]), {"name": them["owner_name"], "won": 0, "drawn": 0, "lost": 0})
            row["won" if gf > ga else "drawn" if gf == ga else "lost"] += 1
    rounds = []
    for r, fixtures in enumerate(state.get("fixtures") or []):
        played = (state.get("results") or [])[r] if r < len(state.get("results") or []) else None
        rounds.append({
            "index": r, "at": schedule[r] if r < len(schedule) else None,
            "matches": [
                {"home": teams[h]["name"], "away": teams[a]["name"], "home_owner": teams[h]["owner_name"], "away_owner": teams[a]["owner_name"],
                 "derby": bool(teams[h]["user_id"] and teams[a]["user_id"]),
                 "mine": viewer_id in (teams[h]["user_id"], teams[a]["user_id"]),
                 **({"hs": m["hs"], "away_score": m["as"]} if (m := next((x for x in played or [] if x["home"] == h), None)) else {})}
                for h, a in fixtures
            ],
        })
    return {
        "id": league.id, "status": league.status, "is_owner": league.owner_id == viewer_id,
        "owner_name": _name(users[league.owner_id]) if league.owner_id in users else "Игрок",
        "rounds_played": league.rounds_played, "total_rounds": ROUNDS,
        "next_round_at": schedule[league.rounds_played] if league.status == "active" and league.rounds_played < len(schedule) else None,
        "members": [{"user_id": m.user_id, "name": _name(users[m.user_id]) if m.user_id in users else "Игрок", "status": m.status}
                    for m in members],
        "table": [
            {**row, "name": teams[row["team_index"]]["name"], "owner_name": teams[row["team_index"]]["owner_name"],
             "is_me": teams[row["team_index"]]["user_id"] == viewer_id,
             "is_friend": bool(teams[row["team_index"]]["user_id"])}
            for row in table
        ],
        "rounds": rounds,
        "players": [
            {"name": t["owner_name"], "team": t["name"], "is_me": t["user_id"] == viewer_id,
             **{k: players.get(str(t["user_id"]), {}).get(k, 0) for k in ("matches", "goals", "assists")},
             "avg_rating": round(p["rating_sum"] / p["matches"], 2) if (p := players.get(str(t["user_id"]))) and p["matches"] else None}
            for t in teams if t["user_id"]
        ],
        "h2h": list(h2h.values()),
        "champion": state.get("champion"),
    }


async def view(db: AsyncSession, user: User, config=None) -> dict:
    from app.services.friend_service import friend_ids

    current = await _member_league(db, user.id)
    if current is not None and current.status == "active":
        await resolve_league(db, current.id)
        current = await db.get(PlayerCareerFriendLeague, current.id)
    last = current or (await db.execute(
        select(PlayerCareerFriendLeague).join(PlayerCareerFriendMember, PlayerCareerFriendMember.league_id == PlayerCareerFriendLeague.id)
        .where(PlayerCareerFriendMember.user_id == user.id, PlayerCareerFriendMember.status == "accepted",
               PlayerCareerFriendLeague.status == "finished")
        .order_by(PlayerCareerFriendLeague.id.desc()).limit(1)
    )).scalar_one_or_none()
    invites = (await db.execute(
        select(PlayerCareerFriendLeague).join(PlayerCareerFriendMember, PlayerCareerFriendMember.league_id == PlayerCareerFriendLeague.id)
        .where(PlayerCareerFriendMember.user_id == user.id, PlayerCareerFriendMember.status == "invited",
               PlayerCareerFriendLeague.status == "lobby")
    )).scalars().all()
    league_ids = [x.id for x in [last, *invites] if x is not None]
    members = (await db.execute(
        select(PlayerCareerFriendMember).where(PlayerCareerFriendMember.league_id.in_(league_ids))
    )).scalars().all() if league_ids else []
    ids = {m.user_id for m in members} | {x.owner_id for x in [last, *invites] if x is not None}
    friends = await friend_ids(db, user.id)
    with_club = await _with_club(db, friends)
    ids |= set(with_club)
    users = {u.id: u for u in (await db.execute(select(User).where(User.id.in_(ids)))).scalars().all()} if ids else {}
    return {
        "league": _league_out(last, [m for m in members if m.league_id == last.id], users, user.id) if last else None,
        "invites": [{"id": x.id, "owner_name": _name(users[x.owner_id]) if x.owner_id in users else "Игрок"} for x in invites],
        "can_create": current is None,
        "friends": [{"user_id": uid, "name": _name(users[uid]) if uid in users else "Игрок", "player_name": mp.name}
                    for uid, mp in with_club.items()],
        "derby_multiplier": (config or await get_config(db)).player_career_derby_multiplier,
        "rewards": list((config or await get_config(db)).player_career_friends_rewards or []),
    }
