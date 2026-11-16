"""«Менеджер» matchday squad: two «Академия» slots, the bench of the match
day, substitutions for tired starters, the extra formations and the grant
a little above the division budget."""
import pytest

import app.core.rate_limit as rate_limit_module
from app.models.enums import CardSource, Position, Rarity
from app.services import manager_finance, manager_service, manager_tactics
from app.services.card_creation import create_user_card
from app.services.club_formation_service import CLUB_FORMATIONS, get_formation_slots
from app.services.game_config_service import get_config
from tests.factories import create_player
from tests.test_manager import API, _club, _no_season_at_the_real_clock, _player  # noqa: F401 (an autouse fixture)

pytestmark = pytest.mark.usefixtures("trade_guards_off")


@pytest.fixture(autouse=True)
def _reset_rate_limits():
    rate_limit_module._hits.clear()
    yield


def _entry(key: str, position: str, rating: int, kind: str = "npc") -> dict:
    return {"key": key, "kind": kind, "ref": None, "name": key, "position": position, "rating": rating}


async def test_two_academy_cards_start_and_move_between_slots(client, db_session, bot_token):
    a_id, a_headers = await _player(client, db_session, bot_token, 896001, "ST")
    one = await create_player(db_session, rarity=Rarity.diamond, rating=55, position=Position.CB, path_talent_code="fighter",
                              display_name="Воспитанник Один")
    two = await create_player(db_session, rarity=Rarity.diamond, rating=54, position=Position.CM, path_talent_code="fighter",
                              display_name="Воспитанник Два")
    c1 = await create_user_card(db_session, a_id, one.id, CardSource.seed)
    c2 = await create_user_card(db_session, a_id, two.id, CardSource.seed)
    await db_session.commit()
    view = await _club(client, a_headers)
    assert view["club"]["academy_card_ids"] == [None, None]
    await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": c1.id})
    view = (await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": c2.id, "academy_slot": 2})).json()
    assert view["club"]["academy_card_ids"] == [c1.id, c2.id]
    academy = [p["name"] for p in view["club"]["squad"]["xi"] if p["kind"] == "academy"]
    assert sorted(academy) == ["Воспитанник Два", "Воспитанник Один"]
    # The same card picked for the other slot moves there.
    view = (await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": c2.id, "academy_slot": 1})).json()
    assert view["club"]["academy_card_ids"] == [c2.id, None]
    view = (await client.patch(f"{API}/manager/club", headers=a_headers, json={"clear_academy": True, "academy_slot": 1})).json()
    assert view["club"]["academy_card_ids"] == [None, None]
    resp = await client.patch(f"{API}/manager/club", headers=a_headers, json={"academy_card_id": c1.id, "academy_slot": 3})
    assert resp.status_code == 409


async def test_one_academy_slot_when_configured(client, db_session, bot_token):
    config = await get_config(db_session)
    config.manager_finance = {**(config.manager_finance or {}), "academy_slots": 1}
    await db_session.commit()
    _a_id, a_headers = await _player(client, db_session, bot_token, 896011)
    view = await _club(client, a_headers)
    assert view["club"]["academy_card_ids"] == [None]


def test_matchday_bench_covers_every_line_first():
    bench = [_entry("fwd1", "ST", 70), _entry("fwd2", "ST", 69), _entry("fwd3", "ST", 68), _entry("mid", "CM", 60),
             _entry("def", "CB", 58), _entry("gk", "GK", 50), _entry("fwd4", "ST", 67)]
    subs = manager_service.matchday_bench(bench, 5)
    assert [e["key"] for e in subs] == ["gk", "def", "mid", "fwd1", "fwd2"]
    assert manager_service.matchday_bench(bench, 0) == []


async def test_squad_view_marks_the_matchday_bench(client, db_session, bot_token):
    _a_id, a_headers = await _player(client, db_session, bot_token, 896021, "CB")
    await _club(client, a_headers)
    for n in range(4):  # the own CB + 4 CBs from the catalog: one sits
        p = await create_player(db_session, rating=60 + n, position=Position.CB, display_name=f"Защитник {n}")
        assert (await client.post(f"{API}/manager/npc", headers=a_headers, json={"player_id": p.id, "kind": "loan"})).status_code == 200
    squad = (await client.get(f"{API}/manager", headers=a_headers)).json()["club"]["squad"]
    assert squad["bench_size"] == manager_finance.DEFAULTS["bench_size"]
    assert [p["name"] for p in squad["bench"]] == ["Защитник 0"] and squad["bench"][0]["sub"] is True


async def test_tired_starter_is_substituted(db_session):
    config = await get_config(db_session)
    slots = get_formation_slots("4-3-3")
    positions = {"GK": "GK", "DEF": "CB", "MID": "CM", "FWD": "ST"}
    xi = [{**_entry(f"s{i}", positions[s.category], 60), "slot": s.code} for i, s in enumerate(slots)]
    bench = [_entry("fresh", "ST", 62), _entry("weak", "CB", 50)]
    spec = {"xi": xi, "bench": bench, "cards": {}, "index": 0, "name": "Совы", "formation": "4-3-3", "mods": {}}
    bot = {"xi": [{**p, "kind": "bot"} for p in xi], "cards": {}, "index": 1, "name": "Бот", "formation": "4-3-3", "mods": {}}
    subs = manager_service._Subs({"a": spec, "b": bot}, config)
    *_sides, events = subs.before_phase(30, 0, 0)
    assert events == []
    _sa, _sb, lineup_a, _lb, events = subs.before_phase(61, 0, 0)
    assert len(events) == 1 and events[0]["event_type"] == "substitution" and events[0]["payload"]["in"] == "fresh"
    # The starters are tired now, the substitute is not.
    first = manager_finance.DEFAULTS["tired_pct"][0]
    ratings = sorted(c["rating"] for c in lineup_a)
    assert ratings[0] == 60 * (100 - first) // 100 and 62 in ratings
    played = subs.played("a")
    assert len(played) == 12 and played[-1][0]["key"] == "fresh"
    assert len({card["club_card_id"] for _p, card in played}) == 12  # a substitute has his own engine id
    # The weak defender never beats a tired 60, and the bot side has nobody.
    for minute in (71, 81):
        assert subs.before_phase(minute, 0, 0)[-1] == []


async def test_manager_formations_and_the_grant(db_session):
    config = await get_config(db_session)
    assert {"4-1-4-1", "4-3-1-2"} <= set(manager_tactics.FORMATIONS)
    # Manager only: clubs, the draft and the career don't offer them.
    assert "4-1-4-1" not in CLUB_FORMATIONS and "4-3-1-2" not in CLUB_FORMATIONS
    for code in ("4-1-4-1", "4-3-1-2"):
        assert len(get_formation_slots(code)) == 11 and len(code) <= 8  # manager_clubs.formation is String(8)
    labels = {f["value"]: f["label"] for f in manager_tactics.rules_out(config)["formations"]}
    assert labels["4-3-1-2"] == "4-3-1-2 (ромб)"
    snap = {"level": 0, "marketing": 0, "shop": 0}
    base = config.manager_division_budget[config.manager_divisions - 1]
    grant = manager_service.season_grant(config.manager_divisions, snap, config)["grant"]
    assert grant == manager_service._nice(base * manager_finance.DEFAULTS["grant_pct"] / 100) > base
