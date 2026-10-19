"""«Экипировка» on real Postgres: equipping locks the copy and the card rows
while both eager-load related rows (the copy its item, the card its player)
— a plain FOR UPDATE over such outer joins is rejected by Postgres, which
SQLite never shows. Also: concurrent equips of one copy end consistent.
Every row a test creates is deleted on teardown (real_pg)."""
import asyncio
import uuid
from types import SimpleNamespace

import pytest

from app.core.exceptions import AppError
from app.models.card import UserCard
from app.models.enums import CardSource, Position, Rarity
from app.models.equipment import EquipmentItem, UserEquipment
from app.models.player import Player
from app.models.user import User
from app.services import equipment_service

CONFIG = SimpleNamespace(equipment_enabled=True, equipment_max_rating=3, equipment_max_pp=8, equipment_max_chemistry=1)


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    # The shared test database's game_config row must not be changed.
    async def fake_get_config(_db):
        return CONFIG

    monkeypatch.setattr(equipment_service, "get_config", fake_get_config)
    yield


async def _setup(pg, cards=2):
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Eq", balance=10_000)
        kit = EquipmentItem(name=f"Форма {uuid.uuid4().hex[:6]}", slot="kit", effect="rating", effect_value=1, coins_price=100)
        kit2 = EquipmentItem(name=f"Форма+ {uuid.uuid4().hex[:6]}", slot="kit", effect="rating", effect_value=2, coins_price=100)
        s.add_all([user, kit, kit2])
        await s.flush()
        card_ids = []
        for _ in range(cards):
            tag = uuid.uuid4().hex[:6]
            player = Player(
                first_name="E", last_name=tag, display_name=f"E {tag}", rating=80, rarity=Rarity.common,
                country="X", club="Y", position=Position.ST, quick_sell_price=1, is_active=True,
            )
            s.add(player)
            await s.flush()
            card = UserCard(owner_id=user.id, player_id=player.id, source=CardSource.seed)
            s.add(card)
            await s.flush()
            card_ids.append(card.id)
        copies = [UserEquipment(user_id=user.id, item_id=i.id, source="admin") for i in (kit, kit2)]
        s.add_all(copies)
        await s.commit()
        return user.id, card_ids, [c.id for c in copies]


async def _as(pg, user_id, fn):
    async with pg() as s:
        user = await s.get(User, user_id)
        try:
            return await fn(s, user)
        except AppError as exc:
            return exc


async def _bonus(pg, card_id):
    async with pg() as s:
        return (await s.get(UserCard, card_id)).equipment_rating_bonus


async def test_equip_swap_move_and_unequip(real_pg):
    uid, (a, b), (kit, kit2) = await _setup(real_pg)
    out = await _as(real_pg, uid, lambda s, u: equipment_service.equip(s, u, kit, a))
    assert not isinstance(out, AppError), out
    assert out["rating_bonus"] == 1
    out = await _as(real_pg, uid, lambda s, u: equipment_service.equip(s, u, kit2, a))  # same slot: replaces
    assert out["rating_bonus"] == 2
    out = await _as(real_pg, uid, lambda s, u: equipment_service.equip(s, u, kit2, b))  # moves to card b
    assert await _bonus(real_pg, a) == 0 and await _bonus(real_pg, b) == 2
    out = await _as(real_pg, uid, lambda s, u: equipment_service.unequip(s, u, kit2))
    assert not isinstance(out, AppError) and await _bonus(real_pg, b) == 0


async def test_concurrent_equips_of_one_copy_end_consistent(real_pg):
    uid, (a, b), (kit, _kit2) = await _setup(real_pg)
    results = await asyncio.gather(*[
        _as(real_pg, uid, lambda s, u, card=card: equipment_service.equip(s, u, kit, card)) for card in (a, b, a, b)
    ])
    assert all(not isinstance(r, Exception) or isinstance(r, AppError) for r in results)
    async with real_pg() as s:
        row = await s.get(UserEquipment, kit)
        worn_on = row.user_card_id
        bonuses = {cid: (await s.get(UserCard, cid)).equipment_rating_bonus for cid in (a, b)}
    # Exactly the card that ends up wearing it carries the bonus.
    assert worn_on in (a, b)
    assert bonuses[worn_on] == 1 and sum(bonuses.values()) == 1
