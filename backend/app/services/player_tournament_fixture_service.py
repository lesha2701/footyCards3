TOURNAMENT_SIZE = 16
TOTAL_ROUNDS = 30
# Local app timezone; keep in sync with bot/services/player_tournament_scheduler.py.
# Deliberately not 20:00 — that is the club tournament slot.
SIMULATION_SLOTS: list[tuple[int, int]] = [(10, 0), (15, 0), (21, 0)]


def generate_fixtures(user_ids: list[int]) -> list[tuple[int, int, int]]:
    """Circle-method round-robin for exactly 16 players: fixes user_ids[0],
    rotates the other 15 through 15 rounds of 8 matches (leg 1, every pair
    meets once). Leg 2 (rounds 16-30) repeats the same pairings with home/away
    swapped. Each player faces a different opponent in each of the 15 leg-1
    rounds, so round 15's opponent never equals round 16's (= round 1's)."""
    if len(user_ids) != TOURNAMENT_SIZE:
        raise ValueError("generate_fixtures requires exactly 16 players")

    fixed = user_ids[0]
    rotating = list(user_ids[1:])

    leg_one: list[tuple[int, int, int]] = []
    for round_index in range(TOURNAMENT_SIZE - 1):
        circle = [fixed] + rotating
        pairs = [(circle[i], circle[len(circle) - 1 - i]) for i in range(TOURNAMENT_SIZE // 2)]
        leg_one.extend((round_index + 1, a, b) for a, b in pairs)
        rotating = [rotating[-1]] + rotating[:-1]

    leg_two = [(round_number + 15, b, a) for round_number, a, b in leg_one]
    return leg_one + leg_two
