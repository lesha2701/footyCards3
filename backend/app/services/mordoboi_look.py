"""«Выход на ринг» — how a boxer looks in «Мордобой»: gloves, shorts, an
entrance animation (Cosmetic kinds ring_gloves / ring_shorts /
ring_entrance, equipped like profile frames) and a preset nickname.
Purely visual; snapshotted into the fighter when a bout starts.

«Каска» (Cosmetic kind "helmet") lives here too: a one-shot that bounces the
winner's «Бруталити» back (mordoboi_service.apply_brutality).
"""
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.monetization import Cosmetic, UserCosmetic
from app.models.user import User

HELMET_KIND = "helmet"
SLOTS = {"gloves": "equipped_ring_gloves_id", "shorts": "equipped_ring_shorts_id", "entrance": "equipped_ring_entrance_id"}

NICKNAMES = (
    "Железный", "Бешеный", "Молот", "Танк", "Скала", "Ураган", "Зверь", "Пуля", "Кувалда",
    "Профессор", "Тихий ужас", "Малыш", "Граф", "Шаман", "Мясник", "Нокаутёр", "Гроза района",
    "Бетон", "Кобра", "Бульдозер",
)

# Seeded by migration 0194: (kind, style_key, name, description, coins, stars, sort).
SEED = (
    ("ring_gloves", "pink", "Розовые перчатки", "Нежно, но больно", 2000, 0, 1),
    ("ring_gloves", "steel", "Стальные перчатки", "Звенят при каждом ударе", 3000, 0, 2),
    ("ring_gloves", "toxic", "Токсичные перчатки", "Светятся ядовито-зелёным", 4000, 0, 3),
    ("ring_gloves", "fire", "Огненные перчатки", "Горят во время боя", 0, 60, 4),
    ("ring_gloves", "ice", "Ледяные перчатки", "Морозят соперника взглядом", 0, 60, 5),
    ("ring_gloves", "neon", "Неоновые перчатки", "Переливаются как вывеска", 0, 80, 6),
    ("ring_gloves", "gold", "Золотые перчатки", "Для чемпионов", 0, 120, 7),
    ("ring_shorts", "black", "Чёрные трусы", "Классика тяжеловесов", 1500, 0, 1),
    ("ring_shorts", "white", "Белые трусы", "Смело — на них видно всё", 1500, 0, 2),
    ("ring_shorts", "blue", "Синие трусы", "Синий угол ринга", 1500, 0, 3),
    ("ring_shorts", "green", "Зелёные трусы", "Цвет газона", 1500, 0, 4),
    ("ring_shorts", "gold", "Золотые трусы", "Блестят под прожекторами", 0, 80, 5),
    ("ring_shorts", "stars", "Трусы со звёздами", "Как у легенд прошлого", 0, 100, 6),
    ("ring_entrance", "confetti", "Конфетти", "Выход под дождь из конфетти", 3000, 0, 1),
    ("ring_entrance", "spotlight", "Луч прожектора", "Свет только на тебе", 5000, 0, 2),
    ("ring_entrance", "smoke", "Дым и прожектор", "Выход из клубов дыма", 0, 100, 3),
    ("ring_entrance", "fireworks", "Фейерверк", "Салют в твою честь", 0, 150, 4),
    ("ring_entrance", "lightning", "Молнии", "Разряды по канатам ринга", 0, 150, 5),
    ("helmet", "helmet", "Каска", "Один раз отражает чужое бруталити обратно в победителя", 2000, 30, 1),
)


async def look_for(db: AsyncSession, user: User) -> dict:
    """{nickname, gloves, shorts, entrance} — style keys of what's equipped."""
    ids = {name: getattr(user, slot) for name, slot in SLOTS.items() if getattr(user, slot)}
    styles: dict[int, str] = {}
    if ids:
        rows = await db.execute(select(Cosmetic.id, Cosmetic.style_key).where(Cosmetic.id.in_(ids.values())))
        styles = dict(rows.all())
    look = {name: styles.get(cid) for name, cid in ids.items()}
    look["nickname"] = user.mordoboi_nickname
    return look


async def helmet_of(db: AsyncSession, user_id: int) -> Optional[UserCosmetic]:
    """The user's «Каска», if they own one (the row, so it can be used up)."""
    result = await db.execute(
        select(UserCosmetic).join(Cosmetic, Cosmetic.id == UserCosmetic.cosmetic_id)
        .where(UserCosmetic.user_id == user_id, Cosmetic.kind == HELMET_KIND).limit(1)
    )
    return result.scalars().first()
