from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, DateTime, ForeignKey, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ManagerFilial(Base):
    """«Филиал академии» of a «Менеджер» club (manager_filial): one per
    club, in a region of the world (`region`; `country` is where the
    president put it — the look only). `levels` = {building: level};
    `last_release_key` = the season key of the last «выпуск»; `pending` =
    the candidates of the release waiting for the president's pick;
    `sold_key` = the season of the last sale to the market (one a season)."""

    __tablename__ = "manager_filials"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, unique=True)
    region: Mapped[str] = mapped_column(String(24), nullable=False)
    country: Mapped[str] = mapped_column(String(32), nullable=False, default="")
    levels: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    last_release_key: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    pending: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    sold_key: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerAlumnus(Base):
    """A footballer of a «Филиал академии»: comes at `start_age` in the
    season `joined_key` and gets a year older every season (1 season = 1
    year); his rating follows the career curve to `peak` at `peak_age`,
    holds, then declines; he retires at `retire_age`. `club_id` = the club
    he plays for now (a buyer's too); `status` club / retired / released /
    sold (to the market). `price` = the asking price while listed for
    other presidents."""

    __tablename__ = "manager_alumni"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    filial_id: Mapped[int] = mapped_column(ForeignKey("manager_filials.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manager_clubs.id", ondelete="SET NULL"), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(48), nullable=False)
    country: Mapped[str] = mapped_column(String(32), nullable=False)
    position: Mapped[str] = mapped_column(String(4), nullable=False)
    potential: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    peak: Mapped[int] = mapped_column(Integer, nullable=False)
    peak_age: Mapped[int] = mapped_column(Integer, nullable=False)
    decline_age: Mapped[int] = mapped_column(Integer, nullable=False)
    retire_age: Mapped[int] = mapped_column(Integer, nullable=False)
    start_age: Mapped[int] = mapped_column(Integer, nullable=False, default=17)
    joined_key: Mapped[str] = mapped_column(String(10), nullable=False)
    status: Mapped[str] = mapped_column(String(12), nullable=False, default="club")
    price: Mapped[Optional[int]] = mapped_column(BigInteger, nullable=True)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerAlumniTrade(Base):
    """A sale of an alumnus between two presidents — the guard against
    dumping between friends or one's own second account: the same pair of
    clubs trades again only after `filial_pair_cooldown_seasons`."""

    __tablename__ = "manager_alumni_trades"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    alumnus_id: Mapped[int] = mapped_column(ForeignKey("manager_alumni.id", ondelete="CASCADE"), nullable=False, index=True)
    seller_club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    buyer_club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
