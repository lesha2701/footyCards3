"""The «Реальные Пацаны» collection (migration 0262): the data follows the
game's rules, the art ships with it, and it drops without a pack of its own."""
import importlib.util
from pathlib import Path

import pytest
from sqlalchemy import func, select

from app.models.card_collection import CardCollection
from app.models.coach import Coach
from app.models.enums import CoachBoostType, Position, Rarity
from app.models.muse import Muse
from app.models.pack import Pack
from app.models.player import Player
from app.models.stadium import Stadium
from app.seed import RARITY_SELL_PRICE, RATING_RANGES
from app.services import collection_service
from app.services.career_morale_service import TRAITS
from app.services.coach_service import magnitude_for
from app.services.duel_service import STYLES
from app.services.muse_service import EFFECTS

BACKEND = Path(__file__).resolve().parent.parent
_spec = importlib.util.spec_from_file_location(
    "migration_0262", BACKEND / "alembic" / "versions" / "0262_realnye_patsany_collection.py"
)
migration = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(migration)


def test_player_data_follows_the_rules():
    assert len(migration.PLAYERS) == 14
    for name, slug, position, _country, club, rating, attack, defence, rarity, style, trait in migration.PLAYERS:
        low, high = RATING_RANGES[Rarity(rarity)]
        assert low <= rating <= high, name
        assert 1 <= attack <= 99 and 1 <= defence <= 99, name
        assert Position(position) and style in STYLES and trait in TRAITS and club, name
        assert migration.SELL_PRICE[rarity] == RARITY_SELL_PRICE[Rarity(rarity)], name
        assert (BACKEND / "static" / "players" / rarity / f"rp_{slug}.webp").is_file(), name


def test_coach_boosts_match_their_rarity():
    assert len(migration.COACHES) == 2
    for name, image, _country, rarity, boosts in migration.COACHES:
        assert (BACKEND / "static" / image).is_file(), name
        for boost_type, magnitude in boosts:
            assert magnitude == pytest.approx(magnitude_for(CoachBoostType(boost_type), Rarity(rarity))), name


def test_stadium_and_muses_art_and_effects():
    assert (BACKEND / "static" / migration.COVER).is_file()
    assert (BACKEND / "static" / migration.STADIUM[2]).is_file()
    assert migration.STADIUM[4:] == (0, 3)  # only the opponent malus
    assert len(migration.MUSES) == 2
    for name, _title, _description, _icon, image, _rarity, effect, value, _sort in migration.MUSES:
        assert (BACKEND / "static" / image).is_file(), name
        assert effect in EFFECTS and value > 0, name


@pytest.mark.asyncio
async def test_seeded_collection_counts_everyone_and_has_no_pack(real_pg):
    async with real_pg() as db:
        collection = (await db.execute(
            select(CardCollection).where(CardCollection.name == migration.COLLECTION)
        )).scalar_one()
        assert collection.is_active and collection.reward_coins > 0

        players = (await db.execute(select(Player).where(Player.collection_id == collection.id))).scalars().all()
        assert len(players) == 14 and all(p.is_active and p.is_pack_droppable for p in players)
        for model, column in ((Coach, Coach.collection_id), (Stadium, Stadium.collection_id), (Muse, Muse.card_collection_id)):
            rows = (await db.execute(select(model).where(column == collection.id))).scalars().unique().all()
            assert rows and all(r.is_active and r.is_pack_droppable for r in rows)

        assert await collection_service._staff_progress(db, 0, collection.id) == (5, 0)
        assert (await db.execute(
            select(func.count(Pack.id)).where(Pack.name == migration.COLLECTION)
        )).scalar_one() == 0
