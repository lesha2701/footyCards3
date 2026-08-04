from sqlalchemy import select

from app.models.badge import Badge
from app.models.coin_package import CoinPackage
from app.models.enums import Position, Rarity
from app.models.pack import Pack, PackRarityProbability
from app.models.player import Player
from app.models.user import User

_counter = {"n": 0}


async def create_player(session, rarity: Rarity = Rarity.common, rating: int = 70, position: Position = Position.ST, **overrides) -> Player:
    _counter["n"] += 1
    n = _counter["n"]
    defaults = dict(
        first_name=f"First{n}",
        last_name=f"Last{n}",
        display_name=f"Player {n}",
        rating=rating,
        rarity=rarity,
        country="Тестландия",
        club=f"ФК Тест {n}",
        position=position,
        image_path=None,
        quick_sell_price=10,
        is_active=True,
    )
    defaults.update(overrides)
    player = Player(**defaults)
    session.add(player)
    await session.commit()
    await session.refresh(player)
    return player


async def create_pack(session, slug: str, price: int, card_count: int, probabilities: dict, guaranteed_min_rarity=None, **overrides) -> Pack:
    defaults = dict(name=slug.title(), description="test pack", is_active=True, purchase_limit_per_user=None)
    defaults.update(overrides)
    pack = Pack(slug=slug, price=price, card_count=card_count, guaranteed_min_rarity=guaranteed_min_rarity, **defaults)
    session.add(pack)
    await session.flush()
    for rarity, prob in probabilities.items():
        session.add(PackRarityProbability(pack_id=pack.id, rarity=rarity, probability=prob))
    await session.commit()
    await session.refresh(pack)
    return pack


async def create_badge(session, name: str = "Test Badge", icon: str = "🏆", **overrides) -> Badge:
    defaults = dict(is_active=True, sort_order=0)
    defaults.update(overrides)
    badge = Badge(name=name, icon=icon, **defaults)
    session.add(badge)
    await session.commit()
    await session.refresh(badge)
    return badge


async def create_coin_package(session, stars_price: int, coins_amount: int, **overrides) -> CoinPackage:
    defaults = dict(is_active=True, sort_order=0)
    defaults.update(overrides)
    package = CoinPackage(stars_price=stars_price, coins_amount=coins_amount, **defaults)
    session.add(package)
    await session.commit()
    await session.refresh(package)
    return package


async def get_user_by_telegram_id(session, telegram_id: int) -> User:
    result = await session.execute(select(User).where(User.telegram_id == telegram_id))
    return result.scalar_one()
