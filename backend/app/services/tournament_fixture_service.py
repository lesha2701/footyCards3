def generate_fixtures(club_ids: list[int]) -> list[tuple[int, int, int]]:
    """Standard circle-method round-robin for exactly 8 clubs. Fixes club_ids[0],
    rotates the other 7 through 7 rounds of 4 matches each (leg 1, rounds 1-7,
    every pair meets exactly once). Leg 2 (rounds 8-14) repeats the identical
    7 pairings — round n and round n+7 always share the same pairings, and
    since each club faces a distinct opponent in every one of the 7 leg-1
    rounds, round 7's opponent is never the same as round 8's (= round 1's)
    opponent, so no club ever faces the same opponent on two consecutive
    rounds anywhere across the 14-round schedule."""
    if len(club_ids) != 8:
        raise ValueError("generate_fixtures requires exactly 8 clubs")

    fixed = club_ids[0]
    rotating = list(club_ids[1:])  # 7 clubs, rotates each round

    leg_one: list[tuple[int, int, int]] = []
    for round_index in range(7):
        round_number = round_index + 1
        circle = [fixed] + rotating
        pairs = [(circle[i], circle[len(circle) - 1 - i]) for i in range(4)]
        leg_one.extend((round_number, a, b) for a, b in pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    leg_two = [(round_number + 7, a, b) for round_number, a, b in leg_one]
    return leg_one + leg_two
