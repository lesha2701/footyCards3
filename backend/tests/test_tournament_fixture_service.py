from app.services.tournament_fixture_service import generate_fixtures


def test_generates_14_rounds_of_4_matches_for_8_clubs():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    assert len(fixtures) == 56  # 14 rounds * 4 matches
    by_round: dict[int, list] = {}
    for round_number, a, b in fixtures:
        by_round.setdefault(round_number, []).append((a, b))
    assert set(by_round.keys()) == set(range(1, 15))
    for round_number, matches in by_round.items():
        assert len(matches) == 4
        clubs_in_round = [c for pair in matches for c in pair]
        assert sorted(clubs_in_round) == [1, 2, 3, 4, 5, 6, 7, 8]


def test_every_pair_meets_exactly_twice():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    pair_counts: dict[frozenset, int] = {}
    for _, a, b in fixtures:
        key = frozenset((a, b))
        pair_counts[key] = pair_counts.get(key, 0) + 1
    assert len(pair_counts) == 28  # C(8, 2)
    assert all(count == 2 for count in pair_counts.values())


def test_no_club_faces_same_opponent_on_consecutive_rounds():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    opponent_by_round_per_club: dict[int, dict[int, int]] = {}
    for round_number, a, b in fixtures:
        opponent_by_round_per_club.setdefault(a, {})[round_number] = b
        opponent_by_round_per_club.setdefault(b, {})[round_number] = a
    for club_id, opponents_by_round in opponent_by_round_per_club.items():
        for round_number in range(1, 14):
            assert opponents_by_round[round_number] != opponents_by_round[round_number + 1]


def test_leg_two_repeats_leg_one_pairings():
    fixtures = generate_fixtures([1, 2, 3, 4, 5, 6, 7, 8])
    by_round: dict[int, set] = {}
    for round_number, a, b in fixtures:
        by_round.setdefault(round_number, set()).add(frozenset((a, b)))
    for round_number in range(1, 8):
        assert by_round[round_number] == by_round[round_number + 7]
