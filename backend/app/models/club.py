from datetime import datetime
from typing import Optional

from sqlalchemy import CheckConstraint, DateTime, Enum, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.enums import ClubJoinRequestStatus, ClubLogoShape, ClubRole, ClubType
from app.models.mixins import utcnow


class Club(Base):
    __tablename__ = "clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    description: Mapped[str] = mapped_column(String(512), nullable=False, default="")
    club_type: Mapped[ClubType] = mapped_column(Enum(ClubType, name="club_type_enum"), nullable=False)
    logo_shape: Mapped[ClubLogoShape] = mapped_column(
        Enum(ClubLogoShape, name="club_logo_shape_enum"), nullable=False
    )
    # Hex color string, e.g. "#3B82F6" — validated by ClubCreate/ClubUpdate schemas, not here.
    logo_color: Mapped[str] = mapped_column(String(16), nullable=False)
    captain_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    # Permanent, unique deep-link token — see club_service.join_by_invite.
    invite_code: Mapped[str] = mapped_column(String(16), unique=True, nullable=False, index=True)
    budget: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    cups_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stars_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    last_tournament_applied_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    founded_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (CheckConstraint("budget >= 0", name="ck_clubs_budget_non_negative"),)


class ClubMember(Base):
    __tablename__ = "club_members"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    # unique=True is what enforces "a user is in at most one club" at the DB level.
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True, nullable=False)
    role: Mapped[ClubRole] = mapped_column(Enum(ClubRole, name="club_role_enum"), default=ClubRole.member, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ClubJoinRequest(Base):
    __tablename__ = "club_join_requests"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[ClubJoinRequestStatus] = mapped_column(
        Enum(ClubJoinRequestStatus, name="club_join_request_status_enum"),
        default=ClubJoinRequestStatus.pending, nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)

    __table_args__ = (
        # Only one *pending* request per (club, user) — re-requesting after a
        # rejection is allowed, this just stops a duplicate pending row.
        Index(
            "uq_club_join_request_pending", "club_id", "user_id", unique=True,
            postgresql_where=text("status = 'pending'"), sqlite_where=text("status = 'pending'"),
        ),
    )
