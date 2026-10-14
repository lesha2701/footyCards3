"""Goal commentary fits the score: "открывает счёт" only on the opener (club /
player-tournament / career engine and the Card Arena)."""
from app.services import match_service
from app.services.tournament_match_engine import fix_goal_descriptions, score_phrase


def test_score_phrase():
    assert score_phrase(1, 0) == "открывает счёт"
    assert score_phrase(1, 1) == "сравнивает счёт"
    assert score_phrase(2, 1) == "выходит вперёд"
    assert score_phrase(4, 1) == "увеличивает преимущество"
    assert score_phrase(3, 5) == "сокращает отставание"


def _goal(team, club):
    return {"minute": 10, "event_type": "goal", "team": team, "description": f"⚽ Гол! {club} открывает счёт!"}


def test_engine_log_rewrites_the_opener_phrase_by_running_score():
    events = [
        _goal("a", "Dev FC"),
        {"minute": 20, "event_type": "save", "team": "b", "description": "🧤 сейв"},
        _goal("b", "Полёт"), _goal("b", "Полёт"), _goal("b", "Полёт"), _goal("a", "Dev FC"),
        {"minute": 80, "event_type": "goal", "team": "a", "description": "⚽ ГОЛ! Dev FC забивает!"},
    ]
    fix_goal_descriptions(events)
    texts = [e["description"] for e in events if e["event_type"] == "goal"]
    assert texts == [
        "⚽ Гол! Dev FC открывает счёт!",
        "⚽ Гол! Полёт сравнивает счёт!",
        "⚽ Гол! Полёт выходит вперёд!",
        "⚽ Гол! Полёт увеличивает преимущество!",
        "⚽ Гол! Dev FC сокращает отставание!",
        "⚽ ГОЛ! Dev FC забивает!",  # neutral texts stay
    ]


def test_arena_goal_text_fits_the_score():
    state = {"user_score": 2, "opponent_score": 2}
    event = {"event_type": "goal", "description": "⚽ ГОЛ! Красивый удар — твоя команда открывает счёт!"}
    match_service._fit_goal_to_score(event, "user", state)
    assert event["description"] == "⚽ ГОЛ! Красивый удар — твоя команда сравнивает счёт!"
    opener = {"event_type": "goal", "description": "⚽ ГОЛ! Красивый удар — твоя команда открывает счёт!"}
    match_service._fit_goal_to_score(opener, "user", {"user_score": 1, "opponent_score": 0})
    assert "открывает счёт" in opener["description"]
