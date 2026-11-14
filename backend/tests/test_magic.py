"""«Мяч и Магия»: the army of creature cards and captains, runs, battles, limits and rewards."""
import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Position, Rarity, TransactionType
from app.models.game_config import GameConfig
from app.models.magic import MagicRun
from app.models.transaction import CoinTransaction
from app.services import magic_engine
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1/magic"
RARITIES = (Rarity.common, Rarity.rare, Rarity.epic, Rarity.legendary, Rarity.diamond, Rarity.common)


@pytest.fixture(autouse=True)
async def _setup(request, db_session):
    rate_limit_module._hits.clear()
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
    config.magic_enabled = "disabled" not in request.node.name
    await db_session.commit()
    yield


async def _player(client, db_session, bot_token, telegram_id, copies=(3, 2, 1, 1, 1, 1)):
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, telegram_id)
    players = []
    for i, (rarity, n) in enumerate(zip(RARITIES, copies)):
        player = await create_player(db_session, rating=80 + i, position=Position.ST, rarity=rarity,
                                     display_name=f"M{telegram_id}-{i}")
        for _ in range(n):
            await create_user_card(db_session, user.id, player.id, CardSource.seed)
        players.append(player.id)
    await db_session.commit()
    return headers, user.id, players


async def _play_out(client, headers, run):
    """Plays a run to the end the simple way: battles on autopilot, days skipped."""
    for _ in range(80):
        if run["status"] == "finished":
            return run
        rid, v = run["id"], run["version"]
        if run["phase"] == "battle":
            run = (await client.post(f"{API}/runs/{rid}/battle/auto", headers=headers, json={"version": v})).json()
        elif run["phase"] == "battle_over":
            run = (await client.post(f"{API}/runs/{rid}/battle/leave", headers=headers, json={"version": v})).json()
        elif run["phase"] == "choice":
            code = run["pending"]["options"][0]["code"]
            run = (await client.post(f"{API}/runs/{rid}/choose", headers=headers, json={"version": v, "option": code})).json()
        elif run["phase"] == "final_lost":
            run = (await client.post(f"{API}/runs/{rid}/accept", headers=headers, json={"version": v})).json()
        else:
            run = (await client.post(f"{API}/runs/{rid}/end-day", headers=headers, json={"version": v})).json()
    raise AssertionError("run did not finish")


async def test_army_is_built_from_creature_cards_led_by_captains(client, db_session, bot_token):
    headers, _, players = await _player(client, db_session, bot_token, 970001, copies=(4, 1, 1, 1, 1, 1))
    army = (await client.get(f"{API}/army", headers=headers)).json()
    # The starter set: six creatures of both races; the auto pick fits the leadership (10 + level + knight 3).
    assert army["auto"] is True and army["leadership"] == 14 and len(army["stacks"]) == 5
    assert army["leadership_used"] <= army["leadership"] and not any(s["unruly"] for s in army["stacks"])
    assert {s["faction"] for s in army["stacks"]} == {"dawn", "ash"}  # races mix
    assert all(s["captain"] for s in army["stacks"])  # the best footballers lead them
    caps = {c["card"]["player_id"]: c["cap"] for c in army["captains"]}
    assert caps[players[0]] == 2 and caps[players[4]] == 5  # common leads up to II, diamond up to V
    # A common captain may not lead a tier III creature.
    r = await client.put(f"{API}/army", headers=headers, json={"stacks": [{"unit": "dawn_priest", "captain": players[0]}]})
    assert r.status_code == 409
    saved = (await client.put(f"{API}/army", headers=headers, json={"stacks": [
        {"unit": "dawn_priest", "captain": players[4]}, {"unit": "ash_imp", "captain": players[0]}, {"unit": "dawn_banner"},
    ]})).json()
    assert saved["auto"] is False and [s["unit"] for s in saved["stacks"]] == ["dawn_priest", "ash_imp", "dawn_banner"]
    assert saved["stacks"][0]["captain"]["player_id"] == players[4] and saved["stacks"][2]["captain"] is None
    assert saved["leadership_used"] == 3 + 2 + 1
    # The mage leads less (10 + 1 − 2 = 9).
    assert (await client.get(f"{API}/army?hero_class=mage", headers=headers)).json()["leadership"] == 9
    # Same captain twice, a creature not in the collection, a foreign footballer.
    dup = [{"unit": "dawn_banner", "captain": players[4]}, {"unit": "ash_bones", "captain": players[4]}]
    assert (await client.put(f"{API}/army", headers=headers, json={"stacks": dup})).status_code == 409
    assert (await client.put(f"{API}/army", headers=headers, json={"stacks": [{"unit": "dawn_phoenix"}]})).status_code == 403
    _, _, foreign = await _player(client, db_session, bot_token, 970002)
    r = await client.put(f"{API}/army", headers=headers, json={"stacks": [{"unit": "dawn_banner", "captain": foreign[0]}]})
    assert r.status_code == 403
    assert (await client.post(f"{API}/army/auto", headers=headers)).json()["auto"] is True


async def test_stacks_past_the_leadership_are_unruly(client, db_session, bot_token):
    headers, uid, players = await _player(client, db_session, bot_token, 970005)
    await client.get(f"{API}/hub", headers=headers)  # the starter set
    user = await get_user_by_telegram_id(db_session, 970005)
    user.magic_creatures = {"have": {"dawn_phoenix": 3, "ash_dragon": 2, "dawn_guard": 6}}
    await db_session.commit()
    army = (await client.put(f"{API}/army", headers=headers, json={"stacks": [
        {"unit": "dawn_phoenix"}, {"unit": "dawn_guard"}, {"unit": "ash_dragon"},
    ]})).json()
    # 14 leadership: phoenix 8 + guard 5 fit, the dragon (8) does not — it fights at half.
    assert [s["unruly"] for s in army["stacks"]] == [False, False, True]
    assert army["stacks"][2]["count"] == 1 and army["leadership_used"] == 21
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "ash", "difficulty": "easy"})).json()
    assert [s["unit"] for s in run["army"]] == ["dawn_phoenix", "dawn_guard", "ash_dragon"]


async def test_disabled_flag_blocks_runs(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970003)
    assert (await client.get(f"{API}/hub", headers=headers)).json()["enabled"] is False
    r = await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})
    assert r.status_code == 409


async def test_hub_lists_factions_and_difficulties(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970004)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert [f["code"] for f in hub["factions"]] == ["dawn", "ash"]
    assert all(len([u for u in f["units"] if not u["note"]]) == 5 and len(f["units"]) == 8 and len(f["spells"]) == 3 for f in hub["factions"])
    assert [d["code"] for d in hub["difficulties"]] == ["easy", "normal", "hard"]
    assert hub["hero"]["level"] == 1 and len(hub["army"]) == 5


async def test_full_run_pays_once_and_grows_the_hero(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(magic_engine, "EVENT_CHANCE", 0)  # no purse of gold on the way
    monkeypatch.setattr(magic_engine, "QUEST_GOLD", 0)
    headers, uid, _ = await _player(client, db_session, bot_token, 970010)
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "ash", "difficulty": "normal"})).json()
    assert run["phase"] == "map" and run["day"] == 1 and len(run["army"]) == 5 and run["reachable"]
    again = await client.post(f"{API}/runs", headers=headers, json={"faction": "ash", "difficulty": "normal"})
    assert again.status_code == 409 and again.json()["error"]["details"]["active_run_id"] == run["id"]

    done = await _play_out(client, headers, run)
    assert done["result"] in ("win", "loss") and done["battle"]["kind"] == "final"
    config = await db_session.get(GameConfig, 1)
    base = config.magic_reward_win if done["result"] == "win" else config.magic_reward_loss
    assert done["reward_coins"] == base
    assert done["xp_gained"] == done["score"] * 75 // 100  # quick: hero XP counts ×0.75
    user = await get_user_by_telegram_id(db_session, 970010)
    await db_session.refresh(user)
    assert user.magic_hero_xp == done["score"] and user.magic_rewarded_attempts_today == 1
    assert user.magic_rating == max(0, done["rating_delta"])
    txs = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == uid, CoinTransaction.type == TransactionType.magic_reward,
    ))).scalars().all()
    assert len(txs) == 1 and txs[0].amount == done["reward_coins"]


async def test_stale_versions_conflict_and_retries_are_noops(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970020)
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    x, y = run["reachable"][0]
    body = {"version": run["version"], "x": x, "y": y}
    moved = (await client.post(f"{API}/runs/{run['id']}/move", headers=headers, json=body)).json()
    assert moved["version"] == run["version"] + 1
    retry = (await client.post(f"{API}/runs/{run['id']}/move", headers=headers, json=body)).json()
    assert retry["version"] == moved["version"]
    stale = await client.post(f"{API}/runs/{run['id']}/end-day", headers=headers, json={"version": run["version"]})
    assert stale.status_code == 409


async def test_manual_battle_actions(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970030)
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    for _ in range(10):  # skip to the final battle
        if run["phase"] != "map":
            break
        run = (await client.post(f"{API}/runs/{run['id']}/end-day", headers=headers, json={"version": run["version"]})).json()
    assert run["phase"] == "battle"
    battle = run["battle"]
    assert battle["can_act"] and battle["move_cells"] and battle["can_cast"]
    unit = battle["turn_of"]
    ally = next(u for u in battle["units"] if u["side"] == "me")
    cast = (await client.post(f"{API}/runs/{run['id']}/battle/cast", headers=headers,
                              json={"version": run["version"], "spell": "bless", "target": ally["id"]})).json()
    assert cast["battle"]["can_cast"] is False and cast["hero"]["mana"] < run["hero"]["mana"]
    wrong = await client.post(f"{API}/runs/{run['id']}/battle/act", headers=headers,
                              json={"version": cast["version"], "unit": "e1", "action": "defend"})
    assert wrong.status_code == 409
    acted = (await client.post(f"{API}/runs/{run['id']}/battle/act", headers=headers,
                               json={"version": cast["version"], "unit": unit, "action": "defend"})).json()
    assert acted["events"] and acted["version"] == cast["version"] + 1


async def test_forfeit_pays_nothing(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970040)
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "hard"})).json()
    done = (await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)).json()
    assert done["status"] == "finished" and done["result"] == "loss" and done["reward_coins"] == 0 and done["xp_gained"] == 0


async def test_free_runs_then_an_extra_run_for_coins_then_for_stars(client, db_session, bot_token):
    from app.services import magic_service

    headers, uid, _ = await _player(client, db_session, bot_token, 970050)
    config = await db_session.get(GameConfig, 1)
    config.magic_daily_limit = 1
    config.magic_extra_run_coins = 300
    await db_session.commit()
    user = await get_user_by_telegram_id(db_session, 970050)
    user.balance = 1000
    await db_session.commit()
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    await _play_out(client, headers, run)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    quick = hub["modes"][0]
    assert hub["free_left"] == quick["free_left"] == 0 and hub["extra_price_coins"] == quick["price_coins"] == 300
    await db_session.refresh(user)
    balance = user.balance
    r = await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})
    assert r.status_code == 409 and r.json()["error"]["details"]["reason"] == "no_runs"
    bought = (await client.post(f"{API}/extra-run", headers=headers)).json()
    assert bought["bonus_runs"] == 1 and bought["balance"] == balance - 300 and bought["mode"] == "quick"
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["can_start"] and hub["extra_price_coins"] is None and hub["extra_price_stars"] == config.magic_extra_run_stars
    assert hub["modes"][0]["bank"] == 1 and hub["modes"][2]["bank"] == 0  # bought for the quick mode only
    assert (await client.post(f"{API}/extra-run", headers=headers)).status_code == 409  # the next one is for Stars
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    assert run["phase"] == "map"
    # Stars: pre-checkout checks the price, delivery banks a run.
    await db_session.refresh(user)
    day = magic_service.local_today().isoformat()
    ok, _ = await magic_service.validate_extra_run_stars(db_session, uid, f"quick:{day}", config.magic_extra_run_stars)
    assert ok
    ok, _ = await magic_service.validate_extra_run_stars(db_session, uid, day, config.magic_extra_run_stars)
    assert ok  # an invoice of the old shape: the quick mode
    await db_session.refresh(user)
    await magic_service.deliver_extra_run_stars(db_session, user, f"quick:{day}")
    await db_session.commit()
    await db_session.refresh(user)
    assert user.magic_runs_day["quick"]["bank"] == 1 and user.magic_runs_day["quick"]["stars"] == 1


async def test_every_mode_has_its_own_runs_of_the_day(client, db_session, bot_token):
    from app.services import magic_service

    headers, uid, _ = await _player(client, db_session, bot_token, 970051)
    user = await get_user_by_telegram_id(db_session, 970051)
    user.balance = 5000
    await db_session.commit()
    config = await db_session.get(GameConfig, 1)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    adv = next(m for m in hub["modes"] if m["code"] == "adventure")
    assert adv["free_total"] == adv["free_left"] == config.magic_adventure_daily_limit == 1
    assert adv["price_coins"] == config.magic_adventure_run_coins and adv["stars_left"] == 1
    body = {"faction": "dawn", "difficulty": "easy", "mode": "adventure"}
    run = (await client.post(f"{API}/runs", headers=headers, json=body)).json()
    await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    # The adventure took its own free run, the quick runs are all still there.
    assert hub["modes"][2]["free_left"] == 0 and hub["modes"][0]["free_left"] == config.magic_daily_limit
    r = await client.post(f"{API}/runs", headers=headers, json=body)
    assert r.status_code == 409 and r.json()["error"]["details"]["mode"] == "adventure"
    assert r.json()["error"]["details"]["price_coins"] == config.magic_adventure_run_coins
    # One for coins, then one for Stars, then the adventure is over for today.
    bought = (await client.post(f"{API}/extra-run?mode=adventure", headers=headers)).json()
    assert bought["mode"] == "adventure" and bought["bonus_runs"] == 1
    assert (await client.post(f"{API}/extra-run?mode=adventure", headers=headers)).status_code == 409
    await db_session.refresh(user)
    product, stars, _, _ = await magic_service.extra_run_stars_order(db_session, user, "adventure")
    assert product.startswith("magic_run:adventure:") and stars == config.magic_adventure_run_stars
    await magic_service.deliver_extra_run_stars(db_session, user, product.partition(":")[2])
    await db_session.commit()
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    adv = hub["modes"][2]
    assert adv["bank"] == 2 and adv["price_coins"] is None and adv["price_stars"] is None
    # The weekly challenge has a try of its own.
    assert hub["challenge_left"] == 1


async def test_second_chance_in_the_final_for_coins(client, db_session, bot_token, monkeypatch):
    headers, uid, _ = await _player(client, db_session, bot_token, 970070)
    user = await get_user_by_telegram_id(db_session, 970070)
    user.balance = 1000
    await db_session.commit()
    monkeypatch.setitem(magic_engine.DIFFICULTY["hard"], "power", 2000)  # a sure loss
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "hard"})).json()
    for _ in range(20):
        if run["phase"] == "final_lost":
            break
        rid, v = run["id"], run["version"]
        if run["phase"] == "battle":
            run = (await client.post(f"{API}/runs/{rid}/battle/auto", headers=headers, json={"version": v})).json()
        else:
            run = (await client.post(f"{API}/runs/{rid}/end-day", headers=headers, json={"version": v})).json()
    assert run["phase"] == "final_lost" and run["status"] == "in_progress"
    assert run["retry"]["available"] and run["retry"]["coins"] == 250
    body = {"version": run["version"], "pay": "coins"}
    again = (await client.post(f"{API}/runs/{run['id']}/retry", headers=headers, json=body)).json()
    assert again["phase"] in ("battle", "final_lost", "finished")
    repeat = (await client.post(f"{API}/runs/{run['id']}/retry", headers=headers, json=body)).json()
    assert repeat["version"] == again["version"]  # a retried request is not charged twice
    await db_session.refresh(user)
    assert user.balance == 750 and user.magic_retries_today == 1
    done = await _play_out(client, headers, again)
    assert done["result"] == "loss" and done["retry"] is None


async def test_chest_choice_and_gold_become_coins(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(magic_engine, "EVENT_CHANCE", 0)  # no purse of gold on the way
    monkeypatch.setattr(magic_engine, "QUEST_GOLD", 0)
    headers, _, _ = await _player(client, db_session, bot_token, 970080)
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    stored = await db_session.get(MagicRun, run["id"])
    state = dict(stored.server_state)
    hidden = [o for o in state["map"]["objects"] if not magic_engine.is_seen(state, o["x"], o["y"])]
    assert hidden and len(run["objects"]) == len(state["map"]["objects"]) - len(hidden)  # the fog
    assert run["bot"]["visible"] is False and "x" not in run["bot"]
    stored.server_state = {**state, "hero": {**state["hero"], "gold": 500}}
    await db_session.commit()
    done = await _play_out(client, headers, (await client.get(f"{API}/runs/{run['id']}", headers=headers)).json())
    config = await db_session.get(GameConfig, 1)
    assert done["gold_coins"] == 500 * config.magic_gold_coins_pct // 100
    base = config.magic_reward_win if done["result"] == "win" else config.magic_reward_loss
    assert done["reward_coins"] == base * config.magic_easy_reward_pct // 100 + done["gold_coins"]


async def test_won_hard_run_can_drop_the_configured_pack(client, db_session, bot_token, monkeypatch):
    from tests.factories import create_pack

    pack = await create_pack(db_session, "magic-test", 100, 1, {Rarity.common: 100})
    config = await db_session.get(GameConfig, 1)
    config.magic_pack_id = pack.id
    config.magic_pack_chance_hard_pct = 100
    await db_session.commit()
    headers, _, _ = await _player(client, db_session, bot_token, 970060)
    monkeypatch.setitem(magic_engine.DIFFICULTY["hard"], "power", 5)  # a sure win
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "hard"})).json()
    done = await _play_out(client, headers, run)
    assert done["result"] == "win"
    stored = await db_session.get(MagicRun, done["id"])
    assert stored.pack_opening_id is not None and done["pack_name"] == pack.name


async def test_hardcore_mode_starts_a_big_map(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970077)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert [m["code"] for m in hub["modes"]] == ["quick", "hardcore", "adventure"]
    run = (await client.post(f"{API}/runs", headers=headers,
                             json={"faction": "dawn", "difficulty": "normal", "mode": "hardcore"})).json()
    assert run["mode"] == "hardcore" and run["map_w"] == 60 and run["days"] == hub["modes"][1]["days"] == 14
    after = (await client.get(f"{API}/hub", headers=headers)).json()
    assert after["modes"][1]["free_left"] == hub["modes"][1]["free_left"] - 1  # its own run of the day
    assert after["free_left"] == hub["free_left"]  # the quick runs untouched
    x, y = run["reachable"][0]
    moved = (await client.post(f"{API}/runs/{run['id']}/move", headers=headers,
                               json={"version": run["version"], "x": x, "y": y})).json()
    assert moved["hero"]["x"] == x


async def test_adventure_has_no_rival_and_ends_with_the_faceless_boss(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970078)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    adv = next(m for m in hub["modes"] if m["code"] == "adventure")
    assert adv["days"] == 31 and adv["runs"] == 1 and adv["reward_pct"] == 400
    run = (await client.post(f"{API}/runs", headers=headers,
                             json={"faction": "ash", "difficulty": "normal", "mode": "adventure"})).json()
    assert run["mode"] == "adventure" and run["days"] == 31 and run["bot"]["visible"] is False and run["bot_style"] is None
    after = (await client.get(f"{API}/hub", headers=headers)).json()
    assert after["modes"][2]["free_left"] == 0 and after["free_left"] == hub["free_left"]
    # The fog rows also come as hex: exact where a JS number (53 bits) would not be.
    assert len(run["seen_hex"]) == 76 and [int(h, 16) for h in run["seen_hex"]] == run["seen"]
    lair = [o for o in run["objects"] if o["kind"] == "castle" and o["label"] == "Логово Безликого"]
    assert not lair  # far away in the fog


async def test_weekly_challenge_is_the_same_map_and_has_a_table(client, db_session, bot_token):
    a, _, _ = await _player(client, db_session, bot_token, 970091)
    b, _, _ = await _player(client, db_session, bot_token, 970092)
    body = {"faction": "dawn", "difficulty": "hard", "mode": "hardcore", "challenge": True}
    ra = (await client.post(f"{API}/runs", headers=a, json=body)).json()
    rb = (await client.post(f"{API}/runs", headers=b, json={**body, "faction": "ash"})).json()
    assert ra["challenge_week"] and ra["mode"] == "quick" and ra["difficulty"] == "normal"
    assert ra["blocks"] == rb["blocks"] and ra["road"] == rb["road"]
    await _play_out(client, a, ra)
    hub = (await client.get(f"{API}/hub", headers=a)).json()
    assert hub["challenge"]["plays"] == 1 and hub["challenge"]["top"][0]["me"] is True


async def test_starter_creatures_and_a_magic_pack_for_coins_and_stars(client, db_session, bot_token):
    from app.services import magic_service

    headers, uid, _ = await _player(client, db_session, bot_token, 970090)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    # The starter set: 7 cards of each faction.
    per_faction = sum(magic_engine.CARD_FIGHTERS[t] for t in magic_engine.STARTER_TIERS)
    for f in ("dawn", "ash"):
        assert sum(c["fighters"] for c in hub["creatures"] if c["faction"] == f) == per_faction
    assert hub["creature_pack"]["size"] == 5 and sum(hub["creature_pack"]["odds"].values()) == 100
    again = (await client.get(f"{API}/hub", headers=headers)).json()
    assert again["creatures"] == hub["creatures"]  # granted once
    user = await get_user_by_telegram_id(db_session, 970090)
    user.balance = 3000
    await db_session.commit()
    opened = (await client.post(f"{API}/creature-pack", headers=headers)).json()
    assert len(opened["cards"]) == 5
    assert opened["balance"] == 3000 - 2000
    total = lambda rows: sum(c["fighters"] for c in rows)  # noqa: E731
    assert total(opened["creatures"]) == total(hub["creatures"]) + total(opened["cards"])
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert [c["unit"] for c in hub["last_pack"]] == [c["unit"] for c in opened["cards"]]
    assert (await client.post(f"{API}/creature-pack", headers=headers)).status_code == 400  # 1000 coins left
    # Stars: the price is checked, delivery opens the pack.
    ok, _ = await magic_service.validate_creature_pack_stars(db_session, 15)
    assert ok and not (await magic_service.validate_creature_pack_stars(db_session, 5))[0]
    await db_session.refresh(user)
    out = await magic_service.deliver_creature_pack_stars(db_session, user)
    await db_session.commit()
    assert len(out["cards"]) == 5
    hub2 = (await client.get(f"{API}/hub", headers=headers)).json()
    assert total(hub2["creatures"]) == total(hub["creatures"]) + sum(
        magic_engine.CARD_FIGHTERS[magic_engine.UNITS[c]["tier"]] for c in out["cards"])


async def test_a_run_costs_the_collection_dead_give_essence_wounded_come_back(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    from app.services import magic_service

    headers, uid, _ = await _player(client, db_session, bot_token, 970120)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["risk"]["dead_pct"] == {"quick": 50, "hardcore": 100, "adventure": 50} and hub["essence"] == 0
    before = {c["unit"]: c["fighters"] for c in hub["creatures"]}
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    # The run lost 6 of the first stack's own fighters.
    r = (await db_session.execute(select(MagicRun).where(MagicRun.id == run["id"]))).scalar_one()
    unit = run["army"][0]["unit"]
    state = dict(r.server_state)
    state["fallen"] = {unit: 6}
    r.server_state = state
    await db_session.commit()
    done = (await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)).json()
    cas = done["casualties"]
    assert [(c["unit"], c["count"]) for c in cas["dead"]] == [(unit, 3)]
    assert [(c["unit"], c["count"]) for c in cas["wounded"]] == [(unit, 3)] and cas["until"]
    tier = magic_engine.UNITS[unit]["tier"]
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    after = {c["unit"]: c["fighters"] for c in hub["creatures"]}
    assert after.get(unit, 0) == before[unit] - 6
    assert hub["essence"] == 3 * magic_engine.ESSENCE[tier] and [w["count"] for w in hub["wounded"]] == [3]
    # Healing now costs the essence of the wounded; there's just enough.
    assert hub["heal_essence"] == 3 * magic_engine.ESSENCE[tier]
    healed = (await client.post(f"{API}/heal", headers=headers)).json()
    assert healed["healed"] == 3 and healed["essence"] == 0
    assert (await client.post(f"{API}/heal", headers=headers)).status_code == 409  # nobody to heal
    # The wounded also come back by themselves when their time is up.
    user = await get_user_by_telegram_id(db_session, 970120)
    data = dict(user.magic_creatures)
    data["wounded"] = [{"unit": unit, "count": 2, "until": (datetime.now(timezone.utc) - timedelta(minutes=1)).isoformat()}]
    user.magic_creatures = data
    await db_session.commit()
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["wounded"] == [] and {c["unit"]: c["fighters"] for c in hub["creatures"]}[unit] == before[unit] - 3 + 2
    # Stars heal: checked at pre-checkout (nobody wounded → refused).
    await db_session.refresh(user)
    assert not (await magic_service.validate_heal_stars(db_session, uid, 10))[0]


async def test_an_empty_collection_gets_the_free_starter_set_once_a_day(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970121)
    await client.get(f"{API}/hub", headers=headers)
    user = await get_user_by_telegram_id(db_session, 970121)
    user.magic_creatures = {"have": {}, "essence": 5}
    await db_session.commit()
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    per_faction = sum(magic_engine.CARD_FIGHTERS[t] for t in magic_engine.STARTER_TIERS)
    assert sum(c["fighters"] for c in hub["creatures"]) == per_faction and hub["refill_today"] is True
    assert hub["essence"] == 5
    await db_session.refresh(user)
    data = dict(user.magic_creatures)
    data["have"] = {}
    user.magic_creatures = data
    await db_session.commit()
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["creatures"] == []  # once a day


async def test_the_essence_shop_sells_packs_bonuses_and_skins(client, db_session, bot_token):
    from app.models.monetization import Cosmetic

    headers, _, _ = await _player(client, db_session, bot_token, 970130)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    lead0 = hub["leadership_by_class"]["knight"]
    mana0 = next(c["mana"] for c in hub["hero_classes"] if c["code"] == "knight")
    skin = Cosmetic(kind="magic_hero", name="Тест", style_key="magic_hero_gold", coins_price=0, stars_price=25)
    db_session.add(skin)
    user = await get_user_by_telegram_id(db_session, 970130)
    data = dict(user.magic_creatures)
    data["essence"] = 2000
    user.magic_creatures = data
    config = await db_session.get(GameConfig, 1)
    config.magic_essence_leadership, config.magic_essence_mana = 150, 120
    await db_session.commit()
    shop = (await client.get(f"{API}/shop", headers=headers)).json()
    codes = {i["code"]: i for i in shop["items"]}
    assert shop["essence"] == 2000 and codes["pack"]["price"] == 300
    assert codes["leadership"]["price"] == 150 and codes["mana"]["price"] == 120
    assert codes[f"skin:{skin.id}"]["price"] == 25 * config.magic_essence_per_star == 250  # 1 ⭐ = 100 coins = 10 essence
    buy = lambda code: client.post(f"{API}/shop/buy", headers=headers, json={"code": code})  # noqa: E731
    r = (await buy("pack")).json()
    assert len(r["cards"]) == 5 and r["essence"] == 1700
    assert (await buy("leadership")).json()["essence"] == 1550
    assert (await buy("leadership")).json()["essence"] == 1250  # the second costs ×2
    assert (await buy("mana")).json()["essence"] == 1130
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["leadership_by_class"]["knight"] == lead0 + 2
    assert next(c["mana"] for c in hub["hero_classes"] if c["code"] == "knight") == mana0 + 1
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    assert run["hero"]["max_mana"] == mana0 + 1
    await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)
    assert (await buy(f"skin:{skin.id}")).json()["essence"] == 880
    assert (await buy(f"skin:{skin.id}")).status_code == 409  # already owned
    assert (await buy("pack")).json()["essence"] == 580
    assert (await buy("nothing")).status_code == 404
    shop = (await client.get(f"{API}/shop", headers=headers)).json()
    assert {i["code"]: i for i in shop["items"]}[f"skin:{skin.id}"]["available"] is False


async def test_captains_level_from_duplicates_and_the_guard_refills(client, db_session, bot_token):
    headers, uid, players = await _player(client, db_session, bot_token, 970140, copies=(4, 3, 1, 1, 1, 1))
    army = (await client.get(f"{API}/army", headers=headers)).json()
    cap = next(c for c in army["captains"] if c["card"]["player_id"] == players[0])
    assert cap["level"] == 1 and cap["copies"] == 4
    # One copy a day: +150 XP; more today is refused.
    assert (await client.post(f"{API}/captains/{players[0]}/feed", headers=headers, json={"count": 2})).status_code == 409
    fed = (await client.post(f"{API}/captains/{players[0]}/feed", headers=headers, json={"count": 1})).json()
    cap = next(c for c in fed["captains"] if c["card"]["player_id"] == players[0])
    assert cap["xp"] == 150 and cap["copies"] == 3 and cap["fed_left"] == 0 and cap["dup_xp"] == 150
    assert (await client.post(f"{API}/captains/{players[0]}/feed", headers=headers, json={"count": 1})).status_code == 409
    # Level 3 (a trait slot) — from runs over weeks; here set directly.
    user = await get_user_by_telegram_id(db_session, 970140)
    await db_session.refresh(user)
    data = dict(user.magic_creatures)
    data["captains"] = {str(players[0]): {"xp": 8000}}
    user.magic_creatures = data
    await db_session.commit()
    r = await client.post(f"{API}/captains/{players[0]}/trait", headers=headers, json={"code": "striker"})
    assert next(c for c in r.json()["captains"] if c["card"]["player_id"] == players[0])["traits"] == ["striker"]
    assert (await client.post(f"{API}/captains/{players[0]}/trait", headers=headers, json={"code": "wall"})).status_code == 409
    # The guard: led by players[1] (a rare one, 3 copies); 2 spares of the same footballer → 2 fighters.
    g = (await client.put(f"{API}/guard", headers=headers, json={"player_id": players[1]})).json()["guard"]
    assert g["card"]["player_id"] == players[1] and g["count"] == 0 and g["size"] == 15 and g["unit"] == "magic_guard"
    g = (await client.post(f"{API}/guard/refill?count=2", headers=headers, json={"player_id": players[1]})).json()["guard"]
    assert g["count"] == 2 and g["points"] == 0
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
    assert any(s["unit"] == "magic_guard" and s["count"] == 2 for s in run["army"])
    r = (await db_session.execute(select(MagicRun).where(MagicRun.id == run["id"]))).scalar_one()
    state = dict(r.server_state)
    state["fallen"] = {"magic_guard": 2}
    r.server_state = state
    await db_session.commit()
    done = (await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)).json()
    assert done["casualties"]["guard_lost"] == 1
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["guard"]["count"] == 1
    # Another rarity: a legendary guard has fewer, heavier fighters — the weight carries over.
    g = (await client.put(f"{API}/guard", headers=headers, json={"player_id": players[3]})).json()["guard"]
    assert g["unit"] == "magic_guard_legend" and g["size"] == 3 and g["count"] == 0 and g["points"] == 6


async def test_the_days_runs_go_in_a_row_and_the_challenge_caps_progress(client, db_session, bot_token):
    headers, uid, players = await _player(client, db_session, bot_token, 970142)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["free_left"] == 3
    for _ in range(3):  # the quick mode's day, run in a row: magic is limited by the day only
        run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
        assert run["phase"] == "map"
        await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)
    user = await get_user_by_telegram_id(db_session, 970142)
    await db_session.refresh(user)
    data = dict(user.magic_creatures)
    data["captains"] = {str(p): {"xp": 99999, "traits": ["striker", "wall"]} for p in players}
    user.magic_creatures = data
    await db_session.commit()
    run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "normal", "challenge": True})).json()
    assert "id" in run, run
    r = (await db_session.execute(select(MagicRun).where(MagicRun.id == run["id"]))).scalar_one()
    assert all(s.get("level", 1) <= 3 and len(s.get("traits") or []) <= 1 for s in r.server_state["army"])


async def test_the_free_revival_works_once(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 970141)
    hub = (await client.get(f"{API}/hub", headers=headers)).json()
    assert hub["revive"] is None
    before = {c["unit"]: c["fighters"] for c in hub["creatures"]}
    for attempt in range(2):
        run = (await client.post(f"{API}/runs", headers=headers, json={"faction": "dawn", "difficulty": "easy"})).json()
        unit = run["army"][0]["unit"]
        r = (await db_session.execute(select(MagicRun).where(MagicRun.id == run["id"]))).scalar_one()
        state = dict(r.server_state)
        state["fallen"] = {unit: 4}
        r.server_state = state
        await db_session.commit()
        await client.post(f"{API}/runs/{run['id']}/forfeit", headers=headers)
        hub = (await client.get(f"{API}/hub", headers=headers)).json()
        if attempt == 0:
            assert [(d["unit"], d["count"]) for d in hub["revive"]["dead"]] == [(unit, 2)]
            back = (await client.post(f"{API}/revive", headers=headers)).json()
            assert back["healed"] == 2 and back["essence"] == 0
            have = {c["unit"]: c["fighters"] for c in back["creatures"]}
            assert have[unit] == before[unit] - 2  # only the wounded are still away
        else:
            assert hub["revive"] is None  # once
            assert (await client.post(f"{API}/revive", headers=headers)).status_code == 409


def test_a_move_reaches_the_far_corner_of_the_adventure_map():
    from app.schemas.magic import MagicMoveRequest
    n = magic_engine.MODES["adventure"]["n"]
    assert MagicMoveRequest(version=1, x=n - 1, y=n - 1).x == n - 1
