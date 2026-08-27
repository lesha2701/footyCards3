import random

from app.services import tournament_match_engine as engine


def _fake_lineup(club_id: int):
    """A minimal fake lineup: list of (club_card_id, player_id, name, rating, position, category) tuples,
    one per FORMATION_SLOTS category, enough for _pick_actor to find candidates in every category."""
    return [
        {"club_card_id": club_id * 100 + i, "player_id": club_id * 100 + i, "name": f"Player{club_id}-{i}",
         "rating": 70, "position": pos, "category": cat}
        for i, (cat, pos) in enumerate([
            ("GK", "GK"), ("DEF", "CB"), ("DEF", "CB"), ("DEF", "LB"), ("DEF", "RB"),
            ("MID", "CDM"), ("MID", "CM"), ("MID", "CAM"), ("FWD", "LW"), ("FWD", "ST"), ("FWD", "RW"),
        ])
    ]


class _FakeConfig:
    match_shot_type_in_box_weight = 55
    match_shot_type_long_range_weight = 35
    match_shot_type_empty_net_weight = 10


def test_moment_queue_has_between_14_and_22_moments():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    assert 14 <= len(moments) <= 22


def test_shot_moments_pick_real_actors_from_both_sides():
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(70, 70, _FakeConfig(), lineup_a, lineup_b)
    shot_moments = [m for m in moments if m["kind"] == "shot" and m["shot_type"] != "empty_net"]
    assert shot_moments  # with 14-22 moments and the existing shot-chance weight, at least one is virtually certain
    for m in shot_moments:
        attacking_lineup = lineup_a if m["attacking_side"] == "a" else lineup_b
        defending_lineup = lineup_b if m["attacking_side"] == "a" else lineup_a
        attacking_ids = {a["club_card_id"] for a in attacking_lineup}
        defending_ids = {a["club_card_id"] for a in defending_lineup}
        assert m["actors"]["shooter"]["club_card_id"] in attacking_ids
        assert m["actors"]["pass_target"]["club_card_id"] in attacking_ids
        assert m["actors"]["defender"]["club_card_id"] in defending_ids
        for actor in m["actors"].values():
            assert set(actor.keys()) >= {"club_card_id", "player_id", "name", "rating", "position"}


def test_stronger_side_attacks_more_often(monkeypatch):
    monkeypatch.setattr(engine.random, "sample", lambda pop, k: list(range(1, k + 1)))
    lineup_a, lineup_b = _fake_lineup(1), _fake_lineup(2)
    moments = engine.generate_moment_queue(140, 10, _FakeConfig(), lineup_a, lineup_b)
    attacking_a = sum(1 for m in moments if m["attacking_side"] == "a")
    assert attacking_a > len(moments) / 2
