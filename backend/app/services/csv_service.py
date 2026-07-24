import csv
import io

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import joinedload

from app.models.card_collection import CardCollection
from app.models.enums import Position, Rarity
from app.models.player import Player

CSV_COLUMNS = [
    "first_name", "last_name", "display_name", "rating", "rarity",
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
                db.add(existing)
                updated += 1
            else:
                db.add(Player(**values))
                created += 1
        except Exception as exc:  # noqa: BLE001 - collect row-level errors for the admin report
            errors.append({"row": i, "error": str(exc)})

    await db.commit()
    return {"created": created, "updated": updated, "errors": errors}
