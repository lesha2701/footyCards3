"""«Экипировка», part 2: new effects (save / tackle / pass, «Академия»
experience and Arena win coins), limited editions with serial numbers,
seasonal sale windows, the national-team set bonus for the whole squad, and
a bigger seeded catalog (all editable in the admin panel).

Revision ID: 0185
Revises: 0184
Create Date: 2026-10-20

"""
from datetime import datetime, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0185"
down_revision: Union[str, None] = "0184"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

WINTER_UNTIL = datetime(2027, 3, 1, tzinfo=timezone.utc)

# key: (name, description, set_size, set_bonus_rating, team_country, team_chemistry, is_active, sort)
COLLECTIONS = {
    "street": ("Улица", "Дворовый футбол: кеды, футболка и гетры — первый комплект для новичка.", 3, 1, None, 0, True, 3),
    "champion": ("Чемпионская", "Экипировка победителей: 4 вещи, полный комплект даёт +2 к рейтингу.", 4, 2, None, 0, True, 4),
    "winter": ("Зимний матч", "Сезонная коллекция для вратаря: перчатки, термобельё и шапка. Продаётся до 1 марта.", 3, 1, None, 0, True, 5),
    "brazil": ("Сборная Бразилии", "Форма, шарф и флаг «Селесао»: полный комплект даёт +1 химии всем бразильцам в составе.", 3, 0, "Бразилия", 1, True, 6),
    "italy": ("Сборная Италии", "Форма, шарф и флаг «Скуадры Адзурры»: полный комплект даёт +1 химии всем итальянцам в составе.", 3, 0, "Италия", 1, True, 7),
    "classic": ("Клубная классика", "Ретро-формы клубов: действуют только на игроков своего клуба. Укажи клуб и включи в админке.", 99, 0, None, 0, False, 8),
}
# (collection key or None, name, description, icon, slot, rarity, effect, value, coins, stars,
#  cond_club, cond_country, max_supply, until, is_active, sort)
ITEMS = [
    ("street", "Кеды «Улица»", "Потёртые кеды с асфальтовой площадки.", "👟", "boots", "common", "shot_pp", 2, 600, 0, None, None, None, None, True, 20),
    ("street", "Футболка «Улица»", "Футболка без номера — играешь в пас.", "👕", "kit", "common", "pass_pp", 2, 500, 0, None, None, None, None, True, 21),
    ("street", "Гетры «Улица»", "Гетры, спущенные до щиколоток.", "🧦", "socks", "common", "dribble_pp", 2, 500, 0, None, None, None, None, True, 22),
    ("champion", "Бутсы «Чемпион»", "Золотые шипы победителей.", "👟", "boots", "legendary", "shot_pp", 6, 12000, 250, None, None, None, None, True, 23),
    ("champion", "Форма «Чемпион»", "Форма с чемпионской нашивкой.", "👕", "kit", "legendary", "rating", 1, 14000, 280, None, None, None, None, True, 24),
    ("champion", "Гетры «Чемпион»", "Щитки и гетры, выдержавшие финал.", "🧦", "socks", "legendary", "tackle_pp", 5, 12000, 250, None, None, None, None, True, 25),
    ("champion", "Медаль «Чемпион»", "Медаль на шее заряжает всю команду.", "🏅", "accessory", "legendary", "chemistry", 1, 15000, 300, None, None, None, None, True, 26),
    ("winter", "Перчатки «Зима»", "Тёплые вратарские перчатки с цепким латексом.", "🧤", "gloves", "epic", "save_pp", 4, 3500, 70, None, None, None, "winter", True, 27),
    ("winter", "Термобельё «Зима»", "Под формой тепло — пас не дрожит.", "🧥", "kit", "epic", "pass_pp", 4, 3500, 70, None, None, None, "winter", True, 28),
    ("winter", "Шапка «Зима»", "Вратарская шапка: опыт копится быстрее.", "🧢", "accessory", "epic", "xp_pct", 10, 3000, 60, None, None, None, "winter", True, 29),
    ("brazil", "Форма «Селесао»", "Жёлтая футболка сборной Бразилии.", "👕", "kit", "epic", "chemistry", 1, 4000, 80, None, "Бразилия", None, None, True, 30),
    ("brazil", "Шарф «Селесао»", "Шарф болельщика сборной Бразилии.", "🧣", "accessory", "rare", "dribble_pp", 3, 3000, 0, None, None, None, None, True, 31),
    ("brazil", "Флаг «Селесао»", "Флаг с трибуны «Маракана».", "🚩", "artifact", "rare", "coins_pct", 5, 3000, 0, None, None, None, None, True, 32),
    ("italy", "Форма «Адзурри»", "Синяя футболка сборной Италии.", "👕", "kit", "epic", "chemistry", 1, 4000, 80, None, "Италия", None, None, True, 33),
    ("italy", "Шарф «Адзурри»", "Шарф болельщика сборной Италии.", "🧣", "accessory", "rare", "tackle_pp", 3, 3000, 0, None, None, None, None, True, 34),
    ("italy", "Флаг «Адзурри»", "Флаг с трибуны «Сан-Сиро».", "🚩", "artifact", "rare", "coins_pct", 5, 3000, 0, None, None, None, None, True, 35),
    ("classic", "Ретро-форма (клуб 1)", "Укажи клуб в админке — даст +1 к рейтингу его игрокам.", "👕", "kit", "epic", "rating", 1, 3500, 0, "Укажи клуб", None, None, None, False, 36),
    ("classic", "Ретро-форма (клуб 2)", "Укажи клуб в админке — даст +1 к рейтингу его игрокам.", "👕", "kit", "epic", "rating", 1, 3500, 0, "Укажи клуб", None, None, None, False, 37),
    (None, "Золотая бутса", "Награда лучшему бомбардиру. Тираж — 100 штук.", "🥇", "boots", "legendary", "shot_pp", 6, 0, 500, None, None, 100, None, True, 40),
    (None, "Щитки-броня", "Ни один отбор не обходится без фола? Теперь обходится.", "🛡️", "socks", "rare", "tackle_pp", 4, 2500, 0, None, None, None, None, True, 41),
    (None, "Гетры дирижёра", "Носит тот, кто раздаёт передачи.", "🎼", "socks", "rare", "pass_pp", 4, 2500, 0, None, None, None, None, True, 42),
    (None, "Кепка вратаря", "Солнце не слепит — мяч не проскочит.", "🧢", "accessory", "rare", "save_pp", 3, 2500, 0, None, None, None, None, True, 43),
    (None, "Перчатки-клей", "Мяч прилипает к рукам.", "🧤", "gloves", "epic", "save_pp", 5, 4500, 90, None, None, None, None, True, 44),
    (None, "Свисток наставника", "Талисман: +10% опыта «Академии» за матчи.", "📯", "artifact", "epic", "xp_pct", 10, 6000, 0, None, None, None, None, True, 45),
    (None, "Копилка болельщика", "Талисман: +10% монет за победу в Card Arena.", "🐷", "artifact", "epic", "coins_pct", 10, 6000, 120, None, None, None, None, True, 46),
]


def upgrade() -> None:
    op.add_column("equipment_collections", sa.Column("set_team_country", sa.String(64), nullable=True))
    op.add_column("equipment_collections", sa.Column("set_team_chemistry", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("equipment_items", sa.Column("max_supply", sa.Integer(), nullable=True))
    op.add_column("equipment_items", sa.Column("sold_count", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("equipment_items", sa.Column("available_from", sa.DateTime(timezone=True), nullable=True))
    op.add_column("equipment_items", sa.Column("available_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("user_equipment", sa.Column("serial_number", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column("equipment_max_talisman_pct", sa.Integer(), nullable=False, server_default="15"))

    bind = op.get_bind()
    collections = sa.table(
        "equipment_collections",
        sa.column("id", sa.Integer), sa.column("name", sa.String), sa.column("description", sa.String),
        sa.column("set_size", sa.Integer), sa.column("set_bonus_rating", sa.Integer),
        sa.column("set_team_country", sa.String), sa.column("set_team_chemistry", sa.Integer),
        sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    items = sa.table(
        "equipment_items",
        sa.column("name", sa.String), sa.column("description", sa.String), sa.column("icon", sa.String),
        sa.column("slot", sa.String), sa.column("rarity", sa.String), sa.column("collection_id", sa.Integer),
        sa.column("effect", sa.String), sa.column("effect_value", sa.Integer), sa.column("coins_price", sa.Integer),
        sa.column("stars_price", sa.Integer), sa.column("cond_club", sa.String), sa.column("cond_country", sa.String),
        sa.column("max_supply", sa.Integer), sa.column("available_until", sa.DateTime(timezone=True)),
        sa.column("is_active", sa.Boolean), sa.column("sort_order", sa.Integer),
    )
    ids: dict[str, int] = {}
    for key, (name, desc, size, bonus, country, team_chem, active, sort) in COLLECTIONS.items():
        bind.execute(collections.insert().values(
            name=name, description=desc, set_size=size, set_bonus_rating=bonus, set_team_country=country,
            set_team_chemistry=team_chem, is_active=active, sort_order=sort,
        ))
        ids[key] = bind.execute(sa.select(collections.c.id).where(collections.c.name == name)).scalar_one()
    for (col, name, desc, icon, slot, rarity, effect, value, coins, stars, club, country, supply, until,
         active, sort) in ITEMS:
        bind.execute(items.insert().values(
            name=name, description=desc, icon=icon, slot=slot, rarity=rarity, collection_id=ids.get(col) if col else None,
            effect=effect, effect_value=value, coins_price=coins, stars_price=stars, cond_club=club, cond_country=country,
            max_supply=supply, available_until=WINTER_UNTIL if until == "winter" else None, is_active=active,
            sort_order=sort,
        ))


def downgrade() -> None:
    bind = op.get_bind()
    names = [i[1] for i in ITEMS]
    # Owned copies of these things go with them (user_equipment.item_id ON DELETE CASCADE).
    items = sa.table("equipment_items", sa.column("name", sa.String))
    bind.execute(items.delete().where(items.c.name.in_(names)))
    collections = sa.table("equipment_collections", sa.column("name", sa.String))
    bind.execute(collections.delete().where(collections.c.name.in_([c[0] for c in COLLECTIONS.values()])))
    op.drop_column("game_config", "equipment_max_talisman_pct")
    op.drop_column("user_equipment", "serial_number")
    for name in ("available_until", "available_from", "sold_count", "max_supply"):
        op.drop_column("equipment_items", name)
    op.drop_column("equipment_collections", "set_team_chemistry")
    op.drop_column("equipment_collections", "set_team_country")
