"""Seed script: populates the database with demo data for local development.

Usage (from backend/, with the venv active and DATABASE_URL pointing at a
migrated database):

    python -m app.seed

Safe to re-run: every entity is looked up by a natural unique key before
being created, so running it twice does not create duplicates.
"""
import asyncio
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from sqlalchemy import select

from app.database import AsyncSessionLocal
from app.models.achievement import Achievement
from app.models.card import UserCard
from app.models.enums import (
    CardSource,
    NotificationType,
    Position,
    Rarity,
    TradeCardSide,
    TradeStatus,
)
from app.models.game_config import GameConfig
from app.models.lineup import Lineup, LineupCard
from app.models.pack import Pack, PackRarityProbability
from app.models.player import Player
from app.models.trade import TradeOffer, TradeOfferCard
from app.models.user import User
from app.services.card_creation import create_user_card
from app.services.lineup_service import FORMATION_SLOTS
from app.services.wallet_service import credit_coins

random.seed(42)

BASE_DIR = Path(__file__).resolve().parent.parent
STATIC_DIR = BASE_DIR / "static"

RARITY_COLORS = {
    Rarity.common: ((100, 116, 139), (71, 85, 105)),
    Rarity.rare: ((37, 99, 235), (14, 165, 233)),
    Rarity.epic: ((147, 51, 234), (219, 39, 119)),
    Rarity.legendary: ((245, 158, 11), (239, 68, 68)),
}
RARITY_SELL_PRICE = {Rarity.common: 10, Rarity.rare: 35, Rarity.epic: 120, Rarity.legendary: 400}
RATING_RANGES = {Rarity.common: (58, 73), Rarity.rare: (74, 81), Rarity.epic: (82, 88), Rarity.legendary: (90, 99)}

FIRST_NAMES = [
    "Лукас", "Матео", "Диего", "Кевин", "Бруно", "Хавьер", "Родриго", "Фелипе", "Марко", "Андрес",
    "Томас", "Никлас", "Виктор", "Оскар", "Хуго", "Леон", "Давид", "Симон", "Артур", "Габриэль",
    "Энзо", "Йохан", "Мартин", "Пабло",
]
LAST_NAMES = [
    "Сильва", "Феррейра", "Родригес", "Мартинес", "Гарсия", "Новак", "Андерсон", "Ковач", "Мюллер",
    "Дюбуа", "Бергман", "Ланге", "Оливейра", "Кастро", "Морено", "Рейес", "Виейра", "Нильссон",
    "Хаким", "Диалло", "Traoré", "Соса", "Перейра", "Виллани",
]
COUNTRIES = [
    "Бразилия", "Аргентина", "Германия", "Франция", "Испания", "Италия", "Португалия",
    "Нидерланды", "Хорватия", "Уругвай", "Япония", "Марокко", "Сенегал", "Швеция", "Бельгия",
]
CLUBS = [
    "Норд Юнайтед", "Ривер Стар", "Атлетико Резерв", "Вест Энд", "ФК Комета", "Гранит Юнайтед",
    "Южный Крест", "Стальные Львы", "Портовый ФК", "Горизонт СК", "Альянс", "Феникс Юнайтед",
    "Титан", "Экспресс ФК", "Меридиан",
]
POSITIONS = list(Position)


def _font(size: int) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def generate_player_image(path: Path, display_name: str, rating: int, position: str, rarity: Rarity) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    top, bottom = RARITY_COLORS[rarity]
    width, height = 400, 520
    img = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = round(top[0] + (bottom[0] - top[0]) * ratio)
        g = round(top[1] + (bottom[1] - top[1]) * ratio)
        b = round(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))

    draw.rectangle([16, 16, width - 16, height - 16], outline=(255, 255, 255), width=4)
    draw.text((32, 32), str(rating), font=_font(64), fill=(255, 255, 255))
    draw.text((32, 100), position, font=_font(32), fill=(255, 255, 255))

    initials = "".join(part[0] for part in display_name.split() if part)[:3].upper()
    draw.text((width / 2 - 60, height / 2 - 60), initials, font=_font(96), fill=(255, 255, 255))
    draw.text((32, height - 70), display_name, font=_font(28), fill=(255, 255, 255))

    img.save(path, "WEBP", quality=85)


def generate_pack_image(path: Path, name: str, colors: tuple) -> None:
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    top, bottom = colors
    width, height = 400, 500
    img = Image.new("RGB", (width, height), top)
    draw = ImageDraw.Draw(img)
    for y in range(height):
        ratio = y / height
        r = round(top[0] + (bottom[0] - top[0]) * ratio)
        g = round(top[1] + (bottom[1] - top[1]) * ratio)
        b = round(top[2] + (bottom[2] - top[2]) * ratio)
        draw.line([(0, y), (width, y)], fill=(r, g, b))
    draw.polygon([(width / 2, 60), (width - 60, height / 2), (width / 2, height - 60), (60, height / 2)], outline=(255, 255, 255), width=6)
    draw.text((40, height - 80), name, font=_font(32), fill=(255, 255, 255))
    img.save(path, "WEBP", quality=85)


def generate_placeholder_image() -> None:
    path = STATIC_DIR / "players" / "placeholder" / "player_placeholder.webp"
    if path.exists():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    img = Image.new("RGB", (400, 520), (51, 65, 85))
    draw = ImageDraw.Draw(img)
    draw.rectangle([16, 16, 384, 504], outline=(148, 163, 184), width=4)
    draw.text((110, 220), "?", font=_font(120), fill=(148, 163, 184))
    img.save(path, "WEBP", quality=85)


def build_players_data() -> list[dict]:
    rarity_counts = [(Rarity.common, 20), (Rarity.rare, 12), (Rarity.epic, 8), (Rarity.legendary, 4)]
    total_needed = sum(c for _, c in rarity_counts)

    all_pairs = [(f, l) for f in FIRST_NAMES for l in LAST_NAMES]
    random.shuffle(all_pairs)
    assert len(all_pairs) >= total_needed, "name pool too small for the requested player count"
    pairs = all_pairs[:total_needed]

    data = []
    idx = 0
    for rarity, count in rarity_counts:
        for _ in range(count):
            first, last = pairs[idx]
            position = POSITIONS[idx % len(POSITIONS)]
            country = COUNTRIES[idx % len(COUNTRIES)]
            club = CLUBS[idx % len(CLUBS)]
            rating = random.randint(*RATING_RANGES[rarity])
            idx += 1
            data.append(
                dict(
                    first_name=first,
                    last_name=last,
                    display_name=f"{first} {last}",
                    rating=rating,
                    rarity=rarity,
                    country=country,
                    club=club,
                    position=position,
                    quick_sell_price=RARITY_SELL_PRICE[rarity],
                    is_active=True,
                )
            )
    return data


async def seed_players(db) -> list[Player]:
    players = []
    for seq, data in enumerate(build_players_data(), start=1):
        existing = (
            await db.execute(select(Player).where(Player.display_name == data["display_name"]))
        ).scalar_one_or_none()
        if existing:
            players.append(existing)
            continue

        # ASCII-only filename regardless of the (Cyrillic) display name — keeps
        # static file URLs safe without needing transliteration/URL-encoding.
        slug = f"player_{seq:03d}"
        image_path = f"players/{data['rarity'].value}/{slug}.webp"
        generate_player_image(
            STATIC_DIR / image_path, data["display_name"], data["rating"], data["position"].value, data["rarity"]
        )
        player = Player(**data, image_path=image_path)
        db.add(player)
        players.append(player)
    await db.commit()
    for p in players:
        await db.refresh(p)
    return players


async def seed_packs(db) -> dict[str, Pack]:
    pack_specs = [
        {
            "slug": "basic",
            "name": "Basic Pack",
            "description": "Стартовый пак: 3 карточки, в основном обычные игроки с шансом на редкого.",
            "price": 100,
            "card_count": 3,
            "guaranteed_min_rarity": None,
            "sort_order": 1,
            "colors": ((100, 116, 139), (51, 65, 85)),
            "probabilities": {Rarity.common: 0.75, Rarity.rare: 0.20, Rarity.epic: 0.05},
        },
        {
            "slug": "premium",
            "name": "Premium Pack",
            "description": "5 карточек с гарантированной редкой и повышенным шансом на эпическую.",
            "price": 350,
            "card_count": 5,
            "guaranteed_min_rarity": Rarity.rare,
            "sort_order": 2,
            "colors": ((37, 99, 235), (147, 51, 234)),
            "probabilities": {Rarity.common: 0.45, Rarity.rare: 0.35, Rarity.epic: 0.17, Rarity.legendary: 0.03},
        },
        {
            "slug": "elite",
            "name": "Elite Pack",
            "description": "5 карточек с гарантированной эпической и высоким шансом на легендарную.",
            "price": 800,
            "card_count": 5,
            "guaranteed_min_rarity": Rarity.epic,
            "sort_order": 3,
            "colors": ((245, 158, 11), (239, 68, 68)),
            "probabilities": {Rarity.common: 0.20, Rarity.rare: 0.35, Rarity.epic: 0.35, Rarity.legendary: 0.10},
        },
    ]

    packs = {}
    for spec in pack_specs:
        existing = (await db.execute(select(Pack).where(Pack.slug == spec["slug"]))).scalar_one_or_none()
        image_path = f"packs/{spec['slug']}.webp"
        generate_pack_image(STATIC_DIR / image_path, spec["name"], spec["colors"])

        if existing:
            packs[spec["slug"]] = existing
            continue

        pack = Pack(
            slug=spec["slug"], name=spec["name"], description=spec["description"], price=spec["price"],
            card_count=spec["card_count"], guaranteed_min_rarity=spec["guaranteed_min_rarity"],
            image_path=image_path, is_active=True, sort_order=spec["sort_order"],
        )
        db.add(pack)
        await db.flush()
        for rarity, probability in spec["probabilities"].items():
            db.add(PackRarityProbability(pack_id=pack.id, rarity=rarity, probability=probability))
        packs[spec["slug"]] = pack

    await db.commit()
    for p in packs.values():
        await db.refresh(p)
    return packs


async def seed_achievements(db) -> None:
    specs = [
        ("first_pack", "Первый пак", "Откройте свой первый пак", 20, "packs_opened", 1),
        ("pack_collector", "Коллекционер паков", "Откройте 10 паков", 100, "packs_opened", 10),
        ("squad_builder", "Собиратель состава", "Соберите 10 разных футболистов", 50, "unique_players", 10),
        ("big_collection", "Большая коллекция", "Соберите 25 разных футболистов", 150, "unique_players", 25),
        ("first_trade", "Первый обмен", "Завершите свой первый обмен", 30, "trades_completed", 1),
    ]
    for code, name, description, reward, metric, target in specs:
        existing = (await db.execute(select(Achievement).where(Achievement.code == code))).scalar_one_or_none()
        if existing:
            continue
        db.add(
            Achievement(
                code=code, name=name, description=description, reward_coins=reward, metric=metric, target_value=target
            )
        )
    await db.commit()


async def seed_game_config(db) -> None:
    existing = await db.get(GameConfig, 1)
    if existing is None:
        db.add(GameConfig(id=1))
        await db.commit()


async def _get_or_create_user(db, telegram_id: int, username: str, first_name: str, last_name: str, is_admin: bool = False) -> User:
    existing = (await db.execute(select(User).where(User.telegram_id == telegram_id))).scalar_one_or_none()
    if existing:
        return existing
    user = User(
        telegram_id=telegram_id, username=username, first_name=first_name, last_name=last_name,
        is_admin=is_admin, received_starting_bonus=True, balance=0,
    )
    db.add(user)
    await db.flush()
    from app.models.enums import TransactionType

    await credit_coins(db, user, 500, TransactionType.starting_balance, "Стартовый бонус (seed)")
    await db.commit()
    await db.refresh(user)
    return user


async def seed_admin_user(db) -> User:
    from app.config import get_settings

    settings = get_settings()
    return await _get_or_create_user(db, settings.dev_user_telegram_id, "dev_admin", "Dev", "Admin", is_admin=True)


async def seed_test_users(db) -> list[User]:
    specs = [
        (900000001, "test_alex", "Алекс", "Иванов"),
        (900000002, "test_maria", "Мария", "Петрова"),
        (900000003, "test_ivan", "Иван", "Смирнов"),
        (900000004, "test_olga", "Ольга", "Кузнецова"),
        (900000005, "test_dmitry", "Дмитрий", "Соколов"),
    ]
    users = []
    for telegram_id, username, first, last in specs:
        users.append(await _get_or_create_user(db, telegram_id, username, first, last))
    return users


async def seed_example_collection(db, users: list[User], players: list[Player]) -> None:
    result = await db.execute(select(UserCard.owner_id))
    owners_with_cards = {row[0] for row in result.all()}

    for user in users:
        if user.id in owners_with_cards:
            continue
        sample = random.sample(players, k=min(15, len(players)))
        for player in sample:
            await create_user_card(db, user.id, player.id, CardSource.seed)
    await db.commit()


async def seed_example_lineup(db, user: User, players: list[Player]) -> None:
    existing = (await db.execute(select(Lineup).where(Lineup.user_id == user.id))).scalar_one_or_none()
    if existing:
        return

    by_position: dict[Position, list[Player]] = {}
    for p in players:
        by_position.setdefault(p.position, []).append(p)

    lineup = Lineup(user_id=user.id, formation="4-3-3", is_active=True)
    db.add(lineup)
    await db.flush()

    for slot in FORMATION_SLOTS:
        candidates = by_position.get(slot.ideal_position)
        if not candidates:
            continue
        player = candidates.pop(0)
        card = (
            await db.execute(
                select(UserCard).where(UserCard.owner_id == user.id, UserCard.player_id == player.id)
            )
        ).scalar_one_or_none()
        if not card:
            card = await create_user_card(db, user.id, player.id, CardSource.seed)
        card.is_in_lineup = True
        db.add(card)
        db.add(LineupCard(lineup_id=lineup.id, user_card_id=card.id, slot_code=slot.code))

    await db.commit()


async def seed_example_trade(db, sender: User, receiver: User) -> None:
    existing = (
        await db.execute(
            select(TradeOffer).where(TradeOffer.sender_id == sender.id, TradeOffer.receiver_id == receiver.id)
        )
    ).scalar_one_or_none()
    if existing:
        return

    sender_card = (
        await db.execute(
            select(UserCard).where(UserCard.owner_id == sender.id, UserCard.is_in_lineup.is_(False)).limit(1)
        )
    ).scalar_one_or_none()
    receiver_card = (
        await db.execute(
            select(UserCard).where(UserCard.owner_id == receiver.id, UserCard.is_in_lineup.is_(False)).limit(1)
        )
    ).scalar_one_or_none()
    if not sender_card or not receiver_card:
        return

    offer = TradeOffer(
        sender_id=sender.id, receiver_id=receiver.id, sender_coins=20, receiver_coins=0,
        message="Обменяемся? (пример из seed-скрипта)", status=TradeStatus.pending,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
    )
    db.add(offer)
    await db.flush()

    sender_card.is_locked_in_trade = True
    receiver_card.is_locked_in_trade = True
    db.add(sender_card)
    db.add(receiver_card)
    db.add(TradeOfferCard(trade_offer_id=offer.id, user_card_id=sender_card.id, side=TradeCardSide.offered))
    db.add(TradeOfferCard(trade_offer_id=offer.id, user_card_id=receiver_card.id, side=TradeCardSide.requested))

    from app.models.notification import Notification

    db.add(
        Notification(
            user_id=receiver.id, type=NotificationType.trade_offer_received,
            title="Новое предложение обмена", body=f"{sender.full_display_name()} предложил(а) вам обмен.",
            related_object_type="trade_offer", related_object_id=offer.id,
        )
    )
    await db.commit()


async def main() -> None:
    generate_placeholder_image()

    async with AsyncSessionLocal() as db:
        print("Seeding game config...")
        await seed_game_config(db)

        print("Seeding players...")
        players = await seed_players(db)
        print(f"  {len(players)} players available")

        print("Seeding packs...")
        packs = await seed_packs(db)
        print(f"  {len(packs)} packs available")

        print("Seeding achievements...")
        await seed_achievements(db)

        print("Seeding dev admin user...")
        await seed_admin_user(db)

        print("Seeding test users...")
        users = await seed_test_users(db)

        print("Seeding example collection...")
        await seed_example_collection(db, users, players)

        print("Seeding example lineup...")
        await seed_example_lineup(db, users[0], players)

        print("Seeding example trade...")
        await seed_example_trade(db, users[1], users[2])

    print("Seed complete.")


if __name__ == "__main__":
    asyncio.run(main())
