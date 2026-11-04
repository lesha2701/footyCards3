"""The Python port of the team episodes against the fixture written by the
client's engine (frontend/src/lib/oneOnOne/team.fixture.test.ts): exact
equality, or client and server would disagree on what happened."""

import json
from pathlib import Path

from app.services.free_kick_3d_engine import Swipe
from app.services.team_attack_engine import TeamTimeline, create_team_episode, replay_team

CASES = json.loads((Path(__file__).parent / "fixtures" / "team_episodes.json").read_text(encoding="utf-8"))


def _timeline(t: dict) -> TeamTimeline:
    s = t["shot"]
    return TeamTimeline(
        controls=[tuple(c) for c in t["controls"]],
        feint=(t["feint"]["tick"], t["feint"]["dir"]) if t["feint"] else None,
        shot=(s["tick"], Swipe(s["dx"], s["dy"], s["curve"], s["durationMs"])) if s else None,
        passes=[(p["tick"], (p["target"], p["mode"], p["power"])) for p in t["passes"]],
    )


def test_replays_the_client_episodes_exactly():
    # One test, not one per case: the fixture has hundreds of them.
    for case in CASES:
        _check(case)


def _check(case):
    r = replay_team(create_team_episode(case["kind"], case["seed"], case["rating"]), _timeline(case["timeline"]))
    assert (r.outcome, r.tick, r.feint, r.chip) == (case["outcome"], case["tick"], case["feint"], case["chip"])
    f = case["flight"]
    if f is None:
        assert r.flight is None
        return
    fl = r.flight
    assert fl.outcome == f["outcome"]
    k = f["keeper"]
    assert (fl.keeper_x, fl.keeper_z, fl.lying_for, fl.spread) == (k["x"], k["z"], k["lyingFor"], k["spread"])
    assert fl.over_y == f["overY"]
    assert fl.events == f["events"]
    end = f["end"]
    assert fl.end_t == end["t"]
    assert fl.end_position == (end["position"]["x"], end["position"]["y"], end["position"]["z"])
    assert fl.end_velocity == (end["velocity"]["x"], end["velocity"]["y"], end["velocity"]["z"])
