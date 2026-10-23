"""monetization: login calendar, club pass, season pass, starter offer, cosmetics

Revision ID: 0154
Revises: 0153
Create Date: 2026-10-16

- login_calendar_days (+ bonus claims): the monthly login calendar that
  replaces the 7-day daily streak; claims stay in daily_rewards, which gets
  claim_method (login / coins / stars catch-up).
- club_subscriptions: «Клубный абонемент» (Telegram Stars subscription).
- seasons / season_levels / season_progress / season_claims: «Сезонный пропуск».
- starter_offer_purchases + users.starter_offer_seen_at: the one-time starter offer.
- cosmetics / user_cosmetics + users.equipped_*_id: visual-only items.
- stars_invoices.shop_product: Stars purchases of all of the above.
- game_config: every price/reward of the above, editable in the admin panel.
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0154"
down_revision: Union[str, None] = "0153"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

NEW_TX_TYPES = (
    "calendar_catchup", "cosmetic_purchase", "club_pass_reward", "season_pass_reward", "starter_offer_reward",
)


def _reward_slot(prefix: str = "") -> list[sa.Column]:
    return [
        sa.Column(f"{prefix}coins", sa.Integer(), nullable=False, server_default="0"),
        sa.Column(f"{prefix}pack_id", sa.Integer(), sa.ForeignKey("packs.id", ondelete="SET NULL"), nullable=True),
        sa.Column(f"{prefix}card_rarity", sa.String(16), nullable=True),
        sa.Column(f"{prefix}badge_id", sa.Integer(), sa.ForeignKey("badges.id", ondelete="SET NULL"), nullable=True),
        sa.Column(
            f"{prefix}cosmetic_id", sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True,
        ),
    ]


def upgrade() -> None:
    for value in NEW_TX_TYPES:
        op.execute(f"ALTER TYPE transaction_type_enum ADD VALUE IF NOT EXISTS '{value}'")

    op.create_table(
        "cosmetics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("kind", sa.String(32), nullable=False),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("description", sa.String(255), nullable=True),
        sa.Column("style_key", sa.String(32), nullable=False),
        sa.Column("coins_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("stars_price", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_exclusive", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("sort_order", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "kind IN ('profile_frame', 'profile_background', 'card_skin')", name="ck_cosmetics_kind"
        ),
    )
    op.create_table(
        "user_cosmetics",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("cosmetic_id", sa.Integer(), sa.ForeignKey("cosmetics.id", ondelete="CASCADE"), nullable=False),
        sa.Column("source", sa.String(32), nullable=False),
        sa.Column("granted_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "cosmetic_id", name="uq_user_cosmetic"),
    )
    op.create_index("ix_user_cosmetics_user_id", "user_cosmetics", ["user_id"])
    for col in ("equipped_frame_id", "equipped_background_id", "equipped_card_skin_id"):
        op.add_column("users", sa.Column(col, sa.Integer(), nullable=True))
        op.create_foreign_key(f"fk_users_{col}", "users", "cosmetics", [col], ["id"], ondelete="SET NULL")
    op.add_column("users", sa.Column("starter_offer_seen_at", sa.DateTime(timezone=True), nullable=True))

    op.create_table(
        "login_calendar_days",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("day", sa.Integer(), nullable=False, unique=True),
        *_reward_slot(),
        sa.CheckConstraint("day BETWEEN 0 AND 31", name="ck_login_calendar_day"),
    )
    op.create_table(
        "login_calendar_bonus_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "month", name="uq_login_calendar_bonus_user_month"),
    )
    op.create_index("ix_login_calendar_bonus_claims_user_id", "login_calendar_bonus_claims", ["user_id"])
    op.add_column(
        "daily_rewards", sa.Column("claim_method", sa.String(8), nullable=False, server_default="login"),
    )

    op.create_table(
        "club_subscriptions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("auto_renew", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("telegram_charge_id", sa.String(255), nullable=True),
        sa.Column("payments", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("last_daily_claim", sa.Date(), nullable=True),
        sa.Column("perks_granted", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        "seasons",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("name", sa.String(64), nullable=False),
        sa.Column("starts_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ends_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("premium_stars", sa.Integer(), nullable=False, server_default="399"),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.true()),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "season_levels",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level", sa.Integer(), nullable=False),
        sa.Column("xp_required", sa.Integer(), nullable=False),
        *_reward_slot("free_"),
        *_reward_slot("premium_"),
        sa.UniqueConstraint("season_id", "level", name="uq_season_level"),
    )
    op.create_index("ix_season_levels_season_id", "season_levels", ["season_id"])
    op.create_table(
        "season_progress",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("season_id", sa.Integer(), sa.ForeignKey("seasons.id", ondelete="CASCADE"), nullable=False),
        sa.Column("xp", sa.Integer(), nullable=False, server_default="0"),
        sa.Column("is_premium", sa.Boolean(), nullable=False, server_default=sa.false()),
        sa.Column("premium_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("user_id", "season_id", name="uq_season_progress_user"),
    )
    op.create_index("ix_season_progress_user_id", "season_progress", ["user_id"])
    op.create_index("ix_season_progress_season_id", "season_progress", ["season_id"])
    op.create_table(
        "season_claims",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("level_id", sa.Integer(), sa.ForeignKey("season_levels.id", ondelete="CASCADE"), nullable=False),
        sa.Column("track", sa.String(8), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.UniqueConstraint("user_id", "level_id", "track", name="uq_season_claim"),
        sa.CheckConstraint("track IN ('free', 'premium')", name="ck_season_claim_track"),
    )
    op.create_index("ix_season_claims_user_id", "season_claims", ["user_id"])

    op.create_table(
        "starter_offer_purchases",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("user_id", sa.Integer(), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("stars_amount", sa.Integer(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.add_column("stars_invoices", sa.Column("shop_product", sa.String(64), nullable=True))

    config_columns = [
        ("calendar_catchup_coins", sa.Integer(), "150"),
        ("calendar_catchup_stars", sa.Integer(), "10"),
        ("calendar_catchup_max_per_month", sa.Integer(), "5"),
        ("club_pass_enabled", sa.Boolean(), sa.true()),
        ("club_pass_stars", sa.Integer(), "199"),
        ("club_pass_daily_coins", sa.Integer(), "150"),
        ("club_pass_extra_rewarded_attempts", sa.Integer(), "1"),
        ("club_pass_ad_free", sa.Boolean(), sa.true()),
        ("season_pass_enabled", sa.Boolean(), sa.true()),
        ("season_xp_per_game", sa.Integer(), "10"),
        ("season_xp_per_daily_claim", sa.Integer(), "25"),
        ("starter_offer_enabled", sa.Boolean(), sa.true()),
        ("starter_offer_hours", sa.Integer(), "48"),
        ("starter_offer_stars", sa.Integer(), "50"),
        ("starter_offer_coins", sa.Integer(), "1000"),
    ]
    for name, type_, default in config_columns:
        op.add_column("game_config", sa.Column(name, type_, nullable=False, server_default=default))
    for name in ("club_pass_daily_pack_id", "club_pass_frame_cosmetic_id", "club_pass_badge_id",
                 "starter_offer_pack_id", "starter_offer_cosmetic_id"):
        op.add_column("game_config", sa.Column(name, sa.Integer(), nullable=True))

    # Starter content: a few cosmetics to sell, plus the exclusive frames the
    # club pass and the starter offer grant (wired into game_config).
    op.execute(
        """
        INSERT INTO cosmetics (kind, name, description, style_key, coins_price, stars_price, is_exclusive, sort_order)
        VALUES
          ('profile_frame', 'Золотая рамка', 'Золотая рамка аватара', 'gold', 5000, 25, false, 1),
          ('profile_frame', 'Неоновая рамка', 'Светящаяся рамка аватара', 'neon', 9000, 45, false, 2),
          ('profile_frame', 'Огненная рамка', 'Рамка аватара в огне', 'fire', 0, 75, false, 3),
          ('profile_frame', 'Рамка абонемента', 'Только для владельцев клубного абонемента', 'club_pass', 0, 0, true, 10),
          ('profile_frame', 'Рамка новичка', 'Из стартового предложения', 'starter', 0, 0, true, 11),
          ('profile_background', 'Ночной стадион', 'Фон профиля: стадион под прожекторами', 'stadium_night', 4000, 20, false, 1),
          ('profile_background', 'Изумрудный газон', 'Фон профиля: свежий газон', 'pitch', 3000, 15, false, 2),
          ('profile_background', 'Закат', 'Фон профиля: тёплый закат', 'sunset', 0, 35, false, 3),
          ('card_skin', 'Скин «Хром»', 'Хромированная рамка твоих карточек', 'chrome', 6000, 40, false, 1),
          ('card_skin', 'Скин «Голограмма»', 'Переливающаяся рамка твоих карточек', 'holo', 0, 90, false, 2)
        """
    )
    op.execute(
        """
        UPDATE game_config SET
          club_pass_frame_cosmetic_id = (SELECT id FROM cosmetics WHERE style_key = 'club_pass' LIMIT 1),
          starter_offer_cosmetic_id = (SELECT id FROM cosmetics WHERE style_key = 'starter' LIMIT 1),
          starter_offer_pack_id = (SELECT id FROM packs WHERE slug = 'premium' LIMIT 1),
          club_pass_daily_pack_id = (SELECT id FROM packs WHERE slug = 'basic' LIMIT 1)
        """
    )


def downgrade() -> None:
    for name in ("club_pass_daily_pack_id", "club_pass_frame_cosmetic_id", "club_pass_badge_id",
                 "starter_offer_pack_id", "starter_offer_cosmetic_id", "calendar_catchup_coins",
                 "calendar_catchup_stars", "calendar_catchup_max_per_month", "club_pass_enabled", "club_pass_stars",
                 "club_pass_daily_coins", "club_pass_extra_rewarded_attempts", "club_pass_ad_free",
                 "season_pass_enabled", "season_xp_per_game", "season_xp_per_daily_claim", "starter_offer_enabled",
                 "starter_offer_hours", "starter_offer_stars", "starter_offer_coins"):
        op.drop_column("game_config", name)
    op.drop_column("stars_invoices", "shop_product")
    op.drop_table("starter_offer_purchases")
    op.drop_table("season_claims")
    op.drop_table("season_progress")
    op.drop_table("season_levels")
    op.drop_table("seasons")
    op.drop_table("club_subscriptions")
    op.drop_column("daily_rewards", "claim_method")
    op.drop_table("login_calendar_bonus_claims")
    op.drop_table("login_calendar_days")
    op.drop_column("users", "starter_offer_seen_at")
    for col in ("equipped_frame_id", "equipped_background_id", "equipped_card_skin_id"):
        op.drop_constraint(f"fk_users_{col}", "users", type_="foreignkey")
        op.drop_column("users", col)
    op.drop_table("user_cosmetics")
    op.drop_table("cosmetics")
    # Postgres can't drop enum values; the new transaction types stay.
