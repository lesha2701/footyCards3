"""«Карьера тренера»: the positional 2D replay built over the engine's
result — deterministic, goals where and by whom the event log says, inside
the pitch, a 3-5 minute show of a compact size, and the live first half
equal to the first half of the finished match."""
import base64
import random
from datetime import datetime, timedelta

from app.models.enums import Position
from app.services import career_replay_service as replay
from app.services import career_service
from app.services import career_tactics_service as tactics
from app.services import tournament_match_engine as engine
from tests.test_career import API, _reset_rate_limits  # noqa: F401  (autouse fixture)
from tests.test_career_tactics import _defaults, _runner, _season, _season_row


def _played(seed: int, orders=None):
    config = _defaults()
    a = _runner("a", config=config, bench_positions=(Position.ST, Position.CM))
    b = _runner("b", config=config, offset=100, rating=72)
    a.halftime = orders
    lineups = {"a": replay.lineup_record(a), "b": replay.lineup_record(b)}
    random.seed(seed)
    match = engine.simulate_match_controlled(tactics.CareerMatchController(a, b), config, "Home", "Away")
    return match, lineups


def _clock_at(rep: dict, frame: int) -> float:
    for kind, f0, n, t0, t1, ms in rep["segments"]:
        if f0 <= frame < f0 + n:
            return t0 + (t1 - t0) * (frame - f0) / max(1, n)
    raise AssertionError(f"frame {frame} outside segments")


def _player_at(rep: dict, frame: int, slot: int) -> dict:
    pidx = rep["roster"][slot]
    for f, s, p in rep["swaps"]:
        if s == slot and f <= frame:
            pidx = p
    return rep["players"][pidx]


def test_same_seed_same_frames():
    match, lineups = _played(11)
    one = replay.build_replay(4242, match.event_log, lineups)
    two = replay.build_replay(4242, match.event_log, lineups)
    assert one == two
    assert replay.build_replay(4243, match.event_log, lineups)["frames"] != one["frames"]


def test_goals_match_event_log_minutes_and_scorers():
    goals_seen = 0
    for seed in range(12):
        match, lineups = _played(100 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        frames = replay.decode_frames(rep)
        marks = {ev: frame for frame, ev in rep["marks"]}
        # Every event of the log is placed on the timeline exactly once.
        assert sorted(marks) == list(range(len(match.event_log)))
        assert len(rep["marks"]) == len(match.event_log)
        for idx, e in enumerate(match.event_log):
            frame = marks[idx]
            clock = _clock_at(rep, frame)
            assert (e["minute"] - 1) * 60 <= clock < e["minute"] * 60 + 30, (idx, e["minute"], clock)
            if e["event_type"] != "goal":
                continue
            goals_seen += 1
            # The ball is in the attacked goal, between the posts.
            bx, by = frames[frame]["ball"]
            assert abs(bx - replay.WIDTH / 2) <= 3.9
            assert by >= replay.LENGTH - 0.5 if e["team"] == "a" else by <= 0.5
            # The last player on the ball before the shot is the scorer.
            holder = next(frames[f]["holder"] for f in range(frame, -1, -1) if frames[f]["holder"] is not None)
            scorer = _player_at(rep, frame, holder)
            assert scorer["s"] == e["team"]
            assert scorer["name"] == e["payload"]["shooter"]
    assert goals_seen > 0


def test_positions_stay_on_the_pitch_and_move_smoothly():
    match, lineups = _played(7)
    rep = replay.build_replay(9, match.event_log, lineups)
    frames = replay.decode_frames(rep)
    assert rep["count"] == len(frames) > 100
    for fr in frames:
        for x, y in [fr["ball"], *fr["players"]]:
            assert 0 <= x <= replay.WIDTH and 0 <= y <= replay.LENGTH
    # Episodes run in real time: nobody jumps more than a sprint per frame
    # (+ quantisation) inside an episode.
    for kind, f0, n, t0, t1, ms in rep["segments"]:
        if kind == "bridge":
            continue
        for f in range(f0 + 1, f0 + n):
            for (x0, y0), (x1, y1) in zip(frames[f - 1]["players"], frames[f]["players"]):
                assert ((x1 - x0) ** 2 + (y1 - y0) ** 2) ** 0.5 <= 9.0 * replay.STEP + 0.6
    # Goalkeepers stay near their own goal.
    for fr in frames:
        assert fr["players"][0][1] < 40 and fr["players"][11][1] > replay.LENGTH - 40


def test_show_length_and_response_size():
    for seed in range(6):
        match, lineups = _played(300 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        seconds = sum(n * ms for _, _, n, _, _, ms in rep["segments"]) / 1000
        assert 150 <= seconds <= 320, seconds
        assert len(rep["frames"]) < 120_000
        assert rep["segments"][0][0] == "kickoff" and rep["segments"][-1][0] == "whistle"
        # Segments tile the frames without gaps.
        pos = 0
        for _, f0, n, *_ in rep["segments"]:
            assert f0 == pos
            pos += n
        assert pos == rep["count"]


def test_live_first_half_is_the_first_half_of_the_full_match():
    match, lineups = _played(21)
    on = {p[0] for p in lineups["a"]["xi"]}
    orders = tactics.clean_halftime({"mentality": "ATTACKING", "subs": [{"out": 9, "in": 50}]}, on, {50, 51}, 3)
    full, _ = _played(21, orders)
    first = [e for e in match.event_log if e["minute"] <= tactics.HALF_TIME]
    live = replay.build_replay(77, first, lineups, halves=1)
    done = replay.build_replay(77, full.event_log, lineups)
    assert live["halves"] == 1
    size = live["count"] * replay.FRAME_SIZE
    assert base64.b64decode(done["frames"])[:size] == base64.b64decode(live["frames"])
    assert done["segments"][:len(live["segments"])] == live["segments"]
    # The half-time substitute comes on in the second half.
    subs = [e for e in full.event_log if e["event_type"] == "substitution"]
    assert subs and any(p["id"] == 50 for p in done["players"])
    assert done["swaps"] and all(f >= live["count"] for f, _, _ in done["swaps"])


def test_old_matches_without_lineups_still_draw():
    match, _ = _played(5)
    rep = replay.build_replay(1, match.event_log, None)
    assert rep["count"] > 0 and len(rep["roster"]) == 22
    scorers = {e["payload"]["shooter"] for e in match.event_log if e["event_type"] == "goal"}
    names = {p["name"] for p in rep["players"]}
    assert scorers <= names


async def test_replay_endpoint_live_break_then_full_match(client, db_session, bot_token):
    user_id, headers, season = await _season(client, db_session, bot_token, 881001)
    first = datetime.fromisoformat(season["schedule"][0])
    row = await _season_row(db_session, season["id"])
    match_index = next(i for i, (h, a) in enumerate(row.state["fixtures"][0]) if 0 in (h, a))
    url = f"{API}/career/seasons/{season['id']}/rounds/0/matches/{match_index}/replay"
    assert (await client.get(url, headers=headers)).status_code == 404  # not played yet

    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=1))
    resp = await client.get(url, headers=headers)
    assert resp.status_code == 200, resp.text
    live = resp.json()
    assert live["live"] and live["replay"]["halves"] == 1
    assert all(e["minute"] <= 45 for e in live["events"])
    assert len(live["replay"]["players"]) >= 22 and all(p["name"] for p in live["replay"]["players"][:22])
    view = (await client.get(f"{API}/career", headers=headers)).json()["season"]["live"]
    assert view["match_index"] == match_index

    await career_service.resolve_due(db_session, season["id"], now=first + timedelta(minutes=11))
    done = (await client.get(url, headers=headers)).json()
    assert not done["live"] and done["replay"]["halves"] == 2
    assert done["home_score"] + done["away_score"] == sum(1 for e in done["events"] if e["event_type"] == "goal")
    size = live["replay"]["count"] * replay.FRAME_SIZE
    assert base64.b64decode(done["replay"]["frames"])[:size] == base64.b64decode(live["replay"]["frames"])
    # Matches without a human have no events to draw.
    other = next(i for i, (h, a) in enumerate(row.state["fixtures"][0]) if 0 not in (h, a))
    bad = await client.get(f"{API}/career/seasons/{season['id']}/rounds/0/matches/{other}/replay", headers=headers)
    assert bad.status_code == 404


def test_defending_block_keeps_its_shape():
    """Without the ball a team drops into a compact block, not onto its goal
    line: outside set pieces the outfield players' median depth stays off
    the six-yard box, and the lines keep their order (strikers ahead)."""
    deep = total = 0
    for seed in range(6):
        match, lineups = _played(700 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        frames = replay.decode_frames(rep)
        for fr in frames:
            for side, slots in (("a", range(1, 11)), ("b", range(12, 22))):
                depths = sorted(fr["players"][i][1] if side == "a" else replay.LENGTH - fr["players"][i][1] for i in slots)
                total += 1
                deep += depths[4] < 10.0
    assert deep / total < 0.03, deep / total


def test_passes_reach_the_receiver_and_a_held_ball_stays_at_the_feet():
    """A pass ends at the receiver (aimed at where he runs to, not where he
    was a frame ago) and the holder's ball is a step in front of him."""
    quant = replay.LENGTH / 255 + 0.05      # one quantisation step
    checked = held = 0
    for seed in range(6):
        match, lineups = _played(300 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        frames = replay.decode_frames(rep)
        for f0, f1, _passer, receiver in rep["passes"]:
            last = f1 - 1
            if last < f0 or last >= len(frames):
                continue
            bx, by = frames[last]["ball"]
            px, py = frames[last]["players"][receiver]
            assert ((bx - px) ** 2 + (by - py) ** 2) ** 0.5 <= quant, (seed, f0, f1)
            checked += 1
        for fr in frames:
            if fr["holder"] is None:
                continue
            bx, by = fr["ball"]
            px, py = fr["players"][fr["holder"]]
            assert ((bx - px) ** 2 + (by - py) ** 2) ** 0.5 <= replay.DRIBBLE + quant
            held += 1
    assert checked > 50 and held > 500


def test_the_ball_reaches_a_new_holder_instead_of_jumping_to_him():
    """In episodes, a player who gets the ball (a pass, a tackle, a set
    piece taker) has it come to him: one frame of pass speed at most."""
    received = 0
    for seed in range(6):
        match, lineups = _played(500 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        frames = replay.decode_frames(rep)
        episode = set()
        for kind, f0, n, *_ in rep["segments"]:
            if kind in ("goal", "moment"):
                episode.update(range(f0, f0 + n))
        for f in range(1, len(frames)):
            holder = frames[f]["holder"]
            if f not in episode or holder is None or frames[f - 1]["holder"] == holder:
                continue
            bx, by = frames[f - 1]["ball"]
            px, py = frames[f]["players"][holder]
            assert ((bx - px) ** 2 + (by - py) ** 2) ** 0.5 <= 9.0, (seed, f)
            received += 1
    assert received > 100


def test_shots_are_struck_from_where_the_event_says():
    """A goal from inside the box is struck inside it (the finisher makes his
    run first), a long-range one from 20-32 m."""
    seen = {"in_box": 0, "long_range": 0}
    for seed in range(10):
        match, lineups = _played(700 + seed)
        rep = replay.build_replay(seed, match.event_log, lineups)
        frames = replay.decode_frames(rep)
        marks = {ev: frame for frame, ev in rep["marks"]}
        for idx, e in enumerate(match.event_log):
            p = e.get("payload") or {}
            if e["event_type"] != "goal" or p.get("set_piece") or p.get("is_penalty"):
                continue
            kind = p.get("shot_type")
            if kind not in seen:
                continue
            bx, by = frames[marks[idx] - 2]["ball"]
            out = replay.LENGTH - by if e["team"] == "a" else by
            if kind == "long_range":
                assert 20.0 <= out <= 32.0, (seed, idx, out)
            else:
                assert out <= 20.5, (seed, idx, out)
            seen[kind] += 1
    assert seen["in_box"] > 3
