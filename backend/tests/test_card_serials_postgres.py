"""Serial numbers on real Postgres: an unlimited card takes its number in a
short transaction of its own (card_creation._take_serial_now), so parallel
openings don't queue on the Player row; numbers stay unique. Every row a
test creates is deleted on teardown (real_pg)."""
import asyncio
import time
import uuid

import pytest
from sqlalchemy import select, update

from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.player import Player
from app.models.user import User
from app.services.card_creation import create_user_card


@pytest.fixture(autouse=True)
def _fresh_schema():
    # The PG database is migrated by alembic and must not be dropped.
    yield


async def _setup(pg) -> tuple[int, int]:
    async with pg() as s:
        tag = uuid.uuid4().hex[:6]
        player = Player(
            first_name="S", last_name=tag, display_name=f"S {tag}", rating=80, rarity=Rarity.epic,
            country="X", club="Y", position=Position.ST, quick_sell_price=1, is_active=True,
        )
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Serial", balance=0)
        s.add_all([player, user])
        await s.commit()
        return user.id, player.id


async def test_parallel_cards_of_one_player_get_unique_numbers(real_pg):
    user_id, player_id = await _setup(real_pg)

    async def open_one():
        async with real_pg() as s:
            card = await create_user_card(s, user_id, player_id, CardSource.pack)
            # The opening goes on holding its transaction; the others don't wait for it.
            await asyncio.sleep(0.3)
            await s.commit()
            return card.serial_number

    started = time.monotonic()
    serials = await asyncio.gather(*(open_one() for _ in range(10)))
    assert sorted(serials) == list(range(1, 11))
    assert time.monotonic() - started < 2.5  # in a row under the lock it would take 3 s+

    async with real_pg() as s:
        assert (await s.get(Player, player_id)).next_serial_number == 11


async def test_a_caller_already_holding_the_player_row_does_not_hang(real_pg):
    user_id, player_id = await _setup(real_pg)
    async with real_pg() as s:
        # This transaction has the row locked already (as an admin edit in it would).
        started = time.monotonic()
        await s.execute(update(Player).where(Player.id == player_id).values(rating=Player.rating))
        first = await create_user_card(s, user_id, player_id, CardSource.pack)
        second = await create_user_card(s, user_id, player_id, CardSource.pack)
        await s.commit()
        assert time.monotonic() - started < 6  # two lock timeouts of 2 s at most
        assert (first.serial_number, second.serial_number) == (1, 2)

    async with real_pg() as s:
        cards = (await s.execute(select(UserCard.serial_number).where(UserCard.player_id == player_id))).scalars().all()
        assert sorted(cards) == [1, 2]
        assert (await s.get(Player, player_id)).next_serial_number == 3
