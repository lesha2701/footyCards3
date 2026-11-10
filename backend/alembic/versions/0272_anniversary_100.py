"""«💯 Нам 100 дней!»: the community goal and calendar (anniversary_members /
anniversary_claims), the event switch, dates and numbers on game_config, the
badge «100 дней» (the calendar's last gift), an empty, inactive collection
«Клуб Центурионов» with the gold frame (card_skin 'gold100') — legends with
100+ caps, filled when their art is ready — its completion badge (new
card_collections.reward_badge_id) and «Юбилейный пак» (3 cards of that
collection, granted by the calendar and the community goal, never sold).

The event is switched on with its dates (21.11 – 30.11 Moscow, right after
«Битва фанатов»): it starts by itself at midnight of the 21st.

Revision ID: 0272
Revises: 0271
Create Date: 2026-11-02
"""
import json
from datetime import datetime, timedelta, timezone
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0272"
down_revision: Union[str, None] = "0271"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

# Real datetimes: asyncpg refuses a string for a timestamptz parameter.
_MSK = timezone(timedelta(hours=3))
STARTS_AT = datetime(2026, 11, 21, tzinfo=_MSK)
ENDS_AT = datetime(2026, 12, 1, tzinfo=_MSK)
BADGE = "100 дней"
COLLECTION = "Клуб Центурионов"
COLLECTION_BADGE = "Клуб Центурионов"
PACK_SLUG = "anniversary-100"
PACK_ODDS = (("rare", "0.55"), ("epic", "0.35"), ("legendary", "0.10"))


def upgrade() -> None:
    op.execute("ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS 'anniversary_reward'")

    op.add_column("game_config", sa.Column("anniversary_enabled", sa.Boolean(), nullable=False, server_default=sa.false()))
    op.add_column("game_config", sa.Column("anniversary_starts_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("anniversary_ends_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("anniversary_settings", sa.JSON(), nullable=False, server_default="{}"))

    op.create_table(
        "anniversary_members",
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("event_key", sa.String(32), primary_key=True),
        sa.Column("games", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calendar_claimed", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("calendar_last_day", sa.String(10), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "anniversary_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("event_key", sa.String(32), nullable=False),
        sa.Column("kind", sa.String(16), nullable=False),
        sa.Column("ref_key", sa.String(96), nullable=False),
        sa.Column("details", sa.JSON(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "ref_key", name="uq_anniversary_claims_user_ref"),
    )
    op.create_index("ix_anniversary_claims_user_id", "anniversary_claims", ["user_id"])

    conn = op.get_bind()
    badge_id = conn.execute(sa.text("SELECT id FROM badges WHERE name = :n"), {"n": BADGE}).scalar()
    if badge_id is None:
        badge_id = conn.execute(sa.text(
            "INSERT INTO badges (name, icon, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, '💯', true, 920, now(), now()) RETURNING id"
        ), {"n": BADGE}).scalar_one()
    # The medal art (static/badges/) unless an admin uploaded another one.
    conn.execute(sa.text(
        "UPDATE badges SET image_path = 'badges/anniversary_100.webp' WHERE id = :id AND image_path IS NULL"
    ), {"id": badge_id})
    # A collection can also award a badge when it's complete.
    op.add_column("card_collections", sa.Column(
        "reward_badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True,
    ))
    club_badge_id = conn.execute(sa.text("SELECT id FROM badges WHERE name = :n"), {"n": COLLECTION_BADGE}).scalar()
    if club_badge_id is None:
        club_badge_id = conn.execute(sa.text(
            "INSERT INTO badges (name, icon, image_path, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, '🏛️', 'badges/centurions_club.webp', true, 921, now(), now()) RETURNING id"
        ), {"n": COLLECTION_BADGE}).scalar_one()
    collection_id = conn.execute(sa.text("SELECT id FROM card_collections WHERE name = :n"), {"n": COLLECTION}).scalar()
    if collection_id is None:
        collection_id = conn.execute(sa.text(
            "INSERT INTO card_collections (name, description, is_active, sort_order, reward_coins, reward_badge_id, "
            "card_skin, created_at, updated_at) VALUES (:n, :d, false, 920, 5000, :b, 'gold100', now(), now()) "
            "RETURNING id"
        ), {"n": COLLECTION, "b": club_badge_id,
            "d": "Легенды, сыгравшие 100+ матчей за сборную, — в доспехах центурионов и золотой рамке. "
                 "Только из юбилейного пака."}).scalar_one()

    pack_id = conn.execute(sa.text(
        "INSERT INTO packs (slug, name, description, price, card_count, guaranteed_min_rarity, image_path, is_active, "
        "sort_order, pity_enabled, coach_drop_chance, stadium_drop_chance, skill_token_drop_chance, player_pool, "
        "muse_drop_chance, created_at, updated_at) "
        "VALUES (:slug, 'Юбилейный пак', :descr, 2500, 3, 'rare', 'packs/anniversary.webp', false, -10, false, "
        "0, 0, 0, :pool, 0, now(), now()) ON CONFLICT (slug) DO NOTHING RETURNING id"
    ), {"slug": PACK_SLUG, "pool": f"collection:{collection_id}",
        "descr": "Подарок к 100 дням Victor FC: 3 карточки коллекции «Клуб Центурионов» в золотой рамке."}).scalar()
    if pack_id is not None:
        for rarity, prob in PACK_ODDS:
            conn.execute(sa.text(
                "INSERT INTO pack_rarity_probabilities (pack_id, rarity, probability) "
                "VALUES (:p, CAST(:r AS rarity_enum), CAST(:prob AS NUMERIC))"
            ), {"p": pack_id, "r": rarity, "prob": prob})
    else:
        pack_id = conn.execute(sa.text("SELECT id FROM packs WHERE slug = :s"), {"s": PACK_SLUG}).scalar_one()

    conn.execute(sa.text(
        "UPDATE game_config SET anniversary_enabled = true, anniversary_starts_at = :start, "
        "anniversary_ends_at = :end, anniversary_settings = CAST(:settings AS JSON) WHERE id = 1"
    ), {"start": STARTS_AT, "end": ENDS_AT, "settings": json.dumps(
        {"badge_id": badge_id, "collection_id": collection_id, "pack_id": pack_id})})


def downgrade() -> None:
    op.drop_column("card_collections", "reward_badge_id")
    op.drop_index("ix_anniversary_claims_user_id", table_name="anniversary_claims")
    op.drop_table("anniversary_claims")
    op.drop_table("anniversary_members")
    op.drop_column("game_config", "anniversary_settings")
    op.drop_column("game_config", "anniversary_ends_at")
    op.drop_column("game_config", "anniversary_starts_at")
    op.drop_column("game_config", "anniversary_enabled")
