import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card_collection import CardCollection
from app.models.enums import Position, Rarity
from app.models.player import Player
from app.services.player_stats_service import compute_default_attack_defense

CSV_COLUMNS = [
    "first_name", "last_name", "display_name", "rating", "attack_rating", "defense_rating", "rarity",
    "country", "club", "position", "collection", "quick_sell_price", "is_active",
]


async def export_players_csv(db: AsyncSession) -> str:
    result = await db.execute(select(Player).order_by(Player.id).options(joinedload(Player.collection)))
    players = result.unique().scalars().all()

    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=CSV_COLUMNS)
    writer.writeheader()
    for p in players:
        writer.writerow(
            {
                "first_name": p.first_name,
                "last_name": p.last_name,
                "display_name": p.display_name,
                "rating": p.rating,
                "attack_rating": p.attack_rating if p.attack_rating is not None else "",
                "defense_rating": p.defense_rating if p.defense_rating is not None else "",
                "rarity": p.rarity.value,
                "country": p.country,
                "club": p.club,
                "position": p.position.value,
                "collection": p.collection.name if p.collection else "",
                "quick_sell_price": p.quick_sell_price,
                "is_active": p.is_active,
            }
        )
    return buffer.getvalue()


def _parse_optional_stat(row: dict, key: str) -> int | None:
    raw = (row.get(key) or "").strip()
    return int(raw) if raw else None


async def import_players_csv(db: AsyncSession, content: str) -> dict:
    reader = csv.DictReader(io.StringIO(content))
    created, updated, errors = 0, 0, []

    for i, row in enumerate(reader, start=2):
        try:
            display_name = row["display_name"].strip()
            existing = (
                await db.execute(select(Player).where(Player.display_name == display_name))
            ).scalar_one_or_none()

            collection_name = (row.get("collection") or "").strip()
            collection_id = None
            if collection_name:
                collection = (
                    await db.execute(select(CardCollection).where(CardCollection.name == collection_name))
                ).scalar_one_or_none()
                if not collection:
                    raise ValueError(f"Unknown collection: {collection_name}")
                collection_id = collection.id

            parsed_attack = _parse_optional_stat(row, "attack_rating")
            parsed_defense = _parse_optional_stat(row, "defense_rating")

            values = dict(
                first_name=row["first_name"].strip(),
                last_name=row["last_name"].strip(),
                display_name=display_name,
                rating=int(row["rating"]),
                rarity=Rarity(row["rarity"].strip().lower()),
                country=row["country"].strip(),
                club=row["club"].strip(),
                position=Position(row["position"].strip().upper()),
                collection_id=collection_id,
                quick_sell_price=int(row.get("quick_sell_price") or 10),
                is_active=str(row.get("is_active", "true")).strip().lower() in ("true", "1", "yes"),
            )

            if existing:
                for key, value in values.items():
                    setattr(existing, key, value)
                # Blank attack/defense cells mean "leave unchanged" on update,
                # not "reset to unset" — only overwrite when a value is given.
                if parsed_attack is not None:
                    existing.attack_rating = parsed_attack
                if parsed_defense is not None:
                    existing.defense_rating = parsed_defense
                db.add(existing)
                updated += 1
            else:
                if parsed_attack is None or parsed_defense is None:
                    default_attack, default_defense = compute_default_attack_defense(values["rating"], values["position"])
                    parsed_attack = parsed_attack if parsed_attack is not None else default_attack
                    parsed_defense = parsed_defense if parsed_defense is not None else default_defense
                db.add(Player(**values, attack_rating=parsed_attack, defense_rating=parsed_defense))
                created += 1
        except Exception as exc:  # noqa: BLE001 - collect row-level errors for the admin report
            errors.append({"row": i, "error": str(exc)})

    await db.commit()
    return {"created": created, "updated": updated, "errors": errors}
