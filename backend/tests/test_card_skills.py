"""Card skills: catalog, tokens, assign/upgrade/replace, lifecycle (trades,
sells, upgrades), admin controls, reward sources and match-engine effects.

Concurrency under real row locks is covered separately in
test_card_skills_postgres.py (SQLite ignores SELECT ... FOR UPDATE)."""
import random
import uuid

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.models.admin_action import AdminAction
from app.models.card import UserCard
from app.models.card_skill import CardSkillLedger, UserSkillToken
from app.models.card_upgrade import CardUpgradeRule
from app.models.diamond_upgrade import DiamondUpgradeTier
from app.models.enums import CardSource, Position, Rarity, TaskCategory, TaskConditionType, TransactionType
from app.models.game_config import GameConfig
from app.models.match import Match
from app.models.player import Player
from app.models.task import TaskDefinition, UserTask
from app.models.transaction import CoinTransaction
from app.services import card_skill_effects as fx
from app.services import card_skill_service, match_service, tournament_match_engine
from app.services.card_skill_effects import effect_for_card, skill_choice, skill_roll
from app.services.lineup_service import FORMATION_SLOTS
from app.services.match_situations import ATTACK_SITUATIONS, DEFENSE_SITUATIONS
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


# --- helpers -------------------------------------------------------------------


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post(f"{API}/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id), resp.json()


async def _config(db_session) -> GameConfig:
    config = await db_session.get(GameConfig, 1)
    if config is None:
        config = GameConfig(id=1)
        db_session.add(config)
        await db_session.commit()
        config = await db_session.get(GameConfig, 1)
    return config


_serial = {"n": 1000}


async def _card(db_session, owner_id: int, position: Position = Position.ST, rarity=Rarity.common, player=None, **kw) -> UserCard:
    if player is None:
        player = await create_player(db_session, rarity=rarity, position=position)
    _serial["n"] += 1
    card = UserCard(owner_id=owner_id, player_id=player.id, source=CardSource.seed, serial_number=_serial["n"], **kw)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    return card


async def _grant(db_session, user_id: int, code: str, qty: int):
    from app.services.wallet_service import lock_user_for_update

    user = await lock_user_for_update(db_session, user_id)
    await card_skill_service.grant_tokens(db_session, user, code, qty, "grant_admin", reason="test")
    await db_session.commit()


async def _tokens(db_session, user_id: int) -> dict[str, int]:
    rows = (await db_session.execute(
        select(UserSkillToken).where(UserSkillToken.user_id == user_id).execution_options(populate_existing=True)
    )).scalars().all()
    return {r.skill_code: r.quantity for r in rows}


def _op(operation, *, skill=None, exp_code=None, exp_level=None, tokens, coins, key=None):
    body = {
        "operation": operation, "expected_skill_code": exp_code, "expected_level": exp_level,
        "expected_token_cost": tokens, "expected_coin_cost": coins,
    }
    if skill:
        body["skill_code"] = skill
    if key:
        body["idempotency_key"] = key
    return body


async def _post_op(client, headers, card_id, body):
    return await client.post(f"{API}/card-skills/cards/{card_id}", headers=headers, json=body)


async def _reload(db_session, model, pk):
    # populate_existing instead of expire_all(): expiring would make every
    # other already-loaded test object lazy-refresh outside a greenlet.
    return (await db_session.execute(
        select(model).where(model.id == pk).execution_options(populate_existing=True)
    )).scalar_one_or_none()


# --- catalog ---------------------------------------------------------------------


@pytest.fixture
def unsupported_aerial(monkeypatch):
    """No v1 skill is engine-unsupported any more; the guard is still kept
    (and tested) by marking one skill unsupported for the test."""
    from dataclasses import replace

    from app.services.card_skill_catalog import SKILL_DEFINITIONS

    monkeypatch.setitem(SKILL_DEFINITIONS, "aerial_master", replace(
        SKILL_DEFINITIONS["aerial_master"], engine_supported=False,
        unavailable_reason="нет модели", remaining_work=("сделать модель",),
    ))


async def test_catalog_lists_all_available_skills(client, db_session, bot_token):
    await _register(client, db_session, 820001, bot_token)
    resp = await client.get(f"{API}/card-skills/catalog", headers=telegram_headers(820001, bot_token))
    assert resp.status_code == 200
    body = resp.json()
    codes = [s["code"] for s in body["skills"]]
    assert codes == [
        "sniper", "dribbler", "playmaker", "interceptor", "aerial_master", "reflexes",
        "crosser", "last_line", "one_on_one",
    ]
    by_code = {s["code"]: s for s in body["skills"]}
    assert all(s["is_available"] and s["engine_supported"] for s in body["skills"])
    assert by_code["crosser"]["positions"] == ["LW", "RW", "LM", "RM", "LB", "RB"]
    assert by_code["last_line"]["positions"] == ["CB"]
    assert by_code["one_on_one"]["positions"] == ["GK"]
    assert by_code["aerial_master"]["positions"] == ["CB", "ST"]
    assert by_code["reflexes"]["positions"] == ["GK"]
    assert [lvl["bonus_pp"] for lvl in by_code["sniper"]["levels"]] == [2, 4, 6]
    assert body["rules"]["costs"]["upgrade_to_3"] == {"token_cost": 4, "coin_cost": 1200}


# --- assign / upgrade / replace --------------------------------------------------


async def test_assign_compatible_skill_spends_one_token(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820010, bot_token)
    card = await _card(db_session, user.id, Position.ST)
    await _grant(db_session, user.id, "sniper", 1)
    headers = telegram_headers(820010, bot_token)

    state = (await client.get(f"{API}/card-skills/cards/{card.id}", headers=headers)).json()
    assign = next(a for a in state["actions"] if a["operation"] == "assign" and a["skill_code"] == "sniper")
    assert assign["allowed"] is True and assign["token_cost"] == 1 and assign["coin_cost"] == 0
    reflexes = next(a for a in state["actions"] if a["skill_code"] == "reflexes")
    assert reflexes["allowed"] is False

    resp = await _post_op(client, headers, card.id, _op("assign", skill="sniper", tokens=1, coins=0))
    assert resp.status_code == 200, resp.text
    assert resp.json()["skill_level"] == 1

    refreshed = await _reload(db_session, UserCard, card.id)
    assert (refreshed.skill_code, refreshed.skill_level) == ("sniper", 1)
    assert (await _tokens(db_session, user.id))["sniper"] == 0
    ledger = (await db_session.execute(select(CardSkillLedger).where(CardSkillLedger.kind == "assign"))).scalars().all()
    assert len(ledger) == 1 and ledger[0].user_card_id == card.id and ledger[0].token_delta == -1


async def test_assign_rejects_incompatible_position(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820011, bot_token)
    card = await _card(db_session, user.id, Position.ST)
    await _grant(db_session, user.id, "reflexes", 1)
    resp = await _post_op(
        client, telegram_headers(820011, bot_token), card.id, _op("assign", skill="reflexes", tokens=1, coins=0),
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "incompatible_position"
    assert (await _tokens(db_session, user.id))["reflexes"] == 1


async def test_assign_rejects_someone_elses_card(client, db_session, bot_token):
    owner, _ = await _register(client, db_session, 820012, bot_token)
    other, _ = await _register(client, db_session, 820013, bot_token)
    card = await _card(db_session, owner.id, Position.ST)
    await _grant(db_session, other.id, "sniper", 1)
    resp = await _post_op(
        client, telegram_headers(820013, bot_token), card.id, _op("assign", skill="sniper", tokens=1, coins=0),
    )
    assert resp.status_code == 404
    assert (await _tokens(db_session, other.id))["sniper"] == 1


async def test_assign_without_tokens_is_rejected(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820014, bot_token)
    card = await _card(db_session, user.id, Position.ST)
    resp = await _post_op(client, telegram_headers(820014, bot_token), card.id, _op("assign", skill="sniper", tokens=1, coins=0))
    assert resp.status_code == 400
    assert resp.json()["error"]["details"]["reason"] == "insufficient_tokens"
    assert (await _reload(db_session, UserCard, card.id)).skill_code is None


async def test_upgrade_to_three_then_refuses_above(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820015, bot_token)
    user.balance = 5000
    await db_session.commit()
    card = await _card(db_session, user.id, Position.CM)
    await _grant(db_session, user.id, "playmaker", 1 + 2 + 4)
    headers = telegram_headers(820015, bot_token)

    assert (await _post_op(client, headers, card.id, _op("assign", skill="playmaker", tokens=1, coins=0))).status_code == 200
    resp = await _post_op(client, headers, card.id, _op("upgrade", exp_code="playmaker", exp_level=1, tokens=2, coins=400))
    assert resp.status_code == 200, resp.text
    resp = await _post_op(client, headers, card.id, _op("upgrade", exp_code="playmaker", exp_level=2, tokens=4, coins=1200))
    assert resp.status_code == 200, resp.text
    assert resp.json()["new_balance"] == 5000 - 400 - 1200

    resp = await _post_op(client, headers, card.id, _op("upgrade", exp_code="playmaker", exp_level=3, tokens=4, coins=1200))
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "max_level"
    refreshed = await _reload(db_session, UserCard, card.id)
    assert refreshed.skill_level == 3
    assert (await _tokens(db_session, user.id))["playmaker"] == 0
    txs = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.card_skill_purchase)
    )).scalars().all()
    assert sorted(-t.amount for t in txs) == [400, 1200]


async def test_upgrade_rejected_without_enough_coins(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820016, bot_token)
    user.balance = 100
    await db_session.commit()
    card = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    await _grant(db_session, user.id, "sniper", 2)
    resp = await _post_op(
        client, telegram_headers(820016, bot_token), card.id, _op("upgrade", exp_code="sniper", exp_level=1, tokens=2, coins=400),
    )
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "insufficient_balance"
    assert (await _reload(db_session, UserCard, card.id)).skill_level == 1
    assert (await _tokens(db_session, user.id))["sniper"] == 2


async def test_replace_destroys_old_skill_without_refund(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820017, bot_token)
    user.balance = 1000
    await db_session.commit()
    card = await _card(db_session, user.id, Position.LW, skill_code="sniper", skill_level=2)
    await _grant(db_session, user.id, "dribbler", 1)
    headers = telegram_headers(820017, bot_token)

    resp = await _post_op(client, headers, card.id, _op("replace", skill="dribbler", exp_code="sniper", exp_level=2, tokens=1, coins=300))
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert (body["skill_code"], body["skill_level"]) == ("dribbler", 1)
    assert (body["previous_skill_code"], body["previous_level"]) == ("sniper", 2)
    assert body["new_balance"] == 700
    tokens = await _tokens(db_session, user.id)
    assert tokens["dribbler"] == 0 and tokens.get("sniper", 0) == 0


async def test_idempotent_retry_charges_once(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820018, bot_token)
    user.balance = 1000
    await db_session.commit()
    card = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    await _grant(db_session, user.id, "sniper", 4)
    headers = telegram_headers(820018, bot_token)
    body = _op("upgrade", exp_code="sniper", exp_level=1, tokens=2, coins=400, key=str(uuid.uuid4()))

    first = await _post_op(client, headers, card.id, body)
    second = await _post_op(client, headers, card.id, body)
    assert first.status_code == 200 and second.status_code == 200
    assert second.json()["replayed"] is True
    assert (await _reload(db_session, UserCard, card.id)).skill_level == 2
    assert (await _tokens(db_session, user.id))["sniper"] == 2
    assert (await _reload(db_session, type(user), user.id)).balance == 600

    # Same key reused for a different card is rejected, not replayed.
    other = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    resp = await _post_op(client, headers, other.id, body)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "idempotency_key_reused"


async def test_stale_state_and_changed_price_are_rejected_without_charge(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820019, bot_token)
    user.balance = 1000
    await db_session.commit()
    card = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=2)
    await _grant(db_session, user.id, "sniper", 10)
    headers = telegram_headers(820019, bot_token)

    resp = await _post_op(client, headers, card.id, _op("upgrade", exp_code="sniper", exp_level=1, tokens=2, coins=400))
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "stale_state"

    config = await _config(db_session)
    config.card_skill_upgrade_3_coin_cost = 1500
    await db_session.commit()
    resp = await _post_op(client, headers, card.id, _op("upgrade", exp_code="sniper", exp_level=2, tokens=4, coins=1200))
    assert resp.status_code == 409
    details = resp.json()["error"]["details"]
    assert details["reason"] == "price_changed" and details["coin_cost"] == 1500
    assert (await _reload(db_session, type(user), user.id)).balance == 1000
    assert (await _tokens(db_session, user.id))["sniper"] == 10


async def test_two_copies_of_same_player_are_independent(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820020, bot_token)
    player = await create_player(db_session, position=Position.ST)
    copy_a = await _card(db_session, user.id, player=player)
    copy_b = await _card(db_session, user.id, player=player)
    await _grant(db_session, user.id, "sniper", 1)
    await _grant(db_session, user.id, "dribbler", 1)
    headers = telegram_headers(820020, bot_token)

    assert (await _post_op(client, headers, copy_a.id, _op("assign", skill="sniper", tokens=1, coins=0))).status_code == 200
    assert (await _post_op(client, headers, copy_b.id, _op("assign", skill="dribbler", tokens=1, coins=0))).status_code == 200
    a, b = await _reload(db_session, UserCard, copy_a.id), await _reload(db_session, UserCard, copy_b.id)
    assert (a.skill_code, b.skill_code) == ("sniper", "dribbler")

    state = (await client.get(f"{API}/card-skills/cards/{copy_a.id}", headers=headers)).json()
    assert {c["id"]: c["skill_code"] for c in state["copies"]} == {copy_a.id: "sniper", copy_b.id: "dribbler"}


# --- lifecycle ------------------------------------------------------------------------


async def test_trade_moves_skill_with_the_copy_and_locks_changes_while_pending(client, db_session, bot_token):
    sender, _ = await _register(client, db_session, 820030, bot_token)
    receiver, _ = await _register(client, db_session, 820031, bot_token)
    card = await _card(db_session, sender.id, Position.ST, skill_code="sniper", skill_level=2)
    await _grant(db_session, sender.id, "sniper", 4)
    sender_headers = telegram_headers(820030, bot_token)

    resp = await client.post(
        f"{API}/trades/offers", headers=sender_headers,
        json={"receiver_id": receiver.id, "offered_card_ids": [card.id], "requested_card_ids": []},
    )
    assert resp.status_code == 200, resp.text
    offer = resp.json()
    assert offer["offered_cards"][0]["skill_code"] == "sniper"
    assert offer["offered_cards"][0]["skill_level"] == 2

    # The offered copy (and its skill) can't change after the offer was made.
    resp = await _post_op(client, sender_headers, card.id, _op("upgrade", exp_code="sniper", exp_level=2, tokens=4, coins=1200))
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "card_locked"

    resp = await client.post(f"{API}/trades/offers/{offer['id']}/accept", headers=telegram_headers(820031, bot_token))
    assert resp.status_code == 200, resp.text
    moved = await _reload(db_session, UserCard, card.id)
    assert moved.owner_id == receiver.id
    assert (moved.skill_code, moved.skill_level) == ("sniper", 2)
    # Tokens are never transferred — they stay with the sender.
    assert (await _tokens(db_session, sender.id))["sniper"] == 4


async def test_selling_skilled_copy_needs_confirmation(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820032, bot_token)
    player = await create_player(db_session, position=Position.ST)
    await _card(db_session, user.id, player=player)
    skilled = await _card(db_session, user.id, player=player, skill_code="sniper", skill_level=1)
    headers = telegram_headers(820032, bot_token)

    resp = await client.post(f"{API}/collection/cards/sell", headers=headers, json={"user_card_id": skilled.id})
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["requires_skill_loss_confirmation"] is True
    assert await _reload(db_session, UserCard, skilled.id) is not None

    resp = await client.post(
        f"{API}/collection/cards/sell", headers=headers, json={"user_card_id": skilled.id, "confirm_skill_loss": True},
    )
    assert resp.status_code == 200, resp.text
    assert await _reload(db_session, UserCard, skilled.id) is None


async def test_collection_prefers_plain_copy_as_representative_and_lists_skilled_copies(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820033, bot_token)
    player = await create_player(db_session, position=Position.ST)
    skilled = await _card(db_session, user.id, player=player, skill_code="sniper", skill_level=3)
    plain = await _card(db_session, user.id, player=player)
    extra_plain = await _card(db_session, user.id, player=player)
    resp = await client.get(f"{API}/collection/cards", headers=telegram_headers(820033, bot_token))
    items = resp.json()["items"]
    # Plain duplicates collapse into one tile; the skilled copy is its own
    # tile so pickers (lineup, trade, sell) can choose exactly that copy.
    assert len(items) == 2
    plain_item = next(i for i in items if i["skill_code"] is None)
    skilled_item = next(i for i in items if i["skill_code"] == "sniper")
    assert plain_item["id"] in (plain.id, extra_plain.id)
    assert skilled_item["id"] == skilled.id and skilled_item["skill_level"] == 3
    assert plain_item["duplicate_count"] == 3
    assert plain_item["skilled_copies"] == [
        {"id": skilled.id, "serial_number": skilled.serial_number, "skill_code": "sniper", "skill_level": 3},
    ]


async def test_rarity_upgrade_stake_needs_confirmation_for_skilled_copy(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820034, bot_token)
    card = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    await create_player(db_session, rarity=Rarity.rare)
    db_session.add(CardUpgradeRule(
        from_rarity=Rarity.common, to_rarity=Rarity.rare, success_chance=1.0, coin_cost=10, is_active=True,
        extra_card_bonus=0.0, max_success_chance=1.0,
    ))
    await db_session.commit()
    headers = telegram_headers(820034, bot_token)
    body = {"user_card_ids": [card.id], "to_rarity": "rare"}

    resp = await client.post(f"{API}/collection/upgrade", headers=headers, json=body)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["requires_skill_loss_confirmation"] is True
    assert await _reload(db_session, UserCard, card.id) is not None

    resp = await client.post(f"{API}/collection/upgrade", headers=headers, json={**body, "confirm_skill_loss": True})
    assert resp.status_code == 200, resp.text


async def test_diamond_feed_keeps_skill_on_fed_card_and_guards_skilled_material(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820035, bot_token)
    diamond = await _card(db_session, user.id, Position.ST, rarity=Rarity.diamond, skill_code="sniper", skill_level=2)
    db_session.add(DiamondUpgradeTier(min_rating=0, max_rating=99, common_cost=1, rare_cost=1, epic_cost=1, legendary_cost=1, is_active=True))
    await db_session.commit()
    plain = await _card(db_session, user.id, Position.CB)
    skilled_material = await _card(db_session, user.id, Position.CB, skill_code="interceptor", skill_level=1)
    headers = telegram_headers(820035, bot_token)

    resp = await client.post(
        f"{API}/collection/diamond-upgrade/feed", headers=headers,
        json={"diamond_card_id": diamond.id, "material_card_ids": [plain.id, skilled_material.id]},
    )
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["requires_skill_loss_confirmation"] is True

    resp = await client.post(
        f"{API}/collection/diamond-upgrade/feed", headers=headers,
        json={"diamond_card_id": diamond.id, "material_card_ids": [plain.id]},
    )
    assert resp.status_code == 200, resp.text
    fed = resp.json()["diamond_card"]
    assert fed["diamond_rating_bonus"] == 1
    assert (fed["skill_code"], fed["skill_level"]) == ("sniper", 2)


async def test_upgradeable_card_listing_exposes_skill_so_ui_can_skip_it(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820036, bot_token)
    await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    await _card(db_session, user.id, Position.ST)
    resp = await client.get(f"{API}/collection/upgrade-cards?rarity=common", headers=telegram_headers(820036, bot_token))
    assert sorted((c["skill_code"] or "") for c in resp.json()) == ["", "sniper"]


# --- switches -------------------------------------------------------------------------


async def test_global_switch_off_blocks_operations_and_match_snapshot(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820040, bot_token)
    card = await _card(db_session, user.id, Position.ST)
    await _grant(db_session, user.id, "sniper", 1)
    config = await _config(db_session)
    config.card_skills_enabled = False
    await db_session.commit()

    resp = await _post_op(client, telegram_headers(820040, bot_token), card.id, _op("assign", skill="sniper", tokens=1, coins=0))
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "mechanic_disabled"
    assert effect_for_card("sniper", 3, Position.ST, config) is None
    assert (await _tokens(db_session, user.id))["sniper"] == 1


async def test_disabled_skill_blocks_assign_and_upgrade_but_allows_replacing_away(client, db_session, bot_token):
    admin, session = await _register(client, db_session, 999000001, bot_token)
    admin_headers = {"Authorization": f"Bearer {session['admin_token']}"}
    resp = await client.patch(f"{API}/admin/card-skills/sniper", headers=admin_headers, json={"is_enabled": False})
    assert resp.status_code == 200
    log = (await db_session.execute(select(AdminAction).where(AdminAction.action == "update_card_skill"))).scalars().all()
    assert len(log) == 1

    user, _ = await _register(client, db_session, 820041, bot_token)
    user.balance = 2000
    await db_session.commit()
    fresh = await _card(db_session, user.id, Position.ST)
    owned = await _card(db_session, user.id, Position.ST, skill_code="sniper", skill_level=1)
    await _grant(db_session, user.id, "sniper", 5)
    await _grant(db_session, user.id, "dribbler", 1)
    headers = telegram_headers(820041, bot_token)

    resp = await _post_op(client, headers, fresh.id, _op("assign", skill="sniper", tokens=1, coins=0))
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "skill_unavailable"
    resp = await _post_op(client, headers, owned.id, _op("upgrade", exp_code="sniper", exp_level=1, tokens=2, coins=400))
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "skill_unavailable"
    # Owned skill keeps its match effect while acquisition is closed.
    config = await _config(db_session)
    assert effect_for_card("sniper", 1, Position.ST, config) is not None
    resp = await _post_op(client, headers, owned.id, _op("replace", skill="dribbler", exp_code="sniper", exp_level=1, tokens=1, coins=300))
    assert resp.status_code == 200, resp.text


async def test_admin_cannot_enable_or_grant_unsupported_skill_and_positions_stay_within_catalog(
    client, db_session, bot_token, unsupported_aerial,
):
    admin, session = await _register(client, db_session, 999000001, bot_token)
    admin_headers = {"Authorization": f"Bearer {session['admin_token']}"}
    resp = await client.patch(f"{API}/admin/card-skills/aerial_master", headers=admin_headers, json={"is_enabled": True})
    assert resp.status_code == 409
    resp = await client.post(
        f"{API}/admin/card-skills/tokens/grant", headers=admin_headers,
        json={"user_id": admin.id, "skill_code": "aerial_master", "quantity": 1, "reason": "x"},
    )
    assert resp.status_code == 409
    resp = await client.patch(f"{API}/admin/card-skills/sniper", headers=admin_headers, json={"allowed_positions": ["GK"]})
    assert resp.status_code == 409
    resp = await client.patch(f"{API}/admin/card-skills/sniper", headers=admin_headers, json={"allowed_positions": ["ST"]})
    assert resp.status_code == 200
    sniper = next(s for s in resp.json()["skills"] if s["code"] == "sniper")
    assert sniper["positions"] == ["ST"]


async def test_admin_grant_is_logged_and_idempotent(client, db_session, bot_token):
    admin, session = await _register(client, db_session, 999000001, bot_token)
    admin_headers = {"Authorization": f"Bearer {session['admin_token']}"}
    user, _ = await _register(client, db_session, 820042, bot_token)
    body = {"user_id": user.id, "skill_code": "reflexes", "quantity": 3, "reason": "компенсация", "idempotency_key": "grant-1"}

    for _ in range(2):
        resp = await client.post(f"{API}/admin/card-skills/tokens/grant", headers=admin_headers, json=body)
        assert resp.status_code == 200
    assert {t["skill_code"]: t["quantity"] for t in resp.json()["tokens"]}["reflexes"] == 3
    resp = await client.post(
        f"{API}/admin/card-skills/tokens/grant", headers=admin_headers,
        json={**body, "quantity": -5, "idempotency_key": "grant-2"},
    )
    assert resp.status_code == 409  # can't go below zero

    ledger = (await client.get(f"{API}/admin/card-skills/ledger?user_id={user.id}", headers=admin_headers)).json()
    assert len(ledger) == 1 and ledger[0]["admin_id"] == admin.id and ledger[0]["reason"] == "компенсация"
    actions = (await db_session.execute(select(AdminAction).where(AdminAction.action == "grant_skill_tokens"))).scalars().all()
    assert len(actions) == 1


# --- reward sources -------------------------------------------------------------------


async def test_task_reward_grants_tokens_once(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820050, bot_token)
    definition = TaskDefinition(
        code="skill_task", name="Навыки", description="", category=TaskCategory.regular,
        condition_type=TaskConditionType.metric_counter, metric="packs_opened", target_value=1,
        reward_coins=0, reward_skill_code="interceptor", reward_skill_tokens=2,
    )
    db_session.add(definition)
    await db_session.flush()
    user_task = UserTask(user_id=user.id, task_definition_id=definition.id, progress=1)
    from datetime import datetime, timezone

    user_task.completed_at = datetime.now(timezone.utc)
    db_session.add(user_task)
    await db_session.commit()
    headers = telegram_headers(820050, bot_token)

    resp = await client.post(f"{API}/tasks/{user_task.id}/claim", headers=headers)
    assert resp.status_code == 200, resp.text
    assert resp.json()["granted_skill_tokens"] == {"skill_code": "interceptor", "quantity": 2}
    resp = await client.post(f"{API}/tasks/{user_task.id}/claim", headers=headers)
    assert resp.status_code == 409
    assert (await _tokens(db_session, user.id))["interceptor"] == 2
    kinds = (await db_session.execute(select(CardSkillLedger.kind))).scalars().all()
    assert kinds == ["grant_task"]


async def test_premium_task_cannot_carry_token_reward(client, db_session, bot_token):
    _admin, session = await _register(client, db_session, 999000001, bot_token)
    resp = await client.post(
        f"{API}/admin/tasks", headers={"Authorization": f"Bearer {session['admin_token']}"},
        json={
            "code": "p1", "name": "P", "category": "premium", "condition_type": "metric_counter",
            "metric": "packs_opened", "reward_skill_code": "sniper", "reward_skill_tokens": 1,
        },
    )
    assert resp.status_code == 409


async def test_tournament_place_tokens_are_granted_once(db_session, client, bot_token):
    user, _ = await _register(client, db_session, 820051, bot_token)
    config = await _config(db_session)
    config.ptour_place_skill_tokens = [{"skill_code": "reflexes", "quantity": 2}, None]
    await db_session.commit()
    from app.services.wallet_service import lock_user_for_update

    for _ in range(2):
        locked = await lock_user_for_update(db_session, user.id)
        await card_skill_service.grant_place_tokens(db_session, locked, 77, 1, config)
        await db_session.commit()
    locked = await lock_user_for_update(db_session, user.id)
    await card_skill_service.grant_place_tokens(db_session, locked, 77, 2, config)  # null entry = nothing
    await db_session.commit()
    assert (await _tokens(db_session, user.id))["reflexes"] == 2


# --- effect math ------------------------------------------------------------------------


def _effect(code="sniper", level=3, bonus=6, cap=8, floor=0.02, ceiling=0.95):
    return {"code": code, "level": level, "bonus_pp": bonus, "cap_pp": cap, "floor": floor, "ceiling": ceiling}


def test_skill_roll_without_effect_matches_plain_random(monkeypatch):
    random.seed(7)
    expected = [random.random() < 0.3 for _ in range(50)]
    random.seed(7)
    got = [skill_roll(0.3, [(None, 1, None)])[0] for _ in range(50)]
    assert got == expected


def test_skill_roll_levels_add_percentage_points_and_flag_decisive(monkeypatch):
    # base miss 0.30; r=0.27 misses without skill, sniper III (-6 pp -> 0.24) turns it into a hit.
    monkeypatch.setattr(fx.random, "random", lambda: 0.27)
    missed, notes = skill_roll(0.30, [(_effect(level=3, bonus=6), -1, "Форвард")])
    assert missed is False and notes[0]["decisive"] is True and notes[0]["bonus_pp"] == 6
    # Level I (-2 pp -> 0.28) is not enough for the same draw — still counted, but not decisive.
    missed, notes = skill_roll(0.30, [(_effect(level=1, bonus=2), -1, "Форвард")])
    assert missed is True and notes[0]["decisive"] is False


def test_skill_roll_caps_same_direction_bonus_and_keeps_bounds(monkeypatch):
    monkeypatch.setattr(fx.random, "random", lambda: 0.5)
    # Two +6 pp on the same side are capped at 8 pp in total: 0.40 -> 0.48, not 0.52.
    assert fx._adjusted(0.40, [(_effect(), 1, None), (_effect(), 1, None)]) == pytest.approx(0.48)
    # Ceiling 0.95 bounds a skill push, floor 0.02 bounds a skill pull ...
    assert fx._adjusted(0.93, [(_effect(), 1, None)]) == pytest.approx(0.95)
    assert fx._adjusted(0.05, [(_effect(), -1, None)]) == pytest.approx(0.02)
    # ... but a base already outside the bounds (from existing curves) is never clipped.
    assert fx._adjusted(0.97, [(_effect(), -1, None)]) == pytest.approx(0.91)
    assert fx._adjusted(0.97, [(_effect(), 1, None)]) == pytest.approx(0.97)
    # Opposing skills net out (playmaker -4 vs interceptor +6 on one pass roll).
    assert fx._adjusted(0.20, [(_effect(bonus=4), -1, None), (_effect(bonus=6), 1, None)]) == pytest.approx(0.22)


def test_skill_choice_without_effect_matches_random_choices():
    random.seed(11)
    expected = [random.choices(["b", "s", "a"], weights=[0.3, 0.45, 0.25], k=1)[0] for _ in range(50)]
    random.seed(11)
    got = [skill_choice(["b", "s", "a"], [0.3, 0.45, 0.25], "a", None)[0] for _ in range(50)]
    assert got == expected


def test_skill_choice_dribbler_moves_share_to_advance(monkeypatch):
    # weights breakdown .30 / stall .45 / advance .25 ; r=0.73 lands in stall
    # (cum .30, .75) without the skill; +6 pp advance -> cum .2760, .69 -> advance.
    monkeypatch.setattr(fx.random, "random", lambda: 0.73)
    pick, notes = skill_choice(["breakdown", "stall", "advance"], [0.30, 0.45, 0.25], "advance", _effect("dribbler"))
    assert pick == "advance" and notes[0]["decisive"] is True


async def test_effect_requires_compatible_position_and_uses_config_levels(db_session):
    config = await _config(db_session)
    config.card_skill_level_2_bonus_pp = 5
    assert effect_for_card("sniper", 2, Position.ST, config)["bonus_pp"] == 5
    assert effect_for_card("sniper", 2, Position.GK, config) is None  # e.g. position edited by admin
    assert effect_for_card("aerial_master", 3, Position.CB, config)["bonus_pp"] == 6
    assert effect_for_card("aerial_master", 3, Position.LB, config) is None
    config.card_skill_event_bonus_cap_pp = 3
    assert effect_for_card("reflexes", 3, Position.GK, config)["bonus_pp"] == 3


# --- Card Arena integration ---------------------------------------------------------------


def _attack_moment(shooter_id=1, target_id=2):
    situation = next(s for s in ATTACK_SITUATIONS if s.shot_type == "in_box")
    return {
        "minute": 10, "situation_id": situation.id, "shot_type": "in_box",
        "actors": {
            "shooter": {"user_card_id": shooter_id, "player_id": 1, "name": "Стрелок", "rating": 70, "position": "ST"},
            "pass_target": {"user_card_id": target_id, "player_id": 2, "name": "Партнёр", "rating": 70, "position": "ST"},
        },
    }, situation


async def test_arena_sniper_changes_only_the_shooters_miss_roll(db_session, monkeypatch):
    config = await _config(db_session)
    moment, situation = _attack_moment()
    eff_rating = match_service._clamp_rating(70 + situation.bias)
    base_miss = match_service._lerp_chance(
        eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max),
    )
    snapshot = {"cards": {"1": {**_effect(), "player": "Стрелок"}}, "user_gk": None, "opponent_gk": None}
    draws = iter([base_miss - 0.01, 0.999])  # miss roll just under base; then the save roll fails
    monkeypatch.setattr(match_service.random, "random", lambda: next(draws))
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))

    state = {"ratings": {"opponent_def": 70, "opponent_gk": 70}, "cards": {}, "red_card_applied": False, "skills": snapshot}
    event, scored = match_service._resolve_attack(moment, "shoot", state, config, "Соперник")
    assert scored == "user"
    assert event["payload"]["skills"][0]["code"] == "sniper"
    assert event["payload"]["skills"][0]["decisive"] is True


async def test_arena_unrelated_skill_and_old_matches_have_no_effect(db_session, monkeypatch):
    config = await _config(db_session)
    moment, _ = _attack_moment()
    monkeypatch.setattr(match_service.random, "random", lambda: 0.99)
    monkeypatch.setattr(fx.random, "random", lambda: 0.99)
    # A dribbler on the shooter does nothing for a shot (Card Arena has no take-on roll).
    state = {
        "ratings": {"opponent_def": 70, "opponent_gk": 70}, "cards": {}, "red_card_applied": False,
        "skills": {"cards": {"1": _effect("dribbler")}, "user_gk": None, "opponent_gk": None},
    }
    event, _ = match_service._resolve_attack(moment, "shoot", state, config, "Соперник")
    assert "skills" not in event["payload"]
    # A match saved before skills existed has no "skills" key at all.
    old_state = {"ratings": {"opponent_def": 70, "opponent_gk": 70}, "cards": {}, "red_card_applied": False}
    event, _ = match_service._resolve_attack(moment, "pass", old_state, config, "Соперник")
    assert "skills" not in event["payload"]


async def test_arena_reflexes_on_user_keeper_raise_save_roll(db_session, monkeypatch):
    config = await _config(db_session)
    situation = next(s for s in DEFENSE_SITUATIONS if s.shot_type == "in_box")
    moment = {
        "minute": 30, "situation_id": situation.id, "shot_type": "in_box",
        "actors": {"defender": {"user_card_id": 5, "player_id": 5, "name": "Защитник", "rating": 70, "position": "CB"}},
    }
    save_p = match_service._lerp_chance_positive(70, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
    draws = iter([0.99, save_p + 0.03])  # shot on target; save roll just above base save chance
    monkeypatch.setattr(match_service.random, "random", lambda: next(draws))
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    state = {
        "ratings": {"user_gk": 70, "user_def": 70, "opponent_fwd": 70}, "cards": {}, "red_card_applied": False,
        "skills": {"cards": {}, "user_gk": {**_effect("reflexes"), "player": "Вратарь"}, "opponent_gk": None},
    }
    event, scored = match_service._resolve_defense(moment, "keeper", state, config, "Соперник")
    assert event["event_type"] == "save" and scored is None
    assert event["payload"]["skills"][0]["code"] == "reflexes"


async def _full_lineup(client, db_session, user_id, headers, sniper_on_st=True):
    slots = []
    for slot in FORMATION_SLOTS:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        kw = {"skill_code": "sniper", "skill_level": 2} if sniper_on_st and slot.ideal_position == Position.ST else {}
        card = await _card(db_session, user_id, player=player, **kw)
        slots.append({"slot_code": slot.code, "user_card_id": card.id})
    resp = await client.put(f"{API}/lineups/active", headers=headers, json={"slots": slots})
    assert resp.status_code == 200, resp.text
    return slots


async def test_arena_snapshot_is_frozen_at_match_start(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820060, bot_token)
    headers = telegram_headers(820060, bot_token)
    await _full_lineup(client, db_session, user.id, headers)
    resp = await client.post(f"{API}/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200, resp.text
    match_id = resp.json()["id"]

    match = await _reload(db_session, Match, match_id)
    snapshot = match.server_state["skills"]
    (card_id, effect), = snapshot["cards"].items()
    assert effect["code"] == "sniper" and effect["bonus_pp"] == 4

    # Later config/card changes must not reach the started match.
    config = await _config(db_session)
    config.card_skill_level_2_bonus_pp = 10
    card = await db_session.get(UserCard, int(card_id))
    card.skill_code, card.skill_level = None, None
    await db_session.commit()
    match = await _reload(db_session, Match, match_id)
    assert match.server_state["skills"]["cards"][card_id]["bonus_pp"] == 4


async def test_arena_snapshot_is_empty_when_mechanic_disabled(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820061, bot_token)
    headers = telegram_headers(820061, bot_token)
    await _full_lineup(client, db_session, user.id, headers)
    config = await _config(db_session)
    config.card_skills_enabled = False
    await db_session.commit()
    resp = await client.post(f"{API}/matches/play", headers=headers, json={"difficulty": "medium"})
    assert resp.status_code == 200
    match = await _reload(db_session, Match, resp.json()["id"])
    assert match.server_state["skills"] is None


# --- tournament engine integration ---------------------------------------------------------


class _Cfg:
    match_attack_shoot_miss_chance_min = 0.08
    match_attack_shoot_miss_chance_max = 0.32
    match_pass_fail_chance_min = 0.05
    match_pass_fail_chance_max = 0.28
    match_receiver_shot_miss_chance_min = 0.05
    match_receiver_shot_miss_chance_max = 0.22
    match_defender_block_chance_min = 0.10
    match_defender_block_chance_max = 0.35
    match_keeper_save_chance_min = 0.35
    match_keeper_save_chance_max = 0.75


def _actor(name, rating=70, skill=None):
    actor = {"club_card_id": 1, "player_id": 1, "name": name, "rating": rating, "position": "ST"}
    if skill:
        actor["skill"] = skill
    return actor


def test_tournament_pass_roll_combines_playmaker_and_interceptor(monkeypatch):
    base_fail = tournament_match_engine._lerp_chance(
        tournament_match_engine._clamp_rating(70 + 6), _Cfg.match_pass_fail_chance_min, _Cfg.match_pass_fail_chance_max,
    )
    moment = {
        "minute": 5, "shot_type": "in_box", "is_box": True,
        "actors": {
            "shooter": _actor("Диспетчер", skill=_effect("playmaker", bonus=4)),
            "pass_target": _actor("Нападающий"),
            "defender": _actor("Перехватчик", skill=_effect("interceptor", bonus=6)),
        },
    }
    # Net +2 pp to the fail chance: a draw 1 pp above the base fail chance now fails.
    monkeypatch.setattr(fx.random, "random", lambda: base_fail + 0.01)
    event, scorer = tournament_match_engine._resolve_shot_action("a", moment, _Cfg(), quality_bias=-6)
    assert event["event_type"] == "pass_failed" and scorer == "none"
    notes = {n["code"]: n for n in event["payload"]["skills"]}
    assert notes["interceptor"]["decisive"] is True and notes["playmaker"]["decisive"] is False


def test_tournament_reflexes_comes_from_defending_goalkeeper(monkeypatch):
    moment = {
        "minute": 5, "shot_type": "in_box", "is_box": True,
        "actors": {"shooter": _actor("Ф"), "pass_target": _actor("П"), "defender": _actor("З", rating=70)},
    }
    save_p = tournament_match_engine._lerp_chance_positive(70, _Cfg.match_keeper_save_chance_min, _Cfg.match_keeper_save_chance_max)
    draws = iter([0.99, save_p + 0.05])
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    monkeypatch.setattr(tournament_match_engine.random, "random", lambda: next(draws))
    keeper = {"category": "GK", "name": "Вратарь", "skill": _effect("reflexes")}
    event, _ = tournament_match_engine._resolve_shot_action("a", moment, _Cfg(), keeper=keeper)
    assert event["event_type"] == "save"
    assert event["payload"]["skills"][0]["player"] == "Вратарь"


def test_tournament_dribbler_applies_to_stage1_duelist_only(monkeypatch):
    from types import SimpleNamespace

    from app.services import club_tactical_matchup_service as svc

    duelist = SimpleNamespace(id=1, player=SimpleNamespace(display_name="Дриблёр"), skill=_effect("dribbler"))
    plain = SimpleNamespace(id=2, player=SimpleNamespace(display_name="Обычный"))
    monkeypatch.setattr(fx.random, "random", lambda: 0.73)
    monkeypatch.setattr(svc.random, "random", lambda: 0.73)
    notes: list = []
    # ratio 0.5 -> band (0.30, 0.45, 0.25)
    assert svc._resolve_stage1_for(0.5, duelist, notes) == "advance"
    assert notes and notes[0]["code"] == "dribbler"
    assert svc._resolve_stage1_for(0.5, plain, []) == "stall"


async def test_player_tournament_adapter_keeps_rating_and_strength_with_coach_and_stadium(db_session):
    """Skills never change ratings or team strength, so coaches/stadiums (which
    act on ratings/profile) and skills cannot double-apply."""
    from types import SimpleNamespace

    from app.models.coach import Coach
    from app.services.club_tactical_matchup_service import build_side
    from app.services.club_formation_service import get_formation_slots
    from app.services.player_tournament_simulation_service import _engine_card

    config = await _config(db_session)
    slots = get_formation_slots("4-3-3")
    plain_pairs, skilled_pairs = [], []
    for slot in slots:
        player = await create_player(db_session, rating=80, position=slot.ideal_position)
        card = SimpleNamespace(
            id=player.id, player_id=player.id, player=player, diamond_rating_bonus=0, skill_code=None, skill_level=None,
        )
        plain_pairs.append((_engine_card(card, config), slot))
        card.skill_code = "sniper" if slot.ideal_position == Position.ST else ("reflexes" if slot.ideal_position == Position.GK else None)
        card.skill_level = 3 if card.skill_code else None
        skilled_pairs.append((_engine_card(card, config), slot))

    coach = Coach(display_name="Тренер", rarity=Rarity.epic)
    coach.boosts = []
    side_plain = build_side(plain_pairs, "BALANCED", "CENTRAL_PLAY", coach=coach, stadium_multiplier=1.05)
    side_skilled = build_side(skilled_pairs, "BALANCED", "CENTRAL_PLAY", coach=coach, stadium_multiplier=1.05)
    assert side_plain.profile == side_skilled.profile
    assert [c.player.rating for c in side_plain.cards] == [c.player.rating for c in side_skilled.cards]
    skilled_codes = {c.skill["code"] for c in side_skilled.cards if c.skill}
    assert skilled_codes == {"sniper", "reflexes"}


# --- player tournament end-to-end ----------------------------------------------------------


async def test_player_tournament_match_snapshots_and_applies_squad_skills(client, db_session, bot_token):
    from app.services import player_tournament_simulation_service as sim
    from tests.player_tournament_helpers import make_ready_user

    user_a = await make_ready_user(client, db_session, bot_token, 820070)
    user_b = await make_ready_user(client, db_session, bot_token, 820071)
    cards_a = (await db_session.execute(
        select(UserCard).where(UserCard.owner_id == user_a.id).execution_options(populate_existing=True)
    )).scalars().all()
    by_position = {}
    for card in cards_a:
        player = await db_session.get(Player, card.player_id)
        by_position.setdefault(player.position, card)
    by_position[Position.ST].skill_code, by_position[Position.ST].skill_level = "sniper", 3
    by_position[Position.GK].skill_code, by_position[Position.GK].skill_level = "reflexes", 2
    await db_session.commit()
    config = await _config(db_session)

    random.seed(3)
    score_a, score_b, events, snapshot = await sim._play_match(
        db_session, user_a.id, user_b.id, {user_a.id: "A", user_b.id: "B"}, config,
    )
    assert snapshot["b"] == {}
    assert {e["code"] for e in snapshot["a"].values()} == {"sniper", "reflexes"}
    assert {e["bonus_pp"] for e in snapshot["a"].values()} == {6, 4}
    # Every note in the log belongs to one of side A's two skilled cards.
    noted = [n for e in events for n in (e.get("payload") or {}).get("skills", [])]
    assert all(n["code"] in ("sniper", "reflexes") for n in noted)

    # Mechanic off -> the same squads produce no snapshot and no notes.
    config.card_skills_enabled = False
    await db_session.commit()
    _sa, _sb, events_off, snapshot_off = await sim._play_match(
        db_session, user_a.id, user_b.id, {user_a.id: "A", user_b.id: "B"}, config,
    )
    assert snapshot_off is None
    assert not any((e.get("payload") or {}).get("skills") for e in events_off)


# --- skill tokens from packs (same per-slot mechanism as stadiums) --------------------------


async def _token_pack(db_session, chance: float, card_count: int = 3):
    from tests.factories import create_pack

    await create_player(db_session, rarity=Rarity.common)
    return await create_pack(
        db_session, f"skills-{uuid.uuid4().hex[:6]}", price=10, card_count=card_count,
        probabilities={Rarity.common: 1.0}, skill_token_drop_chance=chance,
    )


async def _set_drop(db_session, code: str, weight: int, quantity: int = 1, enabled: bool = True):
    rows = await card_skill_service.ensure_catalog(db_session)
    for row in rows.values():
        if row.code == code:
            row.pack_drop_weight, row.pack_drop_quantity, row.is_enabled = weight, quantity, enabled
        elif code != "*":
            row.pack_drop_weight = 0
    await db_session.commit()


async def test_skill_pack_rolls_tokens_and_replays_without_double_grant(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820080, bot_token)
    pack = await _token_pack(db_session, chance=1.0)
    await _set_drop(db_session, "reflexes", weight=5, quantity=2)
    headers = telegram_headers(820080, bot_token)

    body = {"idempotency_key": "skill-pack-1"}
    first = await client.post(f"{API}/packs/{pack.id}/open", headers=headers, json=body)
    assert first.status_code == 200, first.text
    result = first.json()
    assert result["cards"] == [] and result["skill_tokens"] == [{"skill_code": "reflexes", "quantity": 2}] * 3
    assert (await _tokens(db_session, user.id))["reflexes"] == 6

    replay = await client.post(f"{API}/packs/{pack.id}/open", headers=headers, json=body)
    assert replay.status_code == 200
    assert replay.json()["skill_tokens"] == result["skill_tokens"]
    assert (await _tokens(db_session, user.id))["reflexes"] == 6
    kinds = (await db_session.execute(select(CardSkillLedger.kind))).scalars().all()
    assert kinds == ["grant_pack"] * 3


async def test_pack_without_token_chance_or_droppable_skills_keeps_giving_players(client, db_session, bot_token):
    user, _ = await _register(client, db_session, 820081, bot_token)
    headers = telegram_headers(820081, bot_token)
    plain = await _token_pack(db_session, chance=0.0)
    resp = await client.post(f"{API}/packs/{plain.id}/open", headers=headers, json={"idempotency_key": "p-1"})
    assert len(resp.json()["cards"]) == 3 and resp.json()["skill_tokens"] == []

    # Chance set, but every skill is either weight 0 or closed by the admin.
    tokened = await _token_pack(db_session, chance=1.0)
    await _set_drop(db_session, "sniper", weight=3, enabled=False)
    resp = await client.post(f"{API}/packs/{tokened.id}/open", headers=headers, json={"idempotency_key": "p-2"})
    assert len(resp.json()["cards"]) == 3 and resp.json()["skill_tokens"] == []
    assert await _tokens(db_session, user.id) == {}


async def test_partial_token_chance_splits_slots(client, db_session, bot_token, monkeypatch):
    from app.services import pack_service

    await _register(client, db_session, 820082, bot_token)
    pack = await _token_pack(db_session, chance=0.5, card_count=2)
    await _set_drop(db_session, "sniper", weight=1)
    draws = iter([0.2, 0.9])  # slot 1 < 0.5 -> tokens, slot 2 -> player
    monkeypatch.setattr(pack_service.random, "random", lambda: next(draws))
    resp = await client.post(
        f"{API}/packs/{pack.id}/open", headers=telegram_headers(820082, bot_token), json={"idempotency_key": "s-1"},
    )
    body = resp.json()
    assert len(body["cards"]) == 1 and body["skill_tokens"] == [{"skill_code": "sniper", "quantity": 1}]


async def test_admin_edits_pack_drop_table_within_rules(client, db_session, bot_token):
    _admin, session = await _register(client, db_session, 999000001, bot_token)
    headers = {"Authorization": f"Bearer {session['admin_token']}"}
    resp = await client.patch(
        f"{API}/admin/card-skills/sniper", headers=headers, json={"pack_drop_weight": 7, "pack_drop_quantity": 3},
    )
    assert resp.status_code == 200
    sniper = next(s for s in resp.json()["skills"] if s["code"] == "sniper")
    assert (sniper["pack_drop_weight"], sniper["pack_drop_quantity"]) == (7, 3)
    resp = await client.patch(f"{API}/admin/card-skills/aerial_master", headers=headers, json={"pack_drop_weight": 2})
    assert resp.status_code == 200


async def test_unsupported_skill_is_shown_closed_with_remaining_work(client, db_session, bot_token, unsupported_aerial):
    await _register(client, db_session, 820002, bot_token)
    resp = await client.get(f"{API}/card-skills/catalog", headers=telegram_headers(820002, bot_token))
    aerial = next(s for s in resp.json()["skills"] if s["code"] == "aerial_master")
    assert aerial["is_available"] is False and aerial["engine_supported"] is False
    assert aerial["unavailable_reason"] == "нет модели" and aerial["remaining_work"] == ["сделать модель"]


async def test_unsupported_skill_never_drops_from_packs(db_session, unsupported_aerial):
    await card_skill_service.ensure_catalog(db_session)
    table = await card_skill_service.pack_token_drop_table(db_session)
    assert "aerial_master" not in {code for code, _w, _q in table}


# --- aerial_master ------------------------------------------------------------------------


def test_aerial_split_preserves_the_original_miss_probability():
    # Without skills, P(duel lost) + P(duel won) * P(header miss) == the old miss chance.
    for miss in (0.05, 0.18, 0.32):
        for alpha in (0.25, 0.5, 0.75):
            d = alpha * miss
            m2 = miss * (1 - alpha) / (1 - d)
            assert d + (1 - d) * m2 == pytest.approx(miss)
    random.seed(5)
    trials = 40000
    misses = sum(fx.aerial_shot_roll(0.2, 0.5, [], [])[0] for _ in range(trials))
    assert misses / trials == pytest.approx(0.2, abs=0.01)


def test_aerial_alpha_leans_on_ratings_and_is_bounded():
    assert fx.aerial_alpha(80, 80) == pytest.approx(0.5)
    assert fx.aerial_alpha(60, 99) == fx.AERIAL_ALPHA_MAX
    assert fx.aerial_alpha(99, 60) == fx.AERIAL_ALPHA_MIN


def test_aerial_defender_skill_wins_the_duel_and_is_marked_decisive(monkeypatch):
    # miss .2, alpha .5 -> base defender-wins-duel .10; CB aerial III (+6) -> .16
    draws = iter([0.13, 0.99])
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    missed, lost, notes = fx.aerial_shot_roll(0.2, 0.5, [(_effect("aerial_master"), 1, "ЦЗ")], [])
    assert missed and lost
    assert notes[0]["code"] == "aerial_master" and notes[0]["decisive"] is True


def test_aerial_attacker_skill_only_affects_the_duel_not_the_header(monkeypatch):
    # The target's aerial III lowers the duel loss .10 -> .04; the header's own
    # miss chance is untouched — no extra bonus on the shot after the duel.
    draws = iter([0.07, 0.0])
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    missed, lost, notes = fx.aerial_shot_roll(0.2, 0.5, [(_effect("aerial_master"), -1, "ЦФ")], [])
    assert not lost and missed  # won the duel, then missed the header anyway
    assert notes[0]["decisive"] is False


def _cross_moment(defender_skill=None, target_skill=None):
    shooter = {"club_card_id": 1, "player_id": 1, "name": "Вингер", "rating": 70, "position": "LW"}
    moment = {
        "minute": 10, "shot_type": "in_box", "is_box": True, "is_cross": True,
        "actors": {"shooter": shooter, "pass_target": _actor("П"), "defender": _actor("З")},
    }
    aerial = {
        "attack_target": {**_actor("Форвард", skill=target_skill), "position": "ST", "category": "FWD"},
        "defender": {**_actor("Центрбек", skill=defender_skill), "position": "CB", "category": "DEF"},
    }
    return moment, aerial


def test_tournament_cross_uses_aerial_duel_only_when_a_duelist_has_the_skill(monkeypatch):
    monkeypatch.setattr(fx.random, "random", lambda: 0.999)
    monkeypatch.setattr(tournament_match_engine.random, "random", lambda: 0.999)
    moment, aerial = _cross_moment(defender_skill=_effect("aerial_master"))
    event, _ = tournament_match_engine._resolve_shot_action("a", moment, _Cfg(), keeper=None, aerial=aerial)
    assert event["payload"]["aerial_duel"] == {"target": "Форвард", "defender": "Центрбек", "won_by": "attacker"}
    assert event["payload"]["skills"][0]["code"] == "aerial_master"

    moment, aerial = _cross_moment()  # nobody has the skill -> the old single roll, no duel in the log
    event, _ = tournament_match_engine._resolve_shot_action("a", moment, _Cfg(), keeper=None, aerial=aerial)
    assert "aerial_duel" not in event["payload"] and "skills" not in event["payload"]


def test_tournament_aerial_pick_prefers_the_skilled_player():
    lineup = [
        {"position": "CB", "name": "CB1"}, {"position": "CB", "name": "CB2", "skill": _effect("aerial_master")},
        {"position": "ST", "name": "ST1"},
    ]
    assert tournament_match_engine._aerial_pick(lineup, "CB")["name"] == "CB2"
    assert tournament_match_engine._aerial_pick(lineup, "ST")["name"] == "ST1"
    assert tournament_match_engine._aerial_pick([], "CB") is None


async def test_arena_aerial_block_only_in_aerial_situations(db_session, monkeypatch):
    config = await _config(db_session)
    defender = {"user_card_id": 7, "player_id": 7, "name": "Центрбек", "rating": 70, "position": "CB"}
    state = {
        "ratings": {"user_gk": 70, "user_def": 70, "opponent_fwd": 70}, "cards": {}, "red_card_applied": False,
        "skills": {"cards": {"7": {**_effect("aerial_master"), "player": "Центрбек"}}, "user_gk": None, "opponent_gk": None},
    }
    fail_p = match_service._lerp_chance(70, float(config.match_block_fail_chance_min), float(config.match_block_fail_chance_max))
    # One shared random module: a draw just under the base fail chance fails
    # without the skill and succeeds with aerial III (-6 p.p.).
    monkeypatch.setattr(fx.random, "random", lambda: fail_p - 0.01)

    aerial_moment = {"minute": 5, "situation_id": "def_box_corner_scramble", "shot_type": "in_box", "actors": {"defender": defender}}
    event, _ = match_service._resolve_defense(aerial_moment, "block", state, config, "Соперник")
    assert event["event_type"] == "blocked"
    assert event["payload"]["skills"][0]["code"] == "aerial_master" and event["payload"]["skills"][0]["decisive"]

    plain_moment = {"minute": 6, "situation_id": "def_box_one_on_one", "shot_type": "in_box", "actors": {"defender": defender}}
    event, _ = match_service._resolve_defense(plain_moment, "block", state, config, "Соперник")
    assert "skills" not in event["payload"]


# --- crosser / last_line / one_on_one -----------------------------------------------------


def test_skill_choice_sets_matches_random_choices_without_effects():
    random.seed(13)
    expected = [random.choices(["L", "N", "H", "V"], weights=[0.25, 0.5, 0.22, 0.03], k=1)[0] for _ in range(60)]
    random.seed(13)
    got = [fx.skill_choice_sets(["L", "N", "H", "V"], [0.25, 0.5, 0.22, 0.03], [(None, {"H", "V"}, None)])[0] for _ in range(60)]
    assert got == expected


def test_skill_choice_sets_raises_the_favored_group_share(monkeypatch):
    # L .25 N .50 | H .22 V .03 ; r=0.73 lands in N (cum .75). +6 p.p. to {H, V}:
    # group .25 -> .31, others scaled by .69/.75 -> cum N .69 -> r=.73 lands in H.
    monkeypatch.setattr(fx.random, "random", lambda: 0.73)
    pick, notes = fx.skill_choice_sets(
        ["LOW", "NORMAL", "HIGH", "VERY_HIGH"], [0.25, 0.50, 0.22, 0.03], [(_effect("crosser"), {"HIGH", "VERY_HIGH"}, "Вингер")],
    )
    assert pick == "HIGH" and notes[0]["decisive"] is True


def _duelist(name, position, skill=None):
    from types import SimpleNamespace

    return SimpleNamespace(id=hash(name) % 1000, player=SimpleNamespace(display_name=name, position=position), skill=skill)


def test_crosser_only_counts_on_flank_attacks(monkeypatch):
    from app.services import club_tactical_matchup_service as svc

    monkeypatch.setattr(fx.random, "random", lambda: 0.73)
    winger = _duelist("Вингер", Position.LW, _effect("crosser"))
    other = _duelist("Партнёр", Position.LM)
    notes: list = []
    flank = svc._resolve_quality_for(0.5, "wing_attack", [winger, other], notes)
    # band for 0.5: LOW .25 NORMAL .50 HIGH .22 VERY_HIGH .03
    assert flank == "HIGH" and notes and notes[0]["code"] == "crosser"
    # Central attack: exactly the old resolve_quality path, no notes.
    monkeypatch.setattr(svc, "resolve_quality", lambda advantage: "UNCHANGED")
    central_notes: list = []
    assert svc._resolve_quality_for(0.5, "central_attack", [winger, other], central_notes) == "UNCHANGED"
    assert central_notes == []


def test_last_line_defends_the_counter_attack_duel(monkeypatch):
    from app.services import club_tactical_matchup_service as svc

    # ratio .5 -> breakdown .30 stall .45 advance .25 ; r=0.76 -> advance without skills.
    monkeypatch.setattr(fx.random, "random", lambda: 0.76)
    attacker = _duelist("Форвард", Position.ST)
    cb = _duelist("Центрбек", Position.CB, _effect("last_line"))
    notes: list = []
    assert svc._resolve_stage1_for(0.5, attacker, notes, defender=cb) == "stall"
    assert notes[0]["code"] == "last_line" and notes[0]["decisive"] is True
    # Not passed as defender (normal positional attack) -> the old resolve_stage1 path.
    monkeypatch.setattr(svc, "resolve_stage1", lambda ratio: "UNCHANGED")
    assert svc._resolve_stage1_for(0.5, attacker, [], defender=None) == "UNCHANGED"


def test_tournament_one_on_one_only_on_top_quality_chances(monkeypatch):
    save_p = tournament_match_engine._lerp_chance_positive(70, _Cfg.match_keeper_save_chance_min, _Cfg.match_keeper_save_chance_max)
    draws = iter([0.99, save_p + 0.03, 0.99, save_p + 0.03])
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    keeper = {"category": "GK", "name": "Вратарь", "skill": _effect("one_on_one")}
    base = {"minute": 5, "shot_type": "in_box", "is_box": True,
            "actors": {"shooter": _actor("Ф"), "pass_target": _actor("П"), "defender": _actor("З", rating=70)}}
    event, _ = tournament_match_engine._resolve_shot_action("a", {**base, "is_one_on_one": True}, _Cfg(), keeper=keeper)
    assert event["event_type"] == "save" and event["payload"]["skills"][0]["code"] == "one_on_one"
    event, _ = tournament_match_engine._resolve_shot_action("a", {**base, "is_one_on_one": False}, _Cfg(), keeper=keeper)
    assert event["event_type"] == "goal" and "skills" not in event["payload"]


async def test_arena_new_skills_apply_only_in_their_situations(db_session, monkeypatch):
    config = await _config(db_session)
    cb = {"user_card_id": 7, "player_id": 7, "name": "Центрбек", "rating": 70, "position": "CB"}
    state = {
        "ratings": {"user_gk": 70, "user_def": 70, "opponent_fwd": 70, "opponent_def": 70, "opponent_gk": 70},
        "cards": {}, "red_card_applied": False,
        "skills": {
            "cards": {"7": {**_effect("last_line"), "player": "Центрбек"}, "8": {**_effect("crosser"), "player": "Вингер"}},
            "user_gk": {**_effect("one_on_one"), "player": "Вратарь"},
            "opponent_gk": None,
        },
    }
    foul_p = match_service._lerp_chance(70, float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max))
    monkeypatch.setattr(fx.random, "random", lambda: foul_p - 0.01)
    breakaway = {"minute": 5, "situation_id": "def_counter_attack", "shot_type": "long_range", "actors": {"defender": cb}}
    event, _ = match_service._resolve_defense(breakaway, "tackle", state, config, "Соперник")
    assert event["event_type"] == "tackle_won" and event["payload"]["skills"][0]["code"] == "last_line"
    positional = {"minute": 6, "situation_id": "def_long_range_rebound", "shot_type": "long_range", "actors": {"defender": cb}}
    event, _ = match_service._resolve_defense(positional, "tackle", state, config, "Соперник")
    assert "skills" not in event["payload"]

    # one_on_one: the user's keeper on "keeper" in the one-on-one situation only.
    save_p = match_service._lerp_chance_positive(70, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
    draws = iter([0.99, save_p + 0.03])
    monkeypatch.setattr(fx.random, "random", lambda: next(draws))
    one_on_one = {"minute": 7, "situation_id": "def_box_one_on_one", "shot_type": "in_box", "actors": {"defender": cb}}
    event, _ = match_service._resolve_defense(one_on_one, "keeper", state, config, "Соперник")
    assert event["event_type"] == "save" and event["payload"]["skills"][0]["code"] == "one_on_one"

    # crosser: the winger's "Pass" in a flank situation.
    winger = {"user_card_id": 8, "player_id": 8, "name": "Вингер", "rating": 70, "position": "LW"}
    target = {"user_card_id": 9, "player_id": 9, "name": "Форвард", "rating": 70, "position": "ST"}
    situation = next(s for s in ATTACK_SITUATIONS if s.id == "att_box_cutback")
    pass_fail = match_service._lerp_chance(
        match_service._clamp_rating(70 - situation.bias), float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max),
    )
    monkeypatch.setattr(fx.random, "random", lambda: pass_fail - 0.01)
    flank = {"minute": 8, "situation_id": "att_box_cutback", "shot_type": "in_box", "actors": {"shooter": winger, "pass_target": target}}
    event, _ = match_service._resolve_attack(flank, "pass", state, config, "Соперник")
    assert event["event_type"] != "pass_failed"
    assert event["payload"]["skills"][0]["code"] == "crosser" and event["payload"]["skills"][0]["decisive"]
