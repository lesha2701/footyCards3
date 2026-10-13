"""«21: Добавленное время» — engine rules, entries/limits, Stars entries,
rewards via the golden/jackpot wheel pools, hidden information."""
import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models.blackjack import BlackjackMatch
from app.models.enums import Rarity, TransactionType, WheelPrizePool, WheelPrizeType, WheelSpinSource
from app.models.transaction import CoinTransaction
from app.models.wheel import WheelSpin
from app.services import blackjack_engine as engine
from app.services import blackjack_service, wheel_service
from app.services.game_config_service import get_config
from tests.factories import create_player, create_wheel_prize, get_user_by_telegram_id
from tests.utils import telegram_headers

settings = get_settings()
INTERNAL_HEADERS = {"X-Internal-Secret": settings.internal_api_secret}
START_BALANCE = 500


# --- Engine -----------------------------------------------------------------


def test_deck_is_52_unique_cards_with_16_ten_values_and_4_legends():
    deck = engine.shuffled_deck()
    assert len(deck) == 52 and len(set(deck)) == 52
    assert sum(1 for c in deck if engine.card_value(c) == 10) == 16
    assert sum(1 for c in deck if engine.card_rank(c) == engine.LEGEND) == 4


@pytest.mark.parametrize(
    "cards, expected",
    [
        (["fw:2", "mf:9"], (11, False)),
        (["fw:captain", "mf:striker"], (20, False)),
        (["fw:legend", "mf:6"], (17, True)),
        (["fw:legend", "mf:6", "gk:10"], (17, False)),
        (["fw:legend", "mf:legend"], (12, True)),
        (["fw:legend", "mf:legend", "gk:9"], (21, True)),
        (["fw:10", "mf:5", "gk:legend"], (16, False)),
        (["fw:10", "mf:playmaker", "gk:5"], (25, False)),
    ],
)
def test_hand_value_counts_legends_as_1_or_11(cards, expected):
    assert engine.hand_value(cards) == expected


def test_natural_is_only_two_card_21():
    assert engine.is_natural(["fw:legend", "mf:captain"])
    assert engine.is_natural(["fw:10", "mf:legend"])
    assert not engine.is_natural(["fw:7", "mf:7", "gk:7"])
    assert not engine.is_natural(["fw:10", "mf:9"])


def test_dealer_hits_below_17_and_stands_on_soft_17():
    assert engine.dealer_should_hit(["fw:10", "mf:6"])
    assert engine.dealer_should_hit(["fw:legend", "mf:5"])  # soft 16
    assert not engine.dealer_should_hit(["fw:legend", "mf:6"])  # soft 17 → stands (S17)
    assert not engine.dealer_should_hit(["fw:10", "mf:7"])
    dealer, deck = engine.play_dealer(["fw:2", "mf:3"], ["gk:4", "df:5", "fw:6", "mf:10"])
    assert dealer == ["fw:2", "mf:3", "gk:4", "df:5", "fw:6"]  # 20 — stops
    assert deck == ["mf:10"]


def test_initial_and_final_outcomes():
    nat, nat2, plain = ["fw:legend", "mf:10"], ["gk:legend", "df:captain"], ["fw:10", "mf:8"]
    assert engine.initial_outcome(nat, nat2) == ("push", "both_natural")
    assert engine.initial_outcome(nat, plain) == ("hat_trick", "natural")
    assert engine.initial_outcome(plain, nat) == ("loss", "dealer_natural")
    assert engine.initial_outcome(plain, ["gk:10", "df:9"]) is None

    assert engine.final_outcome(["fw:10", "mf:8", "gk:5"], ["df:10", "fw:6"]) == ("loss", "offside")
    assert engine.final_outcome(["fw:10", "mf:8"], ["df:10", "fw:6", "gk:9"]) == ("win", "dealer_offside")
    assert engine.final_outcome(["fw:10", "mf:9"], ["df:10", "fw:8"]) == ("win", "higher")
    assert engine.final_outcome(["fw:10", "mf:7"], ["df:10", "fw:8"]) == ("loss", "lower")
    assert engine.final_outcome(["fw:10", "mf:8"], ["df:10", "fw:8"]) == ("push", "equal")
    # A three-card 21 vs bot 21 is a plain draw, not a hat-trick.
    assert engine.final_outcome(["fw:7", "mf:7", "gk:7"], ["df:10", "fw:legend", "gk:10"]) == ("push", "equal")


# --- Helpers ----------------------------------------------------------------


def _stack(monkeypatch, player, dealer, rest=()):
    """Deal order is player, bot, player, bot(hole), then draws from `rest`."""
    deck = [player[0], dealer[0], player[1], dealer[1], *rest]
    used = set(deck)
    deck += [c for c in engine.full_deck() if c not in used]
    monkeypatch.setattr(blackjack_service, "_shuffled_deck", lambda: list(deck))


async def _register(client, db_session, telegram_id, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200
    return await get_user_by_telegram_id(db_session, telegram_id), telegram_headers(telegram_id, bot_token)


async def _pools(db_session):
    golden = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1000, pool=WheelPrizePool.golden)
    jackpot = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=5000, pool=WheelPrizePool.jackpot)
    return golden, jackpot


async def _set_config(db_session, **values):
    config = await get_config(db_session)
    for key, value in values.items():
        setattr(config, key, value)
    await db_session.commit()


async def _spins(db_session) -> list[WheelSpin]:
    return list((await db_session.execute(select(WheelSpin))).scalars().all())


# --- Outcomes ---------------------------------------------------------------


async def test_natural_hat_trick_spins_jackpot_wheel(client, db_session, bot_token, monkeypatch):
    golden, jackpot = await _pools(db_session)
    user, headers = await _register(client, db_session, 870001, bot_token)
    _stack(monkeypatch, ["fw:legend", "mf:captain"], ["gk:10", "df:7"])

    resp = await client.post("/api/v1/blackjack/start", headers=headers)
    assert resp.status_code == 200, resp.text
    body = resp.json()
    match = body["match"]
    assert match["status"] == "finished"
    assert match["outcome"] == "hat_trick" and match["reward_pool"] == "jackpot"
    assert match["prize"]["id"] == jackpot.id
    assert body["spin_result"]["prize"]["id"] == jackpot.id
    assert body["new_balance"] == START_BALANCE + 5000
    # Once finished, the bot's hand is revealed.
    assert [c["rank"] for c in match["dealer_cards"]] == ["10", "7"]

    spins = await _spins(db_session)
    assert len(spins) == 1
    assert spins[0].source == WheelSpinSource.blackjack and spins[0].blackjack_match_id == match["id"]


async def test_both_naturals_is_a_push_that_grants_a_free_replay(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870002, bot_token)
    _stack(monkeypatch, ["fw:legend", "mf:captain"], ["gk:legend", "df:10"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    assert match["outcome"] == "push" and match["reward_pool"] is None

    status = (await client.get("/api/v1/blackjack/status", headers=headers)).json()
    assert status["free_remaining"] == 0 and status["replay_entries"] == 1

    _stack(monkeypatch, ["fw:10", "mf:8"], ["gk:10", "df:9"])
    replay = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    assert replay["entry_source"] == "replay" and replay["status"] == "in_progress"
    assert await _spins(db_session) == []


async def test_dealer_natural_is_a_loss_with_consolation(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870003, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:legend", "df:striker"])

    body = (await client.post("/api/v1/blackjack/start", headers=headers)).json()
    assert body["match"]["outcome"] == "loss" and body["match"]["outcome_reason"] == "dealer_natural"
    assert body["match"]["consolation_coins"] == 25
    assert body["new_balance"] == START_BALANCE + 25
    tx = (await db_session.execute(
        select(CoinTransaction).where(CoinTransaction.type == TransactionType.blackjack_consolation)
    )).scalars().all()
    assert len(tx) == 1 and tx[0].amount == 25
    assert await _spins(db_session) == []


async def test_zero_consolation_pays_nothing(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    await _set_config(db_session, blackjack_consolation_coins=0)
    user, headers = await _register(client, db_session, 870004, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:legend", "df:striker"])

    body = (await client.post("/api/v1/blackjack/start", headers=headers)).json()
    assert body["match"]["outcome"] == "loss" and body["new_balance"] == START_BALANCE


async def test_hit_into_offside_loses_and_bot_does_not_draw(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870005, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:6"], ["gk:10", "df:6"], rest=["fw:captain"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    assert match["status"] == "in_progress" and match["player_total"] == 16

    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/hit", headers=headers)).json()
    assert body["match"]["outcome"] == "loss" and body["match"]["outcome_reason"] == "offside"
    assert body["match"]["player_total"] == 26
    assert len(body["match"]["dealer_cards"]) == 2
    assert body["new_balance"] == START_BALANCE + 25


async def test_stand_win_when_bot_goes_offside_spins_golden_wheel(client, db_session, bot_token, monkeypatch):
    golden, _ = await _pools(db_session)
    user, headers = await _register(client, db_session, 870006, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:8"], ["gk:6", "df:10"], rest=["fw:9"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert body["match"]["outcome"] == "win" and body["match"]["outcome_reason"] == "dealer_offside"
    assert body["match"]["dealer_total"] == 25 and len(body["match"]["dealer_cards"]) == 3
    assert body["match"]["reward_pool"] == "golden" and body["spin_result"]["prize"]["id"] == golden.id
    assert body["new_balance"] == START_BALANCE + 1000


async def test_bot_stands_on_soft_17(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870007, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:8"], ["gk:legend", "df:6"], rest=["fw:2"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert len(body["match"]["dealer_cards"]) == 2 and body["match"]["dealer_total"] == 17
    assert body["match"]["outcome"] == "win" and body["match"]["outcome_reason"] == "higher"


async def test_stand_lower_loses_and_equal_pushes(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    await _set_config(db_session, blackjack_free_per_day=2)
    user, headers = await _register(client, db_session, 870008, bot_token)

    _stack(monkeypatch, ["fw:10", "mf:7"], ["gk:10", "df:8"])
    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert body["match"]["outcome"] == "loss" and body["match"]["outcome_reason"] == "lower"

    _stack(monkeypatch, ["fw:10", "mf:8"], ["gk:10", "df:8"])
    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert body["match"]["outcome"] == "push"
    await db_session.refresh(user)
    assert user.blackjack_replay_entries == 1


async def test_hitting_to_21_auto_stands(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870009, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:6"], ["gk:10", "df:7"], rest=["fw:5"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/hit", headers=headers)).json()
    assert body["match"]["status"] == "finished" and body["match"]["player_total"] == 21
    assert body["match"]["outcome"] == "win"  # three-card 21 → golden, not jackpot
    assert body["match"]["reward_pool"] == "golden"


async def test_empty_jackpot_pool_falls_back_to_golden(client, db_session, bot_token, monkeypatch):
    golden = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=1000, pool=WheelPrizePool.golden)
    user, headers = await _register(client, db_session, 870010, bot_token)
    _stack(monkeypatch, ["fw:legend", "mf:captain"], ["gk:10", "df:7"])

    body = (await client.post("/api/v1/blackjack/start", headers=headers)).json()
    assert body["match"]["outcome"] == "hat_trick" and body["match"]["reward_pool"] == "golden"
    assert body["spin_result"]["prize"]["id"] == golden.id


async def test_card_prize_from_golden_pool(client, db_session, bot_token, monkeypatch):
    await create_player(db_session, rarity=Rarity.legendary)
    await create_wheel_prize(
        db_session, prize_type=WheelPrizeType.card_rarity, weight=1, card_rarity=Rarity.legendary, pool=WheelPrizePool.golden,
    )
    user, headers = await _register(client, db_session, 870011, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:10", "df:8"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert body["spin_result"]["card_result"]["card"]["player"]["rarity"] == "legendary"


# --- Hidden information ------------------------------------------------------


async def test_hole_card_and_deck_never_leak_while_in_progress(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870020, bot_token)
    # The hole card is the only "captain"; the next deck card is the only "playmaker" drawn early.
    _stack(monkeypatch, ["fw:10", "mf:4"], ["gk:9", "df:captain"], rest=["fw:2", "gk:playmaker"])

    start = await client.post("/api/v1/blackjack/start", headers=headers)
    status = await client.get("/api/v1/blackjack/status", headers=headers)
    match_id = start.json()["match"]["id"]
    hit = await client.post(f"/api/v1/blackjack/matches/{match_id}/hit", headers=headers)

    for resp, match in (
        (start, start.json()["match"]),
        (status, status.json()["active_match"]),
        (hit, hit.json()["match"]),
    ):
        assert match["status"] == "in_progress"
        assert match["dealer_cards"][1] == {"hidden": True, "rank": None, "suit": None}
        assert match["dealer_total"] == 9  # only the face-up card
        text = resp.text
        assert "captain" not in text and "playmaker" not in text
        assert "deck" not in text and "server_state" not in text

    assert hit.json()["match"]["player_total"] == 16
    # Revealed once finished.
    done = (await client.post(f"/api/v1/blackjack/matches/{match_id}/stand", headers=headers)).json()["match"]
    assert done["dealer_cards"][1] == {"hidden": False, "rank": "captain", "suit": "df"}
    assert "deck" not in str(done)


# --- Entries, limits, concurrency ---------------------------------------------


async def test_free_entry_then_blocked(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870030, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:legend", "df:striker"])  # instant loss

    status = (await client.get("/api/v1/blackjack/status", headers=headers)).json()
    assert status["free_remaining"] == 1 and status["golden_prizes"] and status["jackpot_prizes"]
    assert (await client.post("/api/v1/blackjack/start", headers=headers)).status_code == 200

    resp = await client.post("/api/v1/blackjack/start", headers=headers)
    assert resp.status_code == 409
    assert resp.json()["error"]["details"]["reason"] == "no_entries"


async def test_start_with_active_match_returns_it_without_consuming_entry(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870031, bot_token)
    user.blackjack_paid_entries = 3
    await db_session.commit()
    _stack(monkeypatch, ["fw:10", "mf:4"], ["gk:9", "df:8"])

    first = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    second = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    assert first["id"] == second["id"] and first["entry_source"] == "free"
    await db_session.refresh(user)
    assert user.blackjack_paid_entries == 3 and user.blackjack_free_used_today == 1
    count = (await db_session.execute(select(func.count(BlackjackMatch.id)))).scalar()
    assert count == 1


async def test_entry_order_free_then_replay_then_paid(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870032, bot_token)
    user.blackjack_paid_entries = 1
    user.blackjack_replay_entries = 1
    await db_session.commit()

    sources = []
    for _ in range(3):
        _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:legend", "df:striker"])  # instant loss each time
        sources.append((await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]["entry_source"])
    assert sources == ["free", "replay", "paid"]
    assert (await client.post("/api/v1/blackjack/start", headers=headers)).status_code == 409


async def test_repeated_stand_and_hit_after_finish_do_not_pay_twice(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870033, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:10", "df:7"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    first = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    again = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    hit_after = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/hit", headers=headers)).json()
    assert first["new_balance"] == again["new_balance"] == hit_after["new_balance"] == START_BALANCE + 1000
    assert again["spin_result"] is None and again["match"]["prize"]["coins_amount"] == 1000
    assert len(again["match"]["player_cards"]) == 2
    assert len(await _spins(db_session)) == 1


async def test_cannot_play_someone_elses_match(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    _, headers_a = await _register(client, db_session, 870034, bot_token)
    _, headers_b = await _register(client, db_session, 870035, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:4"], ["gk:9", "df:8"])

    match = (await client.post("/api/v1/blackjack/start", headers=headers_a)).json()["match"]
    assert (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers_b)).status_code == 404


async def test_disabled_flag_blocks_start_and_purchase(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    await _set_config(db_session, blackjack_enabled=False)
    _, headers = await _register(client, db_session, 870036, bot_token)

    assert (await client.get("/api/v1/blackjack/status", headers=headers)).json()["enabled"] is False
    resp = await client.post("/api/v1/blackjack/start", headers=headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "disabled"
    assert (await client.post("/api/v1/blackjack/stars-invoice", headers=headers)).status_code == 409


async def test_disabling_mid_hand_still_lets_the_hand_finish(client, db_session, bot_token, monkeypatch):
    await _pools(db_session)
    _, headers = await _register(client, db_session, 870037, bot_token)
    _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:10", "df:7"])
    match = (await client.post("/api/v1/blackjack/start", headers=headers)).json()["match"]
    await _set_config(db_session, blackjack_enabled=False)

    body = (await client.post(f"/api/v1/blackjack/matches/{match['id']}/stand", headers=headers)).json()
    assert body["match"]["outcome"] == "win"


# --- Stars entries -----------------------------------------------------------


async def _fake_invoice_link(payload_token, title, description, stars_amount):
    return f"https://t.me/invoice/{payload_token}"


def _deliver_json(token, telegram_id, charge_id, amount=10):
    return {
        "payload_token": token, "telegram_user_id": telegram_id,
        "telegram_payment_charge_id": charge_id, "total_amount": amount,
    }


async def test_stars_entry_purchase_is_idempotent_and_playable(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(blackjack_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _pools(db_session)
    user, headers = await _register(client, db_session, 870040, bot_token)

    invoice = (await client.post("/api/v1/blackjack/stars-invoice", headers=headers)).json()
    assert invoice["stars_amount"] == 10
    token = invoice["payload_token"]
    assert (await client.get(f"/api/v1/blackjack/stars-invoices/{token}", headers=headers)).json()["status"] == "pending"

    pre = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout", json={"payload_token": token, "total_amount": 10},
        headers=INTERNAL_HEADERS,
    )
    assert pre.json()["ok"] is True

    charge = "bj-charge-" + "a" * 130
    first = await client.post("/api/v1/internal/stars-payments/deliver", json=_deliver_json(token, 870040, charge), headers=INTERNAL_HEADERS)
    assert first.status_code == 200 and first.json()["blackjack_result"]["kind"] == "entry"
    again = await client.post("/api/v1/internal/stars-payments/deliver", json=_deliver_json(token, 870040, charge), headers=INTERNAL_HEADERS)
    assert again.status_code == 200 and again.json()["blackjack_result"]["kind"] == "entry"

    polled = (await client.get(f"/api/v1/blackjack/stars-invoices/{token}", headers=headers)).json()
    assert polled["status"] == "completed" and polled["blackjack_result"] == {"kind": "entry"}

    await db_session.refresh(user)
    assert user.blackjack_paid_entries == 1 and user.blackjack_paid_bought_today == 1
    # Stars never touch the coin balance.
    assert user.balance == START_BALANCE

    # free first, then the purchased entry.
    for expected in ("free", "paid"):
        _stack(monkeypatch, ["fw:10", "mf:9"], ["gk:legend", "df:striker"])
        resp = await client.post("/api/v1/blackjack/start", headers=headers)
        assert resp.json()["match"]["entry_source"] == expected


async def test_paid_daily_limit_enforced_at_invoice_and_pre_checkout(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(blackjack_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _pools(db_session)
    await _set_config(db_session, blackjack_paid_daily_limit=1, blackjack_stars_cost=15)
    _, headers = await _register(client, db_session, 870041, bot_token)

    a = (await client.post("/api/v1/blackjack/stars-invoice", headers=headers)).json()
    b = (await client.post("/api/v1/blackjack/stars-invoice", headers=headers)).json()  # both created before paying
    assert a["stars_amount"] == 15
    deliver = await client.post(
        "/api/v1/internal/stars-payments/deliver",
        json=_deliver_json(a["payload_token"], 870041, "bj-limit-1", amount=15), headers=INTERNAL_HEADERS,
    )
    assert deliver.status_code == 200

    pre_b = await client.post(
        "/api/v1/internal/stars-payments/pre-checkout", json={"payload_token": b["payload_token"], "total_amount": 15},
        headers=INTERNAL_HEADERS,
    )
    assert pre_b.json()["ok"] is False
    resp = await client.post("/api/v1/blackjack/stars-invoice", headers=headers)
    assert resp.status_code == 409 and resp.json()["error"]["details"]["reason"] == "paid_limit"

    status = (await client.get("/api/v1/blackjack/status", headers=headers)).json()
    assert status["paid_bought_today"] == 1 and status["paid_entries"] == 1


async def test_zero_paid_limit_means_free_only(client, db_session, bot_token, monkeypatch):
    monkeypatch.setattr(blackjack_service, "_request_telegram_invoice_link", _fake_invoice_link)
    await _set_config(db_session, blackjack_paid_daily_limit=0)
    _, headers = await _register(client, db_session, 870042, bot_token)
    assert (await client.post("/api/v1/blackjack/stars-invoice", headers=headers)).status_code == 409


# --- Regular wheel is untouched ------------------------------------------------


async def test_regular_wheel_only_rolls_regular_pool(client, db_session, bot_token):
    regular = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=1, coins_amount=10)
    await _pools(db_session)
    _, headers = await _register(client, db_session, 870050, bot_token)

    for _ in range(15):
        assert (await wheel_service._roll_prize(db_session)).id == regular.id
    status = (await client.get("/api/v1/wheel/status", headers=headers)).json()
    assert [p["id"] for p in status["prizes"]] == [regular.id]
    assert status["prizes"][0]["pool"] == "regular"

    spin = (await client.post("/api/v1/wheel/spin/free", headers=headers)).json()
    assert spin["prize"]["id"] == regular.id and spin["new_balance"] == START_BALANCE + 10


# --- Admin -----------------------------------------------------------------------


async def test_admin_pool_filter_and_summary(client, db_session, bot_token):
    session_resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    headers = {"Authorization": f"Bearer {session_resp.json()['admin_token']}"}

    create = await client.post(
        "/api/v1/admin/wheel/prizes", headers=headers,
        json={"prize_type": "coins", "pool": "golden", "weight": 3, "coins_amount": 1000},
    )
    assert create.status_code == 200 and create.json()["pool"] == "golden"
    await client.post(
        "/api/v1/admin/wheel/prizes", headers=headers,
        json={"prize_type": "coins", "pool": "golden", "weight": 1, "coins_amount": 3000},
    )
    await client.post("/api/v1/admin/wheel/prizes", headers=headers, json={"prize_type": "coins", "weight": 1, "coins_amount": 500})

    golden = (await client.get("/api/v1/admin/wheel/prizes?pool=golden", headers=headers)).json()
    assert len(golden) == 2 and {p["pool"] for p in golden} == {"golden"}

    summary = (await client.get("/api/v1/admin/wheel/pools-summary", headers=headers)).json()
    by_pool = {p["pool"]: p for p in summary["pools"]}
    assert by_pool["golden"]["expected_value_coins"] == 1500.0  # 0.75×1000 + 0.25×3000
    assert by_pool["regular"]["expected_value_coins"] == 500.0
    assert by_pool["jackpot"]["active_prizes"] == 0
    est = blackjack_service.OUTCOME_ESTIMATE
    # Empty jackpot pool falls back to golden, as in the game.
    expected = est["jackpot"] * 1500 + est["golden"] * 1500 + est["loss"] * 25
    assert summary["blackjack_expected_value_coins"] == pytest.approx(expected, abs=0.1)
