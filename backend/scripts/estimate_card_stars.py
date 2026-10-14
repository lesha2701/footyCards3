"""Estimates what «Звёзды карточек» would do to the existing player base
before card_stars_enabled is switched on. Read-only: only SELECTs. Prices
come from the command line (default = the GameConfig defaults), not from the
live config.

For every (owner, player) pair it counts the copies that could be fed in —
not admin-locked, not in a trade, not in an Arena lineup / Tactico squad /
tournament squad, without a skill — keeping one copy as the star target, and
reports per rarity: how many owners could reach ★, ★★, ★★★ right away, how
many duplicates that burns and how much quick-sell value («Продать
дубликаты») those duplicates represent today.

Usage (from backend/, DATABASE_URL pointing at the DB to inspect):

    python -m scripts.estimate_card_stars
    python -m scripts.estimate_card_stars --dupes 10,15,25 --legendary-dupes 4,6,10
"""
import argparse
import asyncio
import os
from collections import defaultdict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

RARITIES = ("common", "rare", "epic", "legendary")


def _stars_for(free: int, ladder: list[int]) -> int:
    stars = 0
    for need in ladder:
        if free < need:
            break
        free -= need
        stars += 1
    return stars


async def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dupes", default="10,15,25", help="duplicates per star for every rarity")
    for rarity in RARITIES:
        parser.add_argument(f"--{rarity}-dupes", default=None, help=f"override for {rarity}")
    args = parser.parse_args()
    ladders = {
        r: [int(x) for x in (getattr(args, f"{r}_dupes") or args.dupes).split(",")] for r in RARITIES
    }

    engine = create_async_engine(os.environ["DATABASE_URL"])
    async with engine.connect() as conn:
        rows = (await conn.execute(text("""
            SELECT uc.owner_id, uc.player_id, p.rarity::text AS rarity, p.quick_sell_price,
                   count(*) AS copies,
                   count(*) FILTER (
                       WHERE NOT uc.is_locked_by_admin AND NOT uc.is_locked_in_trade AND NOT uc.is_in_lineup
                         AND NOT uc.is_in_tactico_squad AND uc.skill_code IS NULL
                         AND NOT EXISTS (SELECT 1 FROM personal_squad_cards psc WHERE psc.user_card_id = uc.id)
                   ) AS free
            FROM user_cards uc JOIN players p ON p.id = uc.player_id
            WHERE p.rarity::text <> 'diamond'
            GROUP BY uc.owner_id, uc.player_id, p.rarity, p.quick_sell_price
        """))).all()
    await engine.dispose()

    stats = defaultdict(lambda: {"pairs": 0, "max_copies": 0, "copies_hist": defaultdict(int), "stars": defaultdict(int),
                                 "burnt": 0, "value": 0})
    owners = set()
    for r in rows:
        s = stats[r.rarity]
        owners.add(r.owner_id)
        s["pairs"] += 1
        s["max_copies"] = max(s["max_copies"], r.copies)
        bucket = "1" if r.copies == 1 else "2-9" if r.copies < 10 else "10-24" if r.copies < 25 else "25-49" if r.copies < 50 else "50+"
        s["copies_hist"][bucket] += 1
        # One copy stays as the star target (it may itself be locked/skilled).
        feedable = min(r.free, r.copies - 1)
        stars = _stars_for(feedable, ladders[r.rarity])
        s["stars"][stars] += 1
        burnt = sum(ladders[r.rarity][:stars])
        s["burnt"] += burnt
        s["value"] += burnt * r.quick_sell_price

    print(f"owners with non-diamond cards: {len(owners)}; ladders: {ladders}")
    for rarity in RARITIES:
        s = stats.get(rarity)
        if not s:
            print(f"\n{rarity}: no cards")
            continue
        hist = ", ".join(f"{k}: {s['copies_hist'][k]}" for k in ("1", "2-9", "10-24", "25-49", "50+"))
        reach = ", ".join(f"★{n}: {s['stars'][n]}" for n in range(1, len(ladders[rarity]) + 1))
        print(f"\n{rarity}: {s['pairs']} (owner, player) pairs, max copies {s['max_copies']}")
        print(f"  copies per pair: {hist}")
        print(f"  could claim right away: {reach or '-'}")
        print(f"  duplicates burnt for that: {s['burnt']} (quick-sell value {s['value']} coins)")


if __name__ == "__main__":
    asyncio.run(main())
