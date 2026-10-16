"""«Академия» (services/path_service.py, path_talent_effects.py,
path_match_service.py): experience and stages, daily limits and bought
attempts, idempotency, squad limits, diamond-feed / trade / sale rules, the
path pack, and every talent (fires / does not fire, cap, order, freezing,
«не действует» in unsupported modes)."""
from types import SimpleNamespace as NS

import pytest
from sqlalchemy import func, select

import app.core.rate_limit as rate_limit_module
from app.models.card import UserCard
from app.models.card_path import CardPath, PathStageTask, PathTalent, PathXpEvent
from app.models.enums import CardSource, Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.match import Match
from app.models.transaction import CoinTransaction
from app.services import chemistry_service, path_match_service, path_service, tournament_match_engine
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS, SLOTS_BY_CODE, get_active_lineup
from app.services.path_talent_effects import dynamic_bonus, plan_static, talent_snapshot
from tests.factories import create_pack, create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


async def _config(db_session, **overrides) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    for key, value in overrides.items():
        setattr(config, key, value)
    await db_session.commit()
    return config


async def _login(client, db_session, bot_token, telegram_id, balance=10_000):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    user.balance = balance
    await db_session.commit()
    return headers, user


async def _path_card(db_session, user_id, *, talent="big_matches", position=Position.ST, rating=60, stage=0, level=0):
    player = await create_player(db_session, rarity=Rarity.diamond, rating=rating, position=position, path_talent_code=talent)
    card = await create_user_card(db_session, user_id, player.id, CardSource.seed)
    card.path_stage, card.path_level, card.path_rating_bonus = stage, level, level
    await db_session.commit()
    return card


async def _reload(db_session, model, key):
    return (await db_session.execute(
        select(model).where(list(model.__table__.primary_key.columns)[0] == key).execution_options(populate_existing=True)
    )).scalar_one_or_none()


def _cfg(**overrides):
    base = dict(
        path_enabled=True, path_xp_base=75, path_xp_step=10, path_start_rating=60, path_rating_per_level=1,
        path_xp_match=10, path_xp_win=10, path_xp_draw=3, path_xp_goal=5, path_xp_assist=3, path_talent_cap=8,
    )
    base.update(overrides)
    return NS(**base)


# --- experience scale, levels and stages -----------------------------------------------


def test_default_scale_is_9000_xp_for_36_levels():
    config = _cfg()
    assert path_service.level_cost(1, 0, config) == 75
    assert path_service.level_cost(36, 0, config) == 425
    assert path_service.xp_for_levels(36, 0, config) == 9000
    # A design that starts higher skips the cheap levels.
    assert path_service.level_offset(62, config) == 2
    assert path_service.level_cost(1, 2, config) == 95


def _catalog_stub():
    stages = [
        NS(stage_index=0, name="Новичок", max_rating=65, talent_level=0),
        NS(stage_index=1, name="Перспективный", max_rating=74, talent_level=0),
        NS(stage_index=2, name="Основной", max_rating=84, talent_level=1),
        NS(stage_index=3, name="Звезда", max_rating=89, talent_level=1),
        NS(stage_index=4, name="Легенда", max_rating=96, talent_level=2),
    ]
    tasks = {0: [NS(id=1, stage_index=0, metric="matches", target=3, positions=None)],
             2: [NS(id=2, stage_index=2, metric="goal_contributions", target=2, positions=["ST"])]}
    return path_service.Catalog(stages=stages, tasks=tasks, talents={})


def test_stage_gate_caps_the_level_until_tasks_are_done():
    catalog, config = _catalog_stub(), _cfg()
    card = NS(player=NS(rating=60, position=Position.ST), path_level=0, path_stage=0, path_rating_bonus=0)
    path = NS(xp=path_service.xp_for_levels(8, 0, config), stage_counters={"matches": 2})
    gained = path_service.advance(card, path, catalog, config)
    # Enough experience for 68, but Новичок ends at 65 and its task is not done.
    assert card.path_level == 5 and card.path_rating_bonus == 5 and card.path_stage == 0
    assert gained["levels"] == [61, 62, 63, 64, 65] and gained["stages"] == []

    path.stage_counters = {"matches": 3}
    gained = path_service.advance(card, path, catalog, config)
    assert card.path_stage == 1 and card.path_level == 8 and path.stage_counters == {}
    assert gained["stages"] == [1] and gained["levels"] == [66, 67, 68]


def test_position_limited_task_is_skipped_for_other_positions_and_ceiling_holds():
    catalog, config = _catalog_stub(), _cfg()
    defender = NS(player=NS(rating=60, position=Position.CB), path_level=24, path_stage=2, path_rating_bonus=24)
    path = NS(xp=path_service.xp_for_levels(36, 0, config) + 5000, stage_counters={})
    path_service.advance(defender, path, catalog, config)
    # Goal task applies only to ST: the CB walks through to the ceiling (96).
    assert defender.path_stage == 4 and defender.path_level == 36 and defender.player.rating + defender.path_rating_bonus == 96

    striker = NS(player=NS(rating=60, position=Position.ST), path_level=24, path_stage=2, path_rating_bonus=24)
    path = NS(xp=path_service.xp_for_levels(36, 0, config), stage_counters={})
    path_service.advance(striker, path, catalog, config)
    assert striker.path_stage == 2 and striker.path_level == 24


def test_metric_deltas_and_match_xp():
    assert path_service.metric_deltas("ptour", "win", 1, 2) == {
        "matches": 1, "wins": 1, "goals": 1, "assists": 2, "goal_contributions": 3, "ptour_matches": 1,
        "official_matches": 1,
    }
    config = _cfg()
    assert path_service.match_xp(config, "win", 1, 1) == 10 + 10 + 5 + 3
    assert path_service.match_xp(config, "draw", 0, 0) == 13
    assert path_service.match_xp(config, "loss", 0, 0) == 10


# --- awarding: idempotency, daily limits, bought attempts ------------------------------------


async def test_award_is_idempotent_per_card_and_match(client, db_session, bot_token):
    await _config(db_session)
    _headers, user = await _login(client, db_session, bot_token, 970001)
    card = await _path_card(db_session, user.id)
    entry = [path_service.MatchEntry(card.id, "win", goals=1)]
    first = await path_service.award_match(db_session, user_id=user.id, source_type="arena", source_id="42", entries=entry)
    second = await path_service.award_match(db_session, user_id=user.id, source_type="arena", source_id="42", entries=entry)
    await db_session.commit()
    assert first[0].status == "awarded" and first[0].xp == 25
    assert second[0].status == "duplicate"
    path = await _reload(db_session, CardPath, card.id)
    assert path.xp == 25 and path.arena_used == 1
    assert (await db_session.execute(select(func.count(PathXpEvent.id)))).scalar_one() == 1


async def test_arena_uses_free_then_bought_attempts_and_other_modes_have_own_caps(client, db_session, bot_token):
    await _config(db_session, path_daily_free_arena=2, path_daily_ptour=1, path_daily_career=1)
    _headers, user = await _login(client, db_session, bot_token, 970002)
    card = await _path_card(db_session, user.id)

    async def award(source, sid):
        res = await path_service.award_match(
            db_session, user_id=user.id, source_type=source, source_id=sid,
            entries=[path_service.MatchEntry(card.id, "loss")],
        )
        await db_session.commit()
        return res[0].status

    assert [await award("arena", str(i)) for i in range(3)] == ["awarded", "awarded", "no_attempts"]
    path = await _reload(db_session, CardPath, card.id)
    path.bought_attempts = 1
    await db_session.commit()
    assert await award("arena", "10") == "awarded"
    assert await award("arena", "11") == "no_attempts"
    # Tournament / career never use Arena attempts — their own caps.
    assert await award("ptour", "t1") == "awarded"
    assert await award("ptour", "t2") == "limit"
    assert await award("career", "c1") == "awarded"
    assert await award("career", "c2") == "limit"
    path = await _reload(db_session, CardPath, card.id)
    assert path.bought_attempts == 0 and path.xp == 10 * 5


async def test_award_skips_cards_of_another_owner_and_non_path_cards(client, db_session, bot_token):
    await _config(db_session)
    _h, user = await _login(client, db_session, bot_token, 970003)
    _h2, other = await _login(client, db_session, bot_token, 970004)
    foreign = await _path_card(db_session, other.id)
    plain_player = await create_player(db_session, rarity=Rarity.diamond)
    plain = await create_user_card(db_session, user.id, plain_player.id, CardSource.seed)
    await db_session.commit()
    res = await path_service.award_match(
        db_session, user_id=user.id, source_type="arena", source_id="1",
        entries=[path_service.MatchEntry(foreign.id, "win"), path_service.MatchEntry(plain.id, "win")],
    )
    assert {r.status for r in res} == {"not_path"}


async def test_path_disabled_gives_no_experience(client, db_session, bot_token):
    await _config(db_session, path_enabled=False)
    _h, user = await _login(client, db_session, bot_token, 970005)
    card = await _path_card(db_session, user.id)
    res = await path_service.award_match(
        db_session, user_id=user.id, source_type="arena", source_id="1", entries=[path_service.MatchEntry(card.id, "win")],
    )
    assert res == []


async def test_buy_attempt_with_coins_rising_price_limit_and_replay(client, db_session, bot_token):
    await _config(db_session, path_coin_attempt_prices=[300, 400])
    headers, user = await _login(client, db_session, bot_token, 970006, balance=1_000)
    card = await _path_card(db_session, user.id)
    url = f"/api/v1/path/cards/{card.id}/buy-attempt"

    r1 = await client.post(url, headers=headers, json={"idempotency_key": "k1"})
    assert r1.status_code == 200, r1.text
    assert r1.json()["daily"]["bought_attempts"] == 1 and r1.json()["daily"]["next_coin_price"] == 400
    replay = await client.post(url, headers=headers, json={"idempotency_key": "k1"})
    assert replay.status_code == 200 and replay.json()["daily"]["bought_attempts"] == 1
    r2 = await client.post(url, headers=headers, json={"idempotency_key": "k2"})
    assert r2.status_code == 200 and r2.json()["daily"]["coin_buys_left"] == 0
    r3 = await client.post(url, headers=headers, json={"idempotency_key": "k3"})
    assert r3.status_code == 409
    await db_session.refresh(user)
    assert user.balance == 1_000 - 300 - 400
    spent = (await db_session.execute(select(func.sum(CoinTransaction.amount)).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.path_attempt_purchase,
    ))).scalar_one()
    assert spent == -700


async def test_buy_attempt_for_a_plain_card_is_refused(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970007)
    player = await create_player(db_session, rarity=Rarity.diamond)
    card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()
    resp = await client.post(f"/api/v1/path/cards/{card.id}/buy-attempt", headers=headers, json={})
    assert resp.status_code == 409


async def test_stars_attempt_delivery_adds_one_attempt(client, db_session, bot_token, monkeypatch):
    from app.models.pack import StarsInvoice
    from app.services import stars_payment_service

    async def fake_link(*args, **kwargs):
        return "https://t.me/invoice/x"

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", fake_link)
    await _config(db_session, path_stars_attempt_prices=[3, 4])
    headers, user = await _login(client, db_session, bot_token, 970008)
    card = await _path_card(db_session, user.id)
    resp = await client.post(f"/api/v1/path/cards/{card.id}/stars-invoice", headers=headers)
    assert resp.status_code == 200, resp.text
    token = resp.json()["payload_token"]
    assert resp.json()["stars_amount"] == 3
    ok, _ = await stars_payment_service.validate_pre_checkout(db_session, token, 3)
    assert ok
    result = await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "charge-1", 3)
    assert result.path_result["user_card_id"] == card.id
    again = await stars_payment_service.deliver_payment(db_session, token, user.telegram_id, "charge-1", 3)
    assert again.status == "completed"
    path = await _reload(db_session, CardPath, card.id)
    assert path.bought_attempts == 1 and path.stars_buys == 1
    invoice = (await db_session.execute(select(StarsInvoice).where(StarsInvoice.payload_token == token))).scalar_one()
    assert invoice.completed_at is not None
    state = (await client.get(f"/api/v1/path/cards/{card.id}", headers=headers)).json()
    assert state["daily"]["next_stars_price"] == 4


# --- Card Arena end to end ---------------------------------------------------------------------


async def _arena_lineup(client, db_session, headers, user, path_card=None, slot_code="FWD2"):
    slots = []
    for slot in FORMATION_SLOTS:
        if path_card is not None and slot.code == slot_code:
            slots.append({"slot_code": slot.code, "user_card_id": path_card.id})
            continue
        player = await create_player(db_session, rating=70, position=slot.ideal_position)
        card = await create_user_card(db_session, user.id, player.id, CardSource.seed)
        await db_session.commit()
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    resp = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200, resp.text
    return slots


async def _play(client, headers):
    actions = {"attack": "shoot", "defense": "tackle", "breakaway": "strike"}
    match = (await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})).json()
    while match["status"] == "in_progress":
        action = actions[match["pending_moment"]["kind"]]
        match = (await client.post(f"/api/v1/matches/{match['id']}/act", headers=headers, json={"action": action})).json()
    return match


async def test_rewarded_arena_match_gives_experience_once(client, db_session, bot_token):
    await _config(db_session, hourly_game_limit=10)
    headers, user = await _login(client, db_session, bot_token, 970010)
    card = await _path_card(db_session, user.id)
    await _arena_lineup(client, db_session, headers, user, card)
    match = await _play(client, headers)
    assert match["status"] == "finished"
    progress = match["path_progress"]
    assert progress and progress[0]["user_card_id"] == card.id and progress[0]["status"] == "awarded"
    event = (await db_session.execute(select(PathXpEvent).where(PathXpEvent.user_card_id == card.id))).scalar_one()
    assert event.source_type == "arena" and event.source_id == str(match["id"])
    expected = 10 + {"win": 10, "draw": 3, "loss": 0}[match["result"]]
    assert event.xp >= expected


async def test_forfeit_and_blocked_rewards_give_no_experience(client, db_session, bot_token):
    await _config(db_session, hourly_game_limit=10)
    headers, user = await _login(client, db_session, bot_token, 970011)
    card = await _path_card(db_session, user.id)
    await _arena_lineup(client, db_session, headers, user, card)
    match = (await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})).json()
    if match["status"] == "in_progress":
        await client.post(f"/api/v1/matches/{match['id']}/forfeit", headers=headers)
    user.game_rewards_blocked = True
    await db_session.commit()
    await _play(client, headers)
    assert (await db_session.execute(select(func.count(PathXpEvent.id)))).scalar_one() == 0


# --- squad limits, diamond feed, trade, sale -------------------------------------------------------


async def test_path_card_has_its_own_limit_next_to_a_diamond(client, db_session, bot_token):
    await _config(db_session, match_max_diamond_cards=1, match_max_path_cards=1)
    headers, user = await _login(client, db_session, bot_token, 970020)
    path_a = await _path_card(db_session, user.id, position=Position.ST)
    diamond_player = await create_player(db_session, rarity=Rarity.diamond, position=Position.LW)
    diamond = await create_user_card(db_session, user.id, diamond_player.id, CardSource.seed)
    await db_session.commit()
    ok = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": [
        {"slot_code": "FWD2", "user_card_id": path_a.id}, {"slot_code": "FWD1", "user_card_id": diamond.id},
    ]})
    assert ok.status_code == 200, ok.text
    path_b = await _path_card(db_session, user.id, position=Position.RW)
    too_many = await client.put("/api/v1/lineups/active", headers=headers, json={"slots": [
        {"slot_code": "FWD2", "user_card_id": path_a.id}, {"slot_code": "FWD3", "user_card_id": path_b.id},
    ]})
    assert too_many.status_code == 409 and "Академии" in too_many.json()["error"]["message"]


async def test_path_cards_are_excluded_from_diamond_feeding(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970021)
    path_card = await _path_card(db_session, user.id)
    diamond_player = await create_player(db_session, rarity=Rarity.diamond)
    diamond = await create_user_card(db_session, user.id, diamond_player.id, CardSource.seed)
    common_player = await create_player(db_session)
    material = await create_user_card(db_session, user.id, common_player.id, CardSource.seed)
    await db_session.commit()
    as_target = await client.post("/api/v1/collection/diamond-upgrade/feed", headers=headers,
                                  json={"diamond_card_id": path_card.id, "material_card_ids": [material.id]})
    assert as_target.status_code == 409
    as_material = await client.post("/api/v1/collection/diamond-upgrade/feed", headers=headers,
                                    json={"diamond_card_id": diamond.id, "material_card_ids": [path_card.id]})
    assert as_material.status_code == 409


async def test_progress_travels_with_the_card_on_a_trade(client, db_session, bot_token, trade_guards_off):
    await _config(db_session)
    headers_a, user_a = await _login(client, db_session, bot_token, 970022)
    headers_b, user_b = await _login(client, db_session, bot_token, 970023)
    card = await _path_card(db_session, user_a.id, stage=2, level=15)
    db_session.add(CardPath(user_card_id=card.id, xp=4000, stage_counters={"matches": 7}, totals={}))
    await db_session.commit()
    offer = await client.post("/api/v1/trades/offers", headers=headers_a, json={
        "receiver_id": user_b.id, "offered_card_ids": [card.id], "receiver_coins": 10,
    })
    assert offer.status_code == 200, offer.text
    accepted = await client.post(f"/api/v1/trades/offers/{offer.json()['id']}/accept", headers=headers_b)
    assert accepted.status_code == 200, accepted.text
    state = await client.get(f"/api/v1/path/cards/{card.id}", headers=headers_b)
    assert state.status_code == 200
    body = state.json()
    assert body["level"] == 15 and body["stage"] == 2 and body["xp"] == 4000 and body["rating"] == 75
    assert (await client.get(f"/api/v1/path/cards/{card.id}", headers=headers_a)).status_code == 403


async def test_selling_a_card_with_path_progress_needs_confirmation(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970024)
    card = await _path_card(db_session, user.id, level=3)
    spare = await create_user_card(db_session, user.id, card.player_id, CardSource.seed)
    await db_session.commit()
    resp = await client.post("/api/v1/collection/cards/sell", headers=headers, json={"user_card_id": card.id})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["requires_path_loss_confirmation"] is True
    resp = await client.post("/api/v1/collection/cards/sell", headers=headers,
                             json={"user_card_id": card.id, "confirm_skill_loss": True})
    assert resp.status_code == 200, resp.text
    assert spare.id


# --- pack pool ---------------------------------------------------------------------------------------


async def test_path_pack_drops_only_path_cards_in_diamond_slots_and_regular_packs_never(client, db_session, bot_token):
    await _config(db_session)
    headers, _user = await _login(client, db_session, bot_token, 970030, balance=100_000)
    path_player = await create_player(db_session, rarity=Rarity.diamond, path_talent_code="fighter")
    plain_diamond = await create_player(db_session, rarity=Rarity.diamond)
    await create_player(db_session, rarity=Rarity.common)
    path_pack = await create_pack(db_session, "path-test", 10, 3, {Rarity.diamond: 1.0}, player_pool="path")
    regular = await create_pack(db_session, "reg-test", 10, 3, {Rarity.diamond: 1.0})

    for _ in range(3):
        opened = await client.post(f"/api/v1/packs/{path_pack.id}/open", headers=headers, json={})
        assert opened.status_code == 200, opened.text
        assert {c["card"]["player"]["id"] for c in opened.json()["cards"]} == {path_player.id}
        opened = await client.post(f"/api/v1/packs/{regular.id}/open", headers=headers, json={})
        assert {c["card"]["player"]["id"] for c in opened.json()["cards"]} == {plain_diamond.id}


# --- talents: snapshot / «не действует» ----------------------------------------------------------------


async def _catalog(db_session):
    return await path_service.load_catalog(db_session)


async def test_talent_needs_main_stage_and_is_off_where_not_modelled(client, db_session, bot_token):
    config = await _config(db_session)
    _h, user = await _login(client, db_session, bot_token, 970040)
    catalog = await _catalog(db_session)
    rookie = await _path_card(db_session, user.id, talent="second_wind", stage=1)
    main = await _path_card(db_session, user.id, talent="second_wind", stage=2)
    legend = await _path_card(db_session, user.id, talent="second_wind", stage=4)
    await db_session.refresh(rookie, ["player"]); await db_session.refresh(main, ["player"]); await db_session.refresh(legend, ["player"])
    assert talent_snapshot(rookie, catalog, config, "arena") is None
    assert talent_snapshot(main, catalog, config, "arena")["level"] == 1
    assert talent_snapshot(legend, catalog, config, "arena")["values"]["bonus"] == 5
    assert talent_snapshot(main, catalog, config, "career")["values"]["fatigue_cut_pct"] == 25
    assert talent_snapshot(main, catalog, config, "tactico") is None
    assert talent_snapshot(main, catalog, config, "stratego") is None
    hunger = await _path_card(db_session, user.id, talent="hunger", stage=2)
    await db_session.refresh(hunger, ["player"])
    assert talent_snapshot(hunger, catalog, config, "ptour") is None  # Arena only
    row = await db_session.get(PathTalent, "second_wind")
    row.is_enabled = False
    await db_session.commit()
    catalog = await _catalog(db_session)
    assert talent_snapshot(main, catalog, config, "arena") is None


# --- talents: pure effects ---------------------------------------------------------------------------


def _snap(code, level=1, **values):
    from app.services.path_talent_catalog import TALENTS, values_for

    v = values_for(code, level, None)
    v.update(values)
    return {"code": code, "name": TALENTS[code].name, "emoji": TALENTS[code].emoji, "kind": TALENTS[code].kind,
            "level": level, "level_label": "I" if level == 1 else "II", "values": v, "player": "P", "card_id": 1}


def _pair(cid, position, slot_code, club="A", country="X"):
    card = NS(id=cid, player=NS(position=position, club=club, country=country, display_name=f"P{cid}", rating=70,
                                rarity=Rarity.common, attack_rating=None, defense_rating=None))
    return card, SLOTS_BY_CODE[slot_code]


def _plan(pairs, talents, **kw):
    params = dict(formation="4-3-3", opponent_ratio=None, coach_country=None, stadium_club=None)
    params.update(kw)
    return plan_static(pairs, talents, _cfg(), **params)


def test_big_matches_fires_only_against_a_stronger_opponent():
    pairs = [_pair(1, Position.ST, "FWD2")]
    assert _plan(pairs, {1: _snap("big_matches")}, opponent_ratio=1.05).static == {1: 3}
    assert _plan(pairs, {1: _snap("big_matches", 2)}, opponent_ratio=1.2).static == {1: 5}
    assert _plan(pairs, {1: _snap("big_matches")}, opponent_ratio=1.04).static == {}
    assert _plan(pairs, {1: _snap("big_matches")}, opponent_ratio=None).static == {}


def test_second_wind_fighter_composure_hold_lead_conditions():
    sw = {**_snap("second_wind"), "room": 8}
    assert dynamic_bonus(sw, minute=59, own=0, opp=0, role="shooter") == 0
    assert dynamic_bonus(sw, minute=60, own=0, opp=0, role="shooter") == 3
    fighter = {**_snap("fighter", 2), "room": 8}
    assert dynamic_bonus(fighter, minute=10, own=0, opp=1, role="defender") == 5
    assert dynamic_bonus(fighter, minute=10, own=1, opp=1, role="defender") == 0
    comp = {**_snap("composure"), "room": 8}
    assert dynamic_bonus(comp, minute=5, own=0, opp=0, role="shooter", one_on_one=True) == 4
    assert dynamic_bonus(comp, minute=5, own=0, opp=0, role="shooter") == 0
    assert dynamic_bonus(comp, minute=5, own=0, opp=0, role="keeper", penalty=True) == 4
    assert dynamic_bonus(comp, minute=5, own=0, opp=0, role="passer", one_on_one=True) == 0
    hold = {**_snap("hold_lead"), "room": 8}
    assert dynamic_bonus(hold, minute=80, own=2, opp=1, role="defender") == 3
    assert dynamic_bonus(hold, minute=70, own=2, opp=1, role="defender") == 0
    assert dynamic_bonus(hold, minute=80, own=1, opp=1, role="keeper") == 0
    assert dynamic_bonus(hold, minute=80, own=2, opp=1, role="shooter") == 0
    # Static talents never act per moment.
    assert dynamic_bonus({**_snap("big_matches"), "room": 8}, minute=90, own=0, opp=5, role="shooter") == 0


def test_dynamic_bonus_respects_the_room_left_by_the_cap():
    assert dynamic_bonus({**_snap("second_wind", 2), "room": 2}, minute=70, own=0, opp=0, role="shooter") == 2
    plan = plan_static([_pair(1, Position.ST, "FWD2")], {1: _snap("fighter", 2)}, _cfg(path_talent_cap=3),
                       formation="4-3-3", opponent_ratio=None, coach_country=None, stadium_club=None)
    assert plan.talents[1]["room"] == 3


def test_universal_removes_the_position_penalty_and_level_two_keeps_chemistry():
    pairs = [_pair(1, Position.CAM, "FWD2")]  # CAM in a striker slot: adjacent
    plan1 = _plan(pairs, {1: _snap("universal")}, chemistry_on=True)
    assert plan1.position_override == {1: Position.ST} and plan1.static == {} and plan1.on_position_slots == set()
    plan2 = _plan(pairs, {1: _snap("universal", 2)}, chemistry_on=True)
    assert plan2.static == {1: 2} and plan2.on_position_slots == {"FWD2"}
    far = _plan([_pair(1, Position.CB, "FWD2")], {1: _snap("universal", 2)}, chemistry_on=True)
    assert far.position_override == {} and far.static == {}


def test_own_guy_lifts_links_only_with_chemistry_on():
    rules = chemistry_service.ChemistryRules()
    pairs = [_pair(1, Position.ST, "FWD2", club="A", country="X"), _pair(2, Position.LW, "FWD1", club="B", country="Y")]
    assert _plan(pairs, {1: _snap("own_guy")}, chemistry_on=False).link_floor == {}
    plan = _plan(pairs, {1: _snap("own_guy", 2)}, chemistry_on=True)
    plain = chemistry_service.compute_chemistry(pairs, "4-3-3", rules)
    lifted = chemistry_service.compute_chemistry(pairs, "4-3-3", rules, **plan.chemistry_hooks())
    assert plain.links[0].level == "none" and lifted.links[0].level == "strong"
    assert lifted.players["FWD2"].points > plain.players["FWD2"].points


def test_academy_coach_and_stadium_stack():
    pairs = [_pair(1, Position.ST, "FWD2", club="Зенит", country="Россия")]
    assert _plan(pairs, {1: _snap("academy")}, coach_country="Россия").static == {1: 2}
    assert _plan(pairs, {1: _snap("academy")}, coach_country="Россия", stadium_club="Зенит").static == {1: 4}
    assert _plan(pairs, {1: _snap("academy", 2)}, coach_country="Россия", stadium_club="Зенит").static == {1: 8}
    assert _plan(pairs, {1: _snap("academy")}, coach_country="Бразилия").static == {}


def test_hunger_grows_with_the_streak_up_to_its_max():
    pairs = [_pair(1, Position.ST, "FWD2")]
    assert _plan(pairs, {1: _snap("hunger")}, hunger={1: 2}).static == {1: 2}
    assert _plan(pairs, {1: _snap("hunger")}, hunger={1: 10}).static == {1: 3}
    assert _plan(pairs, {1: _snap("hunger", 2)}, hunger={1: 10}).static == {1: 6}
    assert _plan(pairs, {1: _snap("hunger")}, hunger={}).static == {}


def test_captain_aura_reaches_neighbours_and_is_capped():
    pairs = [_pair(1, Position.CM, "MID2"), _pair(2, Position.CB, "DEF2"), _pair(3, Position.CB, "DEF3"),
             _pair(4, Position.CDM, "MID1"), _pair(5, Position.CAM, "MID3"), _pair(6, Position.ST, "FWD2")]
    plan = _plan(pairs, {1: _snap("captain")})
    assert 1 not in plan.static
    assert sum(plan.static.values()) == 4 and all(v == 1 for v in plan.static.values())
    plan2 = _plan(pairs, {1: _snap("captain", 2)})
    assert sum(plan2.static.values()) == 6


def test_static_total_per_card_is_capped():
    pairs = [_pair(1, Position.ST, "FWD2", club="Зенит", country="Россия")]
    plan = plan_static(pairs, {1: _snap("academy", 2)}, _cfg(path_talent_cap=5), formation="4-3-3",
                       opponent_ratio=None, coach_country="Россия", stadium_club="Зенит")
    assert plan.static == {1: 5}


# --- talents inside the engines -----------------------------------------------------------------------


async def test_arena_kickoff_adds_a_static_talent_after_coach_and_stadium(client, db_session, bot_token):
    config = await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970050)
    card = await _path_card(db_session, user.id, talent="big_matches", stage=2, level=15)
    await _arena_lineup(client, db_session, headers, user, card)
    lineup = await get_active_lineup(db_session, user)
    stronger = await path_match_service.arena_kickoff(db_session, lineup, user_strength=1000, opponent_strength=1100, config=config)
    assert stronger.strength_delta == 3  # flat, after every multiplier
    assert stronger.state()["talents"]["static"] == {str(card.id): 3}
    weaker = await path_match_service.arena_kickoff(db_session, lineup, user_strength=1000, opponent_strength=1000, config=config)
    # Not stronger: the talent is frozen into the match but adds nothing.
    assert weaker.strength_delta == 0 and weaker.state()["talents"]["static"] == {}
    assert weaker.state()["path"]["cards"] == [card.id]


async def test_arena_talents_are_frozen_at_kickoff(client, db_session, bot_token):
    await _config(db_session, hourly_game_limit=10)
    headers, user = await _login(client, db_session, bot_token, 970051)
    card = await _path_card(db_session, user.id, talent="fighter", stage=4, level=30)
    await _arena_lineup(client, db_session, headers, user, card)
    match = (await client.post("/api/v1/matches/play", headers=headers, json={"difficulty": "medium"})).json()
    row = await db_session.get(Match, match["id"])
    snap = row.server_state["talents"]["cards"][str(card.id)]
    assert snap["code"] == "fighter" and snap["level"] == 2 and snap["values"]["bonus"] == 5
    talent = await db_session.get(PathTalent, "fighter")
    talent.level_values = {"1": {"bonus": 1}, "2": {"bonus": 1}}
    await db_session.commit()
    row = await _reload(db_session, Match, match["id"])
    assert row.server_state["talents"]["cards"][str(card.id)]["values"]["bonus"] == 5


def test_arena_actor_rating_applies_static_and_dynamic_and_notes_only_when_it_counts():
    state = {"user_score": 0, "opponent_score": 1, "talents": {
        "cards": {"7": {**_snap("fighter"), "static": 0, "room": 8}}, "static": {"9": 1},
    }}
    notes: list = []
    assert path_match_service.arena_actor_rating(state, {"user_card_id": 7, "rating": 70}, 30, "shooter", notes) == 73
    assert len(notes) == 1 and notes[0]["bonus"] == 3
    notes = []
    state["user_score"] = 1
    assert path_match_service.arena_actor_rating(state, {"user_card_id": 7, "rating": 70}, 30, "shooter", notes) == 70
    assert notes == []
    # Aura receiver (no own talent): bonus applied, no note claiming a talent of its own.
    assert path_match_service.arena_actor_rating(state, {"user_card_id": 9, "rating": 98}, 30, "shooter", notes) == 99
    assert notes == []


def test_tournament_engine_applies_a_dynamic_talent_without_touching_rng():
    import random

    from app.services.club_tactical_matchup_service import Chance

    snap = {**_snap("composure", 2), "room": 8}
    shooter = {"club_card_id": 1, "name": "S", "rating": 70, "position": "ST", "talent": snap}
    plain_shooter = {k: v for k, v in shooter.items() if k != "talent"}
    defender = {"club_card_id": 2, "name": "D", "rating": 70, "position": "CB"}
    config = NS(
        match_attack_shoot_miss_chance_min=0.2, match_attack_shoot_miss_chance_max=0.6,
        match_receiver_shot_miss_chance_min=0.2, match_receiver_shot_miss_chance_max=0.6,
        match_pass_fail_chance_min=0.1, match_pass_fail_chance_max=0.3,
        match_defender_block_chance_min=0.1, match_defender_block_chance_max=0.3,
        match_keeper_save_chance_min=0.2, match_keeper_save_chance_max=0.5,
        club_tactical_tackle_attempt_chance=0.0,
    )

    def run(actor, quality):
        result = tournament_match_engine.MatchResult(score_a=0, score_b=0)
        chance = Chance(attacking_side="a", minute=50, quality=quality, shot_type="in_box", is_box=True,
                        shooter=actor, pass_target=dict(actor), defender=defender)
        sides = NS(playstyle="BALANCED")
        random.seed(5)
        tournament_match_engine._resolve_chance(result, chance, sides, sides, [], [], config, "A", "B")
        return result.event_log[0], random.random()

    event, after = run(shooter, "VERY_HIGH")
    plain_event, plain_after = run(plain_shooter, "VERY_HIGH")
    assert after == plain_after  # same number of draws
    assert event["payload"]["talents"][0]["code"] == "composure" and event["payload"]["talents"][0]["bonus"] == 7
    assert "talents" not in plain_event["payload"]
    normal, _ = run(shooter, "NORMAL")  # not one-on-one: talent silent
    assert "talents" not in normal["payload"]


async def test_player_tournament_award_counts_goals_and_assists_from_the_log(client, db_session, bot_token):
    await _config(db_session)
    _h, user = await _login(client, db_session, bot_token, 970060)
    card = await _path_card(db_session, user.id)
    log = [
        {"event_type": "goal", "team": "a", "payload": {"shooter_id": card.id}},
        {"event_type": "goal", "team": "a", "payload": {"shooter_id": 999, "assist_id": card.id}},
        {"event_type": "goal", "team": "b", "payload": {"shooter_id": card.id}},
    ]
    res = await path_match_service.award_side(
        db_session, user_id=user.id, source_type="ptour", source_id="1:1:1:2", card_ids=[card.id], own=2, opp=1,
        event_log=log, side="a", config=await db_session.get(GameConfig, 1),
    )
    assert res[0].status == "awarded" and res[0].xp == 10 + 10 + 5 + 3
    path = await _reload(db_session, CardPath, card.id)
    assert path.totals["goals"] == 1 and path.totals["assists"] == 1 and path.totals["ptour_matches"] == 1


async def test_career_second_wind_cuts_fatigue(client, db_session, bot_token):
    config = await _config(db_session)
    _h, user = await _login(client, db_session, bot_token, 970061)
    sw = await _path_card(db_session, user.id, talent="second_wind", stage=2)
    rookie = await _path_card(db_session, user.id, talent="second_wind", stage=0)
    other = await _path_card(db_session, user.id, talent="fighter", stage=4)
    for c in (sw, rookie, other):
        await db_session.refresh(c, ["player"])
    gains = await path_match_service.career_fatigue_gains(
        db_session, {sw.id: 20, rookie.id: 20, other.id: 20}, {c.id: c for c in (sw, rookie, other)}, config,
    )
    assert gains == {sw.id: 15, rookie.id: 20, other.id: 20}


async def test_hunger_streak_grows_and_resets(client, db_session, bot_token):
    await _config(db_session)
    _h, user = await _login(client, db_session, bot_token, 970062)
    one = await _path_card(db_session, user.id, talent="hunger", stage=2)
    two = await _path_card(db_session, user.id, talent="hunger", stage=4)
    for _ in range(4):
        await path_service.update_hunger_streaks(db_session, user.id, {one.id, two.id})
    await path_service.update_hunger_streaks(db_session, user.id, set())
    await db_session.commit()
    assert (await _reload(db_session, CardPath, one.id)).hunger_streak == 0
    assert (await _reload(db_session, CardPath, two.id)).hunger_streak == 2


# --- admin ---------------------------------------------------------------------------------------------


def test_admin_assigns_talents_only_to_fitting_diamonds():
    from app.core.exceptions import ConflictError
    from app.routers.admin_players import validate_path_player

    validate_path_player(NS(path_talent_code=None, rarity=Rarity.common, position=Position.ST))
    validate_path_player(NS(path_talent_code="fighter", rarity=Rarity.diamond, position=Position.ST))
    for bad in (
        NS(path_talent_code="fighter", rarity=Rarity.legendary, position=Position.ST),
        NS(path_talent_code="nope", rarity=Rarity.diamond, position=Position.ST),
        NS(path_talent_code="hold_lead", rarity=Rarity.diamond, position=Position.ST),
    ):
        with pytest.raises(ConflictError):
            validate_path_player(bad)


async def test_admin_overview_lists_talents_stages_and_tasks(client, db_session, bot_token):
    await _config(db_session)
    await path_service.ensure_catalog(db_session)
    await db_session.commit()
    tasks = (await db_session.execute(select(func.count(PathStageTask.id)))).scalar_one()
    assert tasks == len(path_service.TASK_DEFAULTS)
    catalog = await _catalog(db_session)
    assert [s.max_rating for s in catalog.stages] == [65, 74, 84, 89, 96]
    assert len(catalog.talents) == 10


async def test_path_pack_without_academy_players_is_refused_before_payment(client, db_session, bot_token):
    await _config(db_session)
    headers, user = await _login(client, db_session, bot_token, 970031, balance=10_000)
    await create_player(db_session, rarity=Rarity.diamond)  # a regular diamond only
    await create_player(db_session, rarity=Rarity.common)
    pack = await create_pack(db_session, "path-empty", 100, 3, {Rarity.diamond: 0.5, Rarity.common: 0.5}, player_pool="path")

    shop = (await client.get("/api/v1/packs", headers=headers)).json()
    item = next(p for p in shop if p["id"] == pack.id)
    assert item["is_available_now"] is False and "Академии" in item["unavailable_reason"]

    resp = await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "path_pool_empty"
    await db_session.refresh(user)
    assert user.balance == 10_000

    await create_player(db_session, rarity=Rarity.diamond, path_talent_code="fighter")
    shop = (await client.get("/api/v1/packs", headers=headers)).json()
    assert next(p for p in shop if p["id"] == pack.id)["is_available_now"] is True
    assert (await client.post(f"/api/v1/packs/{pack.id}/open", headers=headers, json={})).status_code == 200


async def test_admin_cannot_switch_on_an_empty_academy_pack(client, db_session, bot_token):
    await _config(db_session)
    session = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    admin = {"Authorization": f"Bearer {session.json()['admin_token']}"}
    pack = await create_pack(db_session, "path-off", 100, 1, {Rarity.diamond: 1.0}, player_pool="path", is_active=False)
    resp = await client.post(f"/api/v1/admin/packs/{pack.id}/toggle-active", headers=admin)
    assert resp.status_code == 409 and "Академии" in resp.json()["error"]["message"]
    await create_player(db_session, rarity=Rarity.diamond, path_talent_code="captain", position=Position.CM)
    resp = await client.post(f"/api/v1/admin/packs/{pack.id}/toggle-active", headers=admin)
    assert resp.status_code == 200 and resp.json()["is_active"] is True


async def test_career_applies_static_and_dynamic_talents(db_session):
    from tests.test_career_tactics import _defaults, _runner

    config = await _config(db_session)
    await path_service.ensure_catalog(db_session)
    cfg = _defaults(path_enabled=True, path_talent_cap=8)
    home, away = _runner("a", config=cfg, rating=70), _runner("b", config=cfg, offset=200, rating=80)
    striker = next(p for p in home.on_pitch if p.slot.code == "FWD2")
    keeper = next(p for p in home.on_pitch if p.slot.category == "GK")

    def user_card(engine, code, stage):
        return NS(id=engine.card.id, owner_id=1, path_stage=stage, talent_override=None,
                  player=NS(display_name=engine.card.player.display_name, path_talent_code=code))

    cards = {
        striker.card.id: user_card(striker, "big_matches", 2),   # opponent avg 80 vs 70 → +3
        keeper.card.id: user_card(keeper, "hold_lead", 4),       # dynamic only
    }
    await path_match_service.career_apply_talents(db_session, (home, away), cards, config)
    assert striker.talent_static == 3
    assert keeper.talent_static == 0 and keeper.card.talent["code"] == "hold_lead" and keeper.card.talent["room"] == 8
    _side, lineup, _events = home.state_at(10, 0, 0)
    gk = next(x for x in lineup if x["category"] == "GK")
    assert gk["talent"]["code"] == "hold_lead"
    st = next(x for x in lineup if x["club_card_id"] == striker.card.id)
    plain = next(x for x in lineup if x["category"] == "FWD" and x["club_card_id"] != striker.card.id)
    assert st["rating"] == plain["rating"] + 3
    # Away side has no academy cards: untouched.
    assert all(p.talent_static == 0 and not getattr(p.card, "talent", None) for p in away.on_pitch)


async def test_career_talents_off_when_mechanic_disabled(db_session):
    from tests.test_career_tactics import _defaults, _runner

    config = await _config(db_session, path_enabled=False)
    home, away = _runner("a", config=_defaults()), _runner("b", config=_defaults(), offset=200, rating=90)
    striker = home.on_pitch[-1]
    cards = {striker.card.id: NS(id=striker.card.id, owner_id=1, path_stage=4, talent_override=None,
                                 player=NS(display_name="x", path_talent_code="big_matches"))}
    await path_match_service.career_apply_talents(db_session, (home, away), cards, config)
    assert striker.talent_static == 0
