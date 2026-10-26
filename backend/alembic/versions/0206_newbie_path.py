"""«Путь дебютанта» (newbie path): hidden packs debut / debut-team, newbie_progress, user_cards.bound_until (gift cards that
can't be traded, sold or burned for a while) and GameConfig newbie_* knobs.
newbie_since = now(): only players registered from this release walk the path.

Revision ID: 0206
Revises: 0205
Create Date: 2026-10-26
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op


revision: str = "0206"
down_revision: Union[str, None] = "0205"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# GameConfig NEWBIE_DEFAULT_TASKS as of this revision.
TASKS = [
    {'code': 'penalty', 'label': 'Сыграй в Пенальти', 'mode': 'game:penalty', 'path': '/play/penalty', 'coins': 1000},
    {'code': 'free_kick', 'label': 'Пробей Штрафной', 'mode': 'game:free_kick', 'path': '/play/free-kick', 'coins': 1000},
    {'code': 'memory', 'label': 'Пройди Memory', 'mode': 'game:memory_sequence', 'path': '/play/memory', 'coins': 1000},
    {'code': 'hangman', 'label': 'Угадай слово в «Футбольных буквах»', 'mode': 'game:football_hangman', 'path': '/play/hangman', 'coins': 1000},
    {'code': 'blackjack', 'label': 'Сыграй в «21»', 'mode': 'blackjack', 'path': '/play/blackjack', 'coins': 1000},
    {'code': 'wheel', 'label': 'Крутани Колесо фортуны', 'mode': 'wheel', 'path': '/wheel', 'coins': 1000},
]


def upgrade() -> None:
    op.execute("ALTER TYPE card_source_enum ADD VALUE IF NOT EXISTS 'newbie'")
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'newbie_reward'")

    op.add_column("user_cards", sa.Column("bound_until", sa.DateTime(timezone=True), nullable=True))
    op.create_table(
        "newbie_progress",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("start_day", sa.Date(), nullable=False),
        sa.Column("claimed", sa.JSON(), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reminded_day", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("version", sa.Integer(), nullable=False, server_default="1"),
    )
    op.create_index("ix_newbie_progress_started_at", "newbie_progress", ["started_at"])

    op.add_column("game_config", sa.Column("newbie_enabled", sa.Boolean(), nullable=False, server_default=sa.true()))
    op.add_column("game_config", sa.Column("newbie_since", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("newbie_first_pack_rarities", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("newbie_squad_rarity", sa.String(16), nullable=False, server_default="rare"))
    op.add_column("game_config", sa.Column("newbie_arena_rarity", sa.String(16), nullable=False, server_default="legendary"))
    op.add_column("game_config", sa.Column("newbie_tasks", sa.JSON(), nullable=True))
    op.add_column("game_config", sa.Column("newbie_day2_coins", sa.Integer(), nullable=False, server_default="10000"))
    op.add_column("game_config", sa.Column("newbie_day3_rarity", sa.String(16), nullable=False, server_default="legendary"))
    op.add_column("game_config", sa.Column("newbie_bound_days", sa.Integer(), nullable=False, server_default="14"))
    op.add_column("game_config", sa.Column("newbie_reminder_hour", sa.Integer(), nullable=False, server_default="12"))
    op.add_column("game_config", sa.Column("newbie_finale_coins", sa.Integer(), nullable=False, server_default="5000"))
    op.add_column("game_config", sa.Column("newbie_finale_pack_id", sa.Integer(), nullable=True))
    op.add_column("game_config", sa.Column("newbie_finale_badge_id", sa.Integer(), nullable=True))
    badge_id = op.get_bind().execute(sa.text(
        "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
        "VALUES ('Дебютант', '🎓', true, 950, now(), now()) RETURNING id"
    )).scalar_one()
    op.get_bind().execute(sa.text("UPDATE game_config SET newbie_finale_badge_id = :b"), {"b": badge_id})
    op.get_bind().execute(
        sa.text(
            "UPDATE game_config SET newbie_since = now(), newbie_first_pack_rarities = CAST(:rar AS json), "
            "newbie_tasks = CAST(:tasks AS json)"
        ),
        {"rar": json.dumps(["epic", "rare", "rare"]), "tasks": json.dumps(TASKS, ensure_ascii=False)},
    )
    # Hidden carrier packs of the path (never in the shop): the admin gives
    # them their own art in «Паки». Their cards are picked by newbie_service.
    for slug, name, count, sort in (("debut", "Пак дебютанта", 3, 900), ("debut-team", "Твоя команда", 11, 901)):
        op.get_bind().execute(sa.text(
            "INSERT INTO packs (slug, name, description, price, card_count, is_active, sort_order, "
            "coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, player_pool, muse_drop_chance, created_at, updated_at) "
            "VALUES (:slug, :name, :descr, 0, :count, false, :sort, 0, 0, 0, 'default', 0, now(), now()) "
            "ON CONFLICT (slug) DO NOTHING"
        ), {"slug": slug, "name": name, "count": count, "sort": sort,
            "descr": "Путь дебютанта: выдаётся новому игроку один раз. Не включать в продажу."})
    op.alter_column("game_config", "newbie_first_pack_rarities", nullable=False)
    op.alter_column("game_config", "newbie_tasks", nullable=False)


def downgrade() -> None:
    op.execute("DELETE FROM packs WHERE slug IN ('debut', 'debut-team') AND NOT EXISTS "
               "(SELECT 1 FROM pack_openings po WHERE po.pack_id = packs.id)")
    op.execute("DELETE FROM badges WHERE name = 'Дебютант' AND NOT EXISTS "
               "(SELECT 1 FROM user_badges ub WHERE ub.badge_id = badges.id)")
    for col in (
        "newbie_finale_badge_id", "newbie_finale_pack_id", "newbie_finale_coins", "newbie_reminder_hour",
        "newbie_bound_days", "newbie_day3_rarity", "newbie_day2_coins", "newbie_tasks", "newbie_arena_rarity",
        "newbie_squad_rarity", "newbie_first_pack_rarities", "newbie_since", "newbie_enabled",
    ):
        op.drop_column("game_config", col)
    op.drop_index("ix_newbie_progress_started_at", table_name="newbie_progress")
    op.drop_table("newbie_progress")
    op.drop_column("user_cards", "bound_until")
