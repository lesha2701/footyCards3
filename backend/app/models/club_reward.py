"""Club-wide rewards each member claims for themselves (club_reward_service):
bought in the «Клубный магазин» (`ClubShopItem` / `ClubShopPurchase`),
earned by a completed weekly club quest or a won club war. A grant's
reward is a reward bundle (reward_bundle_service) — coins, a pack, a card
of a rarity, a badge and/or a cosmetic — per member."""
from datetime import date, datetime
from typing import Optional

from sqlalchemy import Boolean, Date, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ClubRewardGrant(Base):
    __tablename__ = "club_reward_grants"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    # "shop" | "quest" | "war"
    source: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    title: Mapped[str] = mapped_column(String(128), nullable=False)
    coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    cosmetic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    __table_args__ = (Index("ix_club_reward_grants_club_id_expires", "club_id", "expires_at"),)


class ClubRewardClaim(Base):
    __tablename__ = "club_reward_claims"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    grant_id: Mapped[int] = mapped_column(ForeignKey("club_reward_grants.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (UniqueConstraint("grant_id", "user_id", name="uq_club_reward_claims_grant_user"),)


class ClubShopItem(Base):
    """«Клубный магазин»: the club spends its budget, every member gets the
    reward bundle. Limited per club per week."""
    __tablename__ = "club_shop_items"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    description: Mapped[str] = mapped_column(String(256), nullable=False, default="")
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    weekly_limit: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    reward_pack_id: Mapped[Optional[int]] = mapped_column(ForeignKey("packs.id", ondelete="SET NULL"), nullable=True)
    reward_card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True)
    reward_badge_id: Mapped[Optional[int]] = mapped_column(ForeignKey("badges.id", ondelete="SET NULL"), nullable=True)
    reward_cosmetic_id: Mapped[Optional[int]] = mapped_column(ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)


class ClubShopPurchase(Base):
    __tablename__ = "club_shop_purchases"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False)
    item_id: Mapped[int] = mapped_column(ForeignKey("club_shop_items.id", ondelete="CASCADE"), nullable=False)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    week_start: Mapped[date] = mapped_column(Date, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (Index("ix_club_shop_purchases_club_week", "club_id", "week_start"),)
