"""Flank duel history on real Postgres: matches of different seasons saving
the same pair at once (duel_service.save_log is one upsert per pair) never
lose a duel. Every row a test creates is deleted on teardown (real_pg)."""
import asyncio
import uuid

from sqlalchemy import select

from app.models.duel import DuelHistory
from app.services import duel_service


def _book(a_key: str, d_key: str, outcomes: list[str]) -> duel_service.DuelBook:
    book = duel_service.DuelBook(
        tuning={**duel_service.DEFAULT_TUNING, "history_cap": 10_000},
        players={1: (a_key, "speed", "A"), 2: (d_key, "speed", "D")},
    )
    att, dfn = type("C", (), {"player_id": 1})(), type("C", (), {"player_id": 2})()
    for outcome in outcomes:
        book.record(att, dfn, outcome)
    return book


async def test_parallel_saves_of_one_pair_add_up(real_pg):
    a_key, d_key = f"att-{uuid.uuid4().hex[:8]}", f"def-{uuid.uuid4().hex[:8]}"

    async def save(outcomes):
        async with real_pg() as s:
            await duel_service.save_log(s, _book(a_key, d_key, outcomes))
            await s.commit()

    await asyncio.gather(*[save(["advance", "breakdown", "breakdown"]) for _ in range(8)])
    async with real_pg() as s:
        row = (await s.execute(select(DuelHistory).where(
            DuelHistory.attacker_key == a_key, DuelHistory.defender_key == d_key,
        ))).scalar_one()
        assert (row.attacker_wins, row.defender_wins) == (8.0, 16.0)


async def test_the_cap_keeps_the_ratio(real_pg):
    a_key, d_key = f"att-{uuid.uuid4().hex[:8]}", f"def-{uuid.uuid4().hex[:8]}"
    async with real_pg() as s:
        book = _book(a_key, d_key, ["advance"] * 30 + ["breakdown"] * 90)
        book.tuning["history_cap"] = 60
        await duel_service.save_log(s, book)
        await s.commit()
        row = (await s.execute(select(DuelHistory).where(DuelHistory.attacker_key == a_key))).scalar_one()
        assert round(row.attacker_wins, 6) == 15 and round(row.defender_wins, 6) == 45


async def test_overlapping_pairs_saved_in_parallel_never_deadlock(real_pg):
    keys = [f"p{i}-{uuid.uuid4().hex[:6]}" for i in range(4)]
    pairs = [(keys[0], keys[1]), (keys[2], keys[3]), (keys[1], keys[2])]

    def book_for(order):
        book = duel_service.DuelBook(
            tuning={**duel_service.DEFAULT_TUNING, "history_cap": 10_000},
            players={i + 1: (k, "speed", k) for i, k in enumerate(keys)},
        )
        by_key = {k: type("C", (), {"player_id": i + 1})() for i, k in enumerate(keys)}
        for a, d in order:
            book.record(by_key[a], by_key[d], "advance")
        return book

    async def save(order):
        async with real_pg() as s:
            await duel_service.save_log(s, book_for(order))
            await s.commit()

    await asyncio.wait_for(asyncio.gather(*[save(pairs if i % 2 else list(reversed(pairs))) for i in range(10)]), 60)
    async with real_pg() as s:
        rows = (await s.execute(select(DuelHistory).where(DuelHistory.attacker_key.in_(keys)))).scalars().all()
        assert sorted(r.attacker_wins for r in rows) == [10.0, 10.0, 10.0]

