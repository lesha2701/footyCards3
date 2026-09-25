from datetime import datetime
from zoneinfo import ZoneInfo

from services.notifier import _keyboard_for
from services.player_tournament_scheduler import PLAYER_TOURNAMENT_SLOTS
from services.tournament_scheduler import SIMULATION_SLOTS, _due_slots

TZ = ZoneInfo("Europe/Moscow")


def test_player_slots_are_10_15_21():
    assert PLAYER_TOURNAMENT_SLOTS == [(10, 0), (15, 0), (21, 0)]


def test_due_slots_with_custom_slots_catches_up():
    now = datetime(2026, 9, 25, 16, 0, tzinfo=TZ)
    assert _due_slots(now, {}, slots=PLAYER_TOURNAMENT_SLOTS) == [(10, 0), (15, 0)]
    assert _due_slots(now, {(10, 0): now.date()}, slots=PLAYER_TOURNAMENT_SLOTS) == [(15, 0)]


def test_club_slots_unchanged_by_default():
    now = datetime(2026, 9, 25, 13, 0, tzinfo=TZ)
    assert SIMULATION_SLOTS == [(12, 0), (20, 0)]
    assert _due_slots(now, {}) == [(12, 0)]


def test_reminder_lead_with_custom_slots():
    now = datetime(2026, 9, 25, 20, 10, tzinfo=TZ)
    assert _due_slots(now, {}, lead_minutes=60, slots=PLAYER_TOURNAMENT_SLOTS) == [(10, 0), (15, 0), (21, 0)]


def _url(markup) -> str:
    return markup.inline_keyboard[0][0].web_app.url


def test_notifier_deep_links_player_tournament_types():
    for t in ("player_tournament_match", "player_tournament_results_ready", "player_tournament_reminder"):
        assert _url(_keyboard_for(None, None, t)).endswith("/player-tournament")


def test_notifier_related_object_player_tournament_and_club_unchanged():
    assert _url(_keyboard_for("player_tournament", 5, "player_tournament_match")).endswith("/player-tournament")
    assert _url(_keyboard_for("club_match", 7)).endswith("/clubs/tournament/7")
    assert _keyboard_for(None, None) is None
    assert _keyboard_for(None, None, "trade_offer") is None
