"""Loyalty keepsakes (services/loyalty_service.py):

- «Франц Беккенбауэр · Центурион» — a legendary card that never drops from a
  pack: only for 100 days in a row (streak_rewards, bound to the player
  forever), with the purple badge «Центурион»; players who reached 100 days
  before it existed get it on their next visit (loyalty_rewards
  "centurion");
- «Старожил» (100 days in the game, 50 active days): the green badge, a
  profile frame, a legendary card and the anniversary pack;
- «Основатель» (the first 100 players): a badge and a gold profile frame;
- «Путь к Центуриону»: milestones 30 and 60 added to streak_rewards when the
  admin hasn't set them;
- «Страховка серии»: users.streak_saved_value / _until / streak_save_free_used_at.

Downgrade drops the schema only; the player, badges and frames stay.

Revision ID: 0272
Revises: 0271
Create Date: 2026-11-09
"""
import json
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0272"
down_revision: Union[str, None] = "0271"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BADGES = {
    # key: (name, icon, image, sort)
    "centurion": ("Центурион", "💜", "badges/centurion_100.svg", 954),
    "oldtimer": ("Старожил", "💚", "badges/oldtimer_100.svg", 955),
    "founder": ("Основатель", "🏛️", "badges/founder.svg", 956),
}
FRAMES = {
    "oldtimer": ("Старожил", "100 дней в VICTOR FC — живой и активный", "oldtimer", 957),
    "founder": ("Основатель", "Один из первых 100 игроков VICTOR FC", "founder", 958),
}
# Added to the «дней подряд» ladder only when the admin has no such step.
PATH_STEPS = [
    {"days": 30, "coins": 3000, "pack_id": None, "card_rarity": "epic", "badge_id": None, "cosmetic_id": None},
    {"days": 60, "coins": 8000, "pack_id": None, "card_rarity": "epic", "badge_id": None, "cosmetic_id": None},
]


def upgrade() -> None:
    op.create_table(
        "loyalty_rewards",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("code", sa.String(32), nullable=False),
        sa.Column("rewards", sa.JSON(), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("seen_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "code", name="uq_loyalty_rewards_user_code"),
    )
    op.create_index("ix_loyalty_rewards_user_id", "loyalty_rewards", ["user_id"])
    op.add_column("users", sa.Column("streak_saved_value", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("streak_saved_until", sa.DateTime(timezone=True), nullable=True))
    op.add_column("users", sa.Column("streak_save_free_used_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("game_config", sa.Column("loyalty_settings", sa.JSON(), nullable=False, server_default="{}"))

    conn = op.get_bind()
    ids: dict[str, int] = {}
    for key, (name, icon, image, sort) in BADGES.items():
        found = conn.execute(sa.text("SELECT id FROM badges WHERE name = :n"), {"n": name}).scalar()
        ids[f"{key}_badge_id"] = found or conn.execute(sa.text(
            "INSERT INTO badges (name, icon, image_path, is_active, sort_order, created_at, updated_at) "
            "VALUES (:n, :icon, :img, true, :sort, now(), now()) RETURNING id"
        ), {"n": name, "icon": icon, "img": image, "sort": sort}).scalar_one()
    for key, (name, description, style, sort) in FRAMES.items():
        found = conn.execute(sa.text(
            "SELECT id FROM cosmetics WHERE kind = 'profile_frame' AND style_key = :s"
        ), {"s": style}).scalar()
        ids[f"{key}_cosmetic_id"] = found or conn.execute(sa.text(
            "INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, "
            "is_active, sort_order, status, win_bonus_coins, created_at, updated_at) "
            "VALUES ('profile_frame', :name, :description, :style, 0, 0, true, true, :sort, 0, 0, now(), now()) "
            "RETURNING id"
        ), {"name": name, "description": description, "style": style, "sort": sort}).scalar_one()

    player_id = conn.execute(sa.text(
        "SELECT id FROM players WHERE display_name = 'Франц Беккенбауэр · Центурион'"
    )).scalar()
    if player_id is None:
        # No photo yet (image_path NULL = the placeholder); is_pack_droppable
        # false keeps it out of packs, the wheel and random card rewards.
        player_id = conn.execute(sa.text(
            "INSERT INTO players (first_name, last_name, display_name, rating, attack_rating, defense_rating, "
            "rarity, country, club, position, image_path, quick_sell_price, is_active, is_pack_droppable, "
            "next_serial_number, next_club_serial_number, created_at, updated_at) "
            "VALUES ('Франц', 'Беккенбауэр', 'Франц Беккенбауэр · Центурион', 95, 86, 97, "
            "CAST('legendary' AS rarity_enum), 'Германия', 'Бавария', CAST('CB' AS position_enum), NULL, 400, "
            "true, false, 1, 1, now(), now()) RETURNING id"
        )).scalar_one()
    ids["centurion_player_id"] = player_id
    conn.execute(sa.text("UPDATE game_config SET loyalty_settings = CAST(:s AS JSON) WHERE id = 1"),
                 {"s": json.dumps(ids)})

    # The ladder: 100 days = the Centurion card + the purple badge (coins
    # kept, the random legendary gives way to the exclusive card), plus the
    # path steps 30 / 60.
    raw = conn.execute(sa.text("SELECT streak_rewards FROM game_config WHERE id = 1")).scalar()
    if raw is None:
        return
    ladder = json.loads(raw) if isinstance(raw, str) else list(raw or [])
    days = {row.get("days") for row in ladder}
    ladder.extend(dict(step) for step in PATH_STEPS if step["days"] not in days)
    hundred = next((row for row in ladder if row.get("days") == 100), None)
    if hundred is None:
        hundred = {"days": 100, "coins": 25000, "pack_id": None, "cosmetic_id": None}
        ladder.append(hundred)
    hundred.update(player_id=player_id, badge_id=ids["centurion_badge_id"], card_rarity=None)
    ladder.sort(key=lambda row: row["days"])
    conn.execute(sa.text("UPDATE game_config SET streak_rewards = CAST(:r AS JSON) WHERE id = 1"),
                 {"r": json.dumps(ladder)})


def downgrade() -> None:
    op.drop_column("game_config", "loyalty_settings")
    op.drop_column("users", "streak_save_free_used_at")
    op.drop_column("users", "streak_saved_until")
    op.drop_column("users", "streak_saved_value")
    op.drop_index("ix_loyalty_rewards_user_id", table_name="loyalty_rewards")
    op.drop_table("loyalty_rewards")
