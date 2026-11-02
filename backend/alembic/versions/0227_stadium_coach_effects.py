"""Stadiums and coaches against the opponent, their collections, Stars sales.

- coach_boost_type_enum: team_rating (+N to the own XI) and opp_attack /
  opp_defence / opp_goalkeeping / opp_team (−N to the opponent) — Card Arena.
- stadiums.opp_malus: −N rating to every opponent player (Card Arena).
- stadiums / coaches.collection_id: they can belong to a card collection.
- card_offers: a coach, a stadium or a Muse can be sold for Stars too
  (player_id becomes optional, exactly one of the four is set).
- Two cards: «Проклятый стадион» (−5 to the opponent) and the legendary
  coach Жозе Моуриньо (dark arts: −4 to the opponent's attack, −2 to all of
  them, +8 to his central defence in tournaments), in the «Ночь живых
  Легенд» collection when it exists.

Revision ID: 0227
Revises: 0226
Create Date: 2026-10-31
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0227"
down_revision: Union[str, None] = "0226"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_BOOSTS = ("team_rating", "opp_attack", "opp_defence", "opp_goalkeeping", "opp_team")


def upgrade() -> None:
    # A new enum value can't be used in the transaction that adds it.
    with op.get_context().autocommit_block():
        for value in NEW_BOOSTS:
            op.execute(f"ALTER TYPE coach_boost_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.add_column("stadiums", sa.Column("opp_malus", sa.Integer(), nullable=False, server_default="0"))
    for table in ("stadiums", "coaches"):
        op.add_column(table, sa.Column(
            "collection_id", sa.Integer(), sa.ForeignKey("card_collections.id", ondelete="SET NULL"), nullable=True,
        ))
        op.create_index(f"ix_{table}_collection_id", table, ["collection_id"])

    op.alter_column("card_offers", "player_id", existing_type=sa.Integer(), nullable=True)
    op.add_column("card_offers", sa.Column("coach_id", sa.Integer(), sa.ForeignKey("coaches.id", ondelete="CASCADE"), nullable=True))
    op.add_column("card_offers", sa.Column("stadium_id", sa.Integer(), sa.ForeignKey("stadiums.id", ondelete="CASCADE"), nullable=True))
    op.add_column("card_offers", sa.Column("muse_id", sa.Integer(), sa.ForeignKey("muses.id", ondelete="CASCADE"), nullable=True))
    op.create_check_constraint(
        "ck_card_offers_one_item", "card_offers",
        "(player_id IS NOT NULL)::int + (coach_id IS NOT NULL)::int + (stadium_id IS NOT NULL)::int "
        "+ (muse_id IS NOT NULL)::int = 1",
    )

    bind = op.get_bind()
    collection_id = bind.execute(sa.text(
        "SELECT id FROM card_collections WHERE name ILIKE '%ночь живых%' ORDER BY id LIMIT 1"
    )).scalar()
    if not bind.execute(sa.text("SELECT 1 FROM stadiums WHERE display_name = 'Проклятый стадион'")).first():
        bind.execute(sa.text(
            "INSERT INTO stadiums (display_name, rarity, image_path, club, quick_sell_price, is_active, is_pack_droppable, "
            "next_serial_number, next_club_serial_number, boost_pct, opp_malus, collection_id, created_at, updated_at) "
            "VALUES ('Проклятый стадион', 'legendary', NULL, NULL, 500, true, true, "
            "1, 1, 0, 5, :collection, now(), now())"
        ), {"collection": collection_id})
    if not bind.execute(sa.text("SELECT 1 FROM coaches WHERE display_name = 'Жозе Моуриньо'")).first():
        coach_id = bind.execute(sa.text(
            "INSERT INTO coaches (display_name, rarity, image_path, country, quick_sell_price, is_active, is_pack_droppable, "
            "next_serial_number, next_club_serial_number, collection_id, created_at, updated_at) "
            "VALUES ('Жозе Моуриньо', 'legendary', 'coaches/legendary/mourinho.webp', 'Португалия', 500, true, true, "
            "1, 1, :collection, now(), now()) RETURNING id"
        ), {"collection": collection_id}).scalar_one()
        # legendary = tier 4 (coach_service.magnitude_for): 1×4, 0.5×4, 2×4.
        for boost_type, magnitude in (("opp_attack", 4), ("opp_team", 2), ("defence_central", 8)):
            bind.execute(sa.text(
                "INSERT INTO coach_boosts (coach_id, boost_type, magnitude) VALUES (:coach, CAST(:type AS coach_boost_type_enum), :m)"
            ), {"coach": coach_id, "type": boost_type, "m": magnitude})


def downgrade() -> None:
    op.execute("DELETE FROM coaches WHERE display_name = 'Жозе Моуриньо' AND next_serial_number = 1")
    op.execute("DELETE FROM stadiums WHERE display_name = 'Проклятый стадион' AND next_serial_number = 1")
    op.execute("DELETE FROM card_offers WHERE player_id IS NULL")
    op.drop_constraint("ck_card_offers_one_item", "card_offers", type_="check")
    for column in ("muse_id", "stadium_id", "coach_id"):
        op.drop_column("card_offers", column)
    op.alter_column("card_offers", "player_id", existing_type=sa.Integer(), nullable=False)
    for table in ("coaches", "stadiums"):
        op.drop_index(f"ix_{table}_collection_id", table_name=table)
        op.drop_column(table, "collection_id")
    op.drop_column("stadiums", "opp_malus")
    # Enum values stay (Postgres can't drop them); nothing uses them any more.
