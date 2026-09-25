from collections import Counter

import pytest

from app.services.player_tournament_fixture_service import SIMULATION_SLOTS, TOTAL_ROUNDS, TOURNAMENT_SIZE, generate_fixtures


def test_constants():
    assert TOURNAMENT_SIZE == 16
    assert TOTAL_ROUNDS == 30
    assert SIMULATION_SLOTS == [(10, 0), (15, 0), (21, 0)]


def test_shape_and_pairings():
    ids = list(range(101, 117))
    fixtures = generate_fixtures(ids)
    assert len(fixtures) == 240
    assert {r for r, _, _ in fixtures} == set(range(1, 31))
    for r in range(1, 31):
        players = [p for rr, a, b in fixtures if rr == r for p in (a, b)]
        assert sorted(players) == ids
    pair_counts = Counter(frozenset((a, b)) for _, a, b in fixtures)
    assert len(pair_counts) == 120
    assert set(pair_counts.values()) == {2}


def test_no_back_to_back_same_opponent():
    ids = list(range(1, 17))
    fixtures = generate_fixtures(ids)
    previous: dict[int, int] = {}
    for r in range(1, 31):
        opponent: dict[int, int] = {}
        for rr, a, b in fixtures:
            if rr == r:
                opponent[a], opponent[b] = b, a
        for user_id in ids:
            assert opponent[user_id] != previous.get(user_id)
        previous = opponent


def test_requires_exactly_16():
    with pytest.raises(ValueError):
        generate_fixtures(list(range(15)))
