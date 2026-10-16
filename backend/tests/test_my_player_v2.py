"""«Мой игрок» v2: level-up screen, training drills and streak, freshness,
friend duels, line change, Stars cosmetics, «Имущество» effects and income,
«Карьера игрока» salary / objectives / history, the share image."""
import io
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest
from PIL import Image
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.card_skill import UserSkillToken
from app.models.career import Friendship
from app.models.enums import NotificationType, Position, TransactionType
from app.models.lifestyle import LifestyleItem, UserLifestyleItem
from app.models.notification import Notification
from app.models.player_career import PlayerCareerSeason
from app.models.transaction import CoinTransaction
from app.models.user import User
from app.services import my_player_service, player_career_service, share_service
from app.services.game_config_service import get_config
from tests.factories import get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"
LOOK = {"skin": 2, "hair": 1, "hair_color": 1, "beard": 1, "eye_color": 3, "kit": 4, "kit_pattern": 1}


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


@pytest.fixture(autouse=True)
def _share_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(share_service, "SHARE_DIR", tmp_path / "share")


async def _login(client, db_session, bot_token, tg_id):
    await client.post(f"{API}/auth/session", headers=telegram_headers(tg_id, bot_token))
    user = await get_user_by_telegram_id(db_session, tg_id)
    return user.id, telegram_headers(tg_id, bot_token)


async def _create(client, headers, **overrides):
    body = {"name": "Виктор Ж.", "number": 9, "position": "ST", "appearance": LOOK, **overrides}
    resp = await client.post(f"{API}/my-player", headers=headers, json=body)
    assert resp.status_code == 200, resp.text
    return resp.json()


async def _befriend(db_session, a: int, b: int):
    db_session.add(Friendship(
        requester_id=a, addressee_id=b, user_low=min(a, b), user_high=max(a, b), status="accepted",
    ))
    await db_session.commit()


async def test_level_up_screen_shows_once_per_new_level(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890001)
    view = await _create(client, headers)
    assert view["level_up"] is None and view["level_seen"] == 1
    assert view["attention"]["training"] and not view["attention"]["level_up"]

    user = await db_session.get(User, user_id)
    config = await get_config(db_session)
    user.my_player_xp = my_player_service.xp_for_next(1, config) + my_player_service.xp_for_next(2, config)
    await db_session.commit()
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["level"] == 3
    assert view["level_up"] == {"from_level": 1, "to_level": 3, "points": 2 * config.my_player_points_per_level}
    assert view["attention"]["level_up"] and view["attention"]["points"]

    view = (await client.post(f"{API}/my-player/level-seen", headers=headers)).json()
    assert view["level_up"] is None and view["level_seen"] == 3
    assert not view["attention"]["level_up"]


async def test_drill_follows_weekday_and_line(client, db_session, bot_token):
    monday = datetime(2026, 10, 12).date()
    assert my_player_service.drill_for(Position.ST, monday) == "shot"
    assert my_player_service.drill_for(Position.GK, monday) == "save"
    assert my_player_service.drill_for(Position.CB, monday) == "tackle"
    assert my_player_service.drill_for(Position.CM, monday) == "pass"
    _, headers = await _login(client, db_session, bot_token, 890002)
    view = await _create(client, headers, position="GK")
    assert view["training"]["drill"]["code"] in my_player_service.DRILLS
    assert view["training"]["streak"] == 0 and view["training"]["streak_left"] == 7


async def test_training_streak_pays_skill_tokens_and_resets(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890003)
    await _create(client, headers)
    config = await get_config(db_session)
    config.my_player_streak_days = 3
    config.my_player_streak_tokens = 2
    await db_session.commit()
    user = await db_session.get(User, user_id)
    start = datetime.now(timezone.utc).replace(hour=9, minute=0, second=0, microsecond=0) - timedelta(days=10)

    async def run(day: int):
        at = start + timedelta(days=day)
        await my_player_service.training_start(db_session, user, now=at)
        return await my_player_service.training_finish(db_session, user, 1, now=at + timedelta(seconds=6))

    assert (await run(0))["streak_reward"] is None
    assert (await run(1))["streak_reward"] is None
    reward = (await run(2))["streak_reward"]
    assert reward and reward["tokens"] == 2 and reward["streak"] == 3
    token = (await db_session.execute(select(UserSkillToken).where(
        UserSkillToken.user_id == user_id, UserSkillToken.skill_code == reward["skill_code"],
    ))).scalar_one()
    assert token.quantity == 2
    # A missed day starts the streak over.
    assert (await run(4))["streak_reward"] is None
    mp = await my_player_service.get_my_player(db_session, user_id)
    assert mp.training_streak == 1


async def test_freshness_regen_penalty_and_training(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890004)
    await _create(client, headers)
    config = await get_config(db_session)
    mp = await my_player_service.get_my_player(db_session, user_id)
    now = datetime.now(timezone.utc)
    my_player_service.set_freshness(mp, 0, now - timedelta(hours=10))
    await db_session.commit()
    assert my_player_service.freshness_now(mp, config, now) == 10 * config.my_player_freshness_regen_per_hour
    assert my_player_service.fatigue_penalty(0, config) == config.my_player_fatigue_max_penalty
    assert my_player_service.fatigue_penalty(100, config) == 0

    card = await my_player_service.engine_card(db_session, user_id, config)
    fresh_rating = my_player_service.rating_of(mp, config)
    assert card.player.rating < fresh_rating  # tired → weaker in matches

    # An «Имущество» regen bonus speeds recovery up.
    item = LifestyleItem(name="Машина", category="car", coins_price=1, prestige=1, effect="freshness_regen", effect_value=3)
    db_session.add(item)
    await db_session.flush()
    db_session.add(UserLifestyleItem(user_id=user_id, item_id=item.id))
    await db_session.commit()
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["freshness"]["regen_per_hour"] == config.my_player_freshness_regen_per_hour + 3
    assert view["freshness"]["regen_bonus"] == 3


async def test_friend_duel_rewards_challenger_and_notifies_friend(client, db_session, bot_token):
    a_id, a_headers = await _login(client, db_session, bot_token, 890005)
    b_id, b_headers = await _login(client, db_session, bot_token, 890006)
    c_id, c_headers = await _login(client, db_session, bot_token, 890007)
    await _create(client, a_headers)
    await _create(client, b_headers, name="Друг Игрок", position="CB")
    config = await get_config(db_session)
    config.my_player_duels_per_day = 2
    await db_session.commit()

    # Not a friend yet / friend without a player.
    assert (await client.post(f"{API}/my-player/duels", headers=a_headers, json={"opponent_user_id": b_id})).status_code == 409
    await _befriend(db_session, a_id, b_id)
    await _befriend(db_session, a_id, c_id)
    assert (await client.post(f"{API}/my-player/duels", headers=a_headers, json={"opponent_user_id": c_id})).status_code == 409

    duels = (await client.get(f"{API}/my-player/duels", headers=a_headers)).json()
    assert [f["user_id"] for f in duels["friends"]] == [b_id] and duels["left_today"] == 2

    balance_before = (await db_session.get(User, a_id)).balance
    resp = await client.post(f"{API}/my-player/duels", headers=a_headers, json={"opponent_user_id": b_id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    duel = body["duel"]
    assert len(duel["events"]) == 2 * my_player_service.DUEL_ATTACKS
    goals = sum(1 for e in duel["events"] if e["side"] == "me" and e["outcome"] == "goal")
    assert goals == duel["my_goals"]
    expected = {"win": config.my_player_duel_reward_win, "draw": config.my_player_duel_reward_draw, "loss": 0}[duel["result"]]
    assert duel["reward_coins"] == expected and body["balance"] == balance_before + expected
    assert body["duels"]["left_today"] == 1

    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == b_id, Notification.type == NotificationType.my_player_duel,
    ))).scalars().all()
    assert len(notes) == 1
    # The friend sees it from his side, without a reward.
    seen = (await client.get(f"{API}/my-player/duels", headers=b_headers)).json()["recent"][0]
    assert not seen["as_challenger"] and seen["reward_coins"] == 0
    assert seen["my_goals"] == duel["opp_goals"] and seen["opp_goals"] == duel["my_goals"]

    assert (await client.post(f"{API}/my-player/duels", headers=a_headers, json={"opponent_user_id": b_id})).status_code == 200
    third = await client.post(f"{API}/my-player/duels", headers=a_headers, json={"opponent_user_id": b_id})
    assert third.status_code == 409  # daily limit


def test_duel_chance_follows_attack_vs_defense():
    strong = {"attack": 95, "defense": 80}
    weak = {"attack": 45, "defense": 40}
    rng = random.Random(1)
    totals = [0, 0]
    for _ in range(200):
        mine, theirs, _ = my_player_service.simulate_duel(strong, weak, rng)
        totals[0] += mine
        totals[1] += theirs
    assert totals[0] > totals[1] * 2


async def test_role_change_for_coins_swaps_key_attribute(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890008)
    view = await _create(client, headers)
    atk, dfn = view["player"]["attributes"]["atk"], view["player"]["attributes"]["def"]
    config = await get_config(db_session)
    user = await db_session.get(User, user_id)
    user.balance = config.my_player_role_change_coins
    await db_session.commit()

    # Free change inside the line is still a PATCH; the paid one is another line only.
    assert (await client.post(f"{API}/my-player/role", headers=headers, json={"position": "LW"})).status_code == 409
    assert (await client.patch(f"{API}/my-player", headers=headers, json={"position": "CB"})).status_code == 409
    resp = await client.post(f"{API}/my-player/role", headers=headers, json={"position": "CB"})
    assert resp.status_code == 200, resp.text
    player = resp.json()["player"]
    assert player["position"] == "CB" and player["category"] == "DEF" and player["key_attr"] == "def"
    assert player["attributes"] == {"atk": dfn, "def": atk}
    assert resp.json()["balance"] == 0
    assert (await client.post(f"{API}/my-player/role", headers=headers, json={"position": "ST"})).status_code == 400  # no coins


async def test_stars_cosmetic_and_role_change(client, db_session, bot_token, monkeypatch):
    from app.services import stars_payment_service
    from tests.test_gifts import INTERNAL_HEADERS, _deliver, _fake_invoice_link

    monkeypatch.setattr(stars_payment_service, "_request_telegram_invoice_link", _fake_invoice_link)
    user_id, headers = await _login(client, db_session, bot_token, 890009)
    await _create(client, headers)
    config = await get_config(db_session)
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    crown = next(c for c in view["cosmetics"]["catalog"] if c["code"] == "crown")
    assert crown["stars_price"] == config.my_player_cosmetic_stars_prices["crown"] and crown["price"] == 0
    assert (await client.post(f"{API}/my-player/cosmetics/buy", headers=headers, json={"code": "crown"})).status_code == 409

    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "cosmetic", "code": "crown"})
    assert resp.status_code == 200, resp.text
    token, stars = resp.json()["payload_token"], resp.json()["stars_amount"]
    pre = await client.post("/api/v1/internal/stars-payments/pre-checkout", headers=INTERNAL_HEADERS,
                            json={"payload_token": token, "total_amount": stars})
    assert pre.json()["ok"] is True
    assert (await _deliver(client, token, 890009, "charge-crown", stars)).status_code == 200
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert "crown" in view["cosmetics"]["owned"] and view["player"]["accessory"] == "crown"
    again = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "cosmetic", "code": "crown"})
    assert again.status_code == 409

    # Effects are a slot of their own.
    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "cosmetic", "code": "fx_fire"})
    await _deliver(client, resp.json()["payload_token"], 890009, "charge-fx", resp.json()["stars_amount"])
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["player"]["effect"] == "fx_fire" and view["player"]["accessory"] == "crown"

    same_line = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "role", "position": "RW"})
    assert same_line.status_code == 409
    resp = await client.post(f"{API}/my-player/stars-invoice", headers=headers, json={"purchase": "role", "position": "CM"})
    assert resp.status_code == 200 and resp.json()["stars_amount"] == config.my_player_role_change_stars
    await _deliver(client, resp.json()["payload_token"], 890009, "charge-role", resp.json()["stars_amount"])
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["player"]["position"] == "CM"


async def test_lifestyle_xp_bonus_and_weekly_income(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890010)
    await _create(client, headers)
    config = await get_config(db_session)
    villa = LifestyleItem(name="Вилла", category="estate", coins_price=1, prestige=5, effect="xp_bonus_pct", effect_value=50)
    stocks = LifestyleItem(name="Акции", category="stocks", coins_price=1, prestige=5, effect="weekly_income", effect_value=300)
    db_session.add_all([villa, stocks])
    await db_session.flush()
    long_ago = datetime.now(timezone.utc) - timedelta(days=7 * 10 + 2)
    db_session.add_all([
        UserLifestyleItem(user_id=user_id, item_id=villa.id),
        UserLifestyleItem(user_id=user_id, item_id=stocks.id, acquired_at=long_ago),
    ])
    await db_session.commit()

    user = await db_session.get(User, user_id)
    xp_before = user.my_player_xp or 0
    from app.services import wallet_service

    locked = await wallet_service.lock_user_for_update(db_session, user_id)
    await wallet_service.credit_coins(db_session, locked, 10, TransactionType.game_reward, "test")
    await db_session.commit()
    assert locked.my_player_xp - xp_before == config.my_player_xp_per_reward * 3 // 2  # +50%

    catalog = (await client.get(f"{API}/lifestyle", headers=headers)).json()
    max_weeks = 4
    assert catalog["income_ready"] == 300 * max_weeks  # capped
    labels = {e["effect"]: e["label"] for e in catalog["effects"]}
    assert labels["xp_bonus_pct"] == "+50% опыта" and labels["weekly_income"] == "+300 монет в неделю"
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert view["attention"]["income"] and view["xp_bonus_pct"] == 50

    balance = (await db_session.get(User, user_id)).balance
    claimed = await client.post(f"{API}/lifestyle/income/claim", headers=headers)
    assert claimed.status_code == 200, claimed.text
    assert claimed.json()["claimed"] == 1200 and claimed.json()["income_ready"] == 0
    assert claimed.json()["balance"] == balance + 1200
    assert (await client.post(f"{API}/lifestyle/income/claim", headers=headers)).status_code == 409
    tx = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == user_id, CoinTransaction.type == TransactionType.lifestyle_income,
    ))).scalars().all()
    assert len(tx) == 1


async def test_admin_lifestyle_effect_validation(client, db_session, bot_token):
    from tests.test_admin_packs import _admin_auth

    auth = await _admin_auth(client, bot_token)
    base = {"name": "Яхта", "category": "other", "coins_price": 100}
    bad = await client.post(f"{API}/admin/lifestyle", headers=auth, json={**base, "effect": "teleport", "effect_value": 1})
    assert bad.status_code == 409
    ok = await client.post(f"{API}/admin/lifestyle", headers=auth, json={**base, "effect": "weekly_income", "effect_value": 200})
    assert ok.status_code == 200 and ok.json()["effect"] == "weekly_income" and ok.json()["effect_value"] == 200


async def test_player_career_salary_objectives_history_and_fatigue(client, db_session, bot_token):
    user_id, headers = await _login(client, db_session, bot_token, 890011)
    await _create(client, headers, name="Карьерист")
    clubs = (await client.get(f"{API}/player-career", headers=headers)).json()["clubs"]
    club = min((c for c in clubs if not c["locked_reason"]), key=lambda c: (-c["level"], c["rating"]))
    config = await get_config(db_session)
    objective_coins = config.player_career_objective_coins
    level_salary = config.player_career_level_salary[club["level"] - 1]
    assert club["salary"] == round(level_salary * (100 + (club["club_stars"] - 1) * config.player_career_star_salary_pct) / 100 / 10) * 10
    await client.post(f"{API}/player-career/contract", headers=headers, json={"club_key": club["key"]})
    season = (await client.post(f"{API}/player-career/seasons", headers=headers)).json()["season"]
    codes = [o["code"] for o in season["objectives"]]
    assert codes == ["place", "goals", "avg_rating"]
    assert all(o["label"] for o in season["objectives"])

    later = datetime.now(timezone.utc) + timedelta(days=8)
    assert await player_career_service.resolve_due(db_session, season["id"], now=later) == 14
    db_session.expire_all()
    row = await db_session.get(PlayerCareerSeason, season["id"])
    assert row.state["salary"] == club["salary"]
    done = row.state["objectives_done"]
    assert row.state["objective_coins"] == len(done) * objective_coins
    salary_tx = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == user_id, CoinTransaction.description.like("%зарплата%"),
    ))).scalars().all()
    assert len(salary_tx) == 1 and salary_tx[0].amount == row.state["salary"]

    mp = await my_player_service.get_my_player(db_session, user_id)
    assert mp.freshness < 100 and mp.freshness_at is not None  # matches tire him

    view = (await client.get(f"{API}/player-career", headers=headers)).json()
    assert len(view["history"]) == 1
    entry = view["history"][0]
    assert entry["club"] == club["name"] and entry["matches"] == 14 and entry["place"] == row.final_place
    finished = view["season"]
    assert finished["salary"] == row.state["salary"]
    assert sum(1 for o in finished["objectives"] if o["met"]) == len(done)


async def test_share_my_player_card(client, db_session, bot_token):
    _, headers = await _login(client, db_session, bot_token, 890012)
    assert (await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "my_player", "id": 0})).status_code == 404
    await _create(client, headers)
    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "my_player", "id": 0})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert "Виктор Ж." in body["caption"] and body["link"].startswith("https://t.me/")
    data = Path(share_service.SHARE_DIR / body["image_url"].removeprefix("/static/share/")).read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        assert img.format == "JPEG" and img.size == (800, 800)


async def test_trophy_showcase_in_view_and_public(client, db_session, bot_token):
    from app.models.trophy import TrophyDefinition, UserTrophy

    user_id, headers = await _login(client, db_session, bot_token, 890013)
    _, other = await _login(client, db_session, bot_token, 890014)
    await _create(client, headers)
    champion = TrophyDefinition(code="player_career_champion", name="Чемпион лиги", icon="🏆", is_active=True)
    unrelated = TrophyDefinition(code="something_else", name="Другое", is_active=True)
    db_session.add_all([champion, unrelated])
    await db_session.flush()
    db_session.add_all([
        UserTrophy(user_id=user_id, trophy_definition_id=champion.id, message="Сезон за «Юность»"),
        UserTrophy(user_id=user_id, trophy_definition_id=unrelated.id),
    ])
    await db_session.commit()
    view = (await client.get(f"{API}/my-player", headers=headers)).json()
    assert [t["name"] for t in view["trophies"]] == ["Чемпион лиги"]
    public = (await client.get(f"{API}/my-player/users/{user_id}", headers=other)).json()
    assert public["trophies"][0]["message"] == "Сезон за «Юность»"
