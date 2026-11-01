from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint, text
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import utcnow


class ManagerClub(Base):
    """«Менеджер»: a user's own club (manager_service). Squad: the owner's
    «Мой игрок» and one «Академия» card (both always start), up to
    config.manager_max_live other users' «Мои игроки» (manager_contracts)
    and catalog footballers (manager_npc). Money is club euros (`budget`,
    BigInteger) — a season grant from the division and the «Клубная база»,
    match income, prizes, fans' merchandise; it pays fees and wages and is
    never converted to coins. `budget_season` = the season key whose grant
    was paid. `look` = emblem / kit / frame picks (manager_shop)."""

    __tablename__ = "manager_clubs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    owner_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(String(32), nullable=False)
    # Tactics (manager_tactics): one of the club formations and one of the four styles.
    formation: Mapped[str] = mapped_column(String(8), nullable=False, default="4-3-3")
    style: Mapped[str] = mapped_column(String(16), nullable=False, default="possession")
    budget: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    division: Mapped[int] = mapped_column(Integer, nullable=False, default=1, index=True)
    academy_card_id: Mapped[Optional[int]] = mapped_column(ForeignKey("user_cards.id", ondelete="SET NULL"), nullable=True)
    budget_season: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    # The league of the current (or last) season.
    league_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manager_leagues.id", ondelete="SET NULL"), nullable=True)
    seasons_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    titles: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    best_division: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    look: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    stadium_name: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    pro_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Euros fans brought this season through merchandise (capped per season).
    merch_season: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    merch_eur: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    # Supporters won by preseason tours («Кабинет президента»), on top of merchandise buyers.
    fans_bonus: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerContract(Base):
    """Another user's «Мой игрок» at a manager club.

    kind: sign (a free agent), transfer (bought from another club: `fee` in
    euros to its budget, the old contract ends), loan (one season, `fee` to
    the parent club; the old contract is `on_loan` meanwhile and comes
    back). An offer needs the player's consent (`player_agreed`) and, for
    transfer/loan, the selling club's (`club_agreed`). status: offered →
    active | declined | cancelled; active → on_loan → active, active →
    ended. `wage` = coins per season to the player's wallet (at most
    config.manager_live_wage_max), paid when the season starts; the club
    budget pays its euro equivalent (× config.manager_wage_eur_per_coin).
    One active contract per player — checked under his user-row lock."""

    __tablename__ = "manager_contracts"
    __table_args__ = (Index("ix_manager_contracts_user_status", "user_id", "status"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(16), nullable=False, default="sign")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="offered")
    from_contract_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manager_contracts.id", ondelete="SET NULL"), nullable=True)
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    wage: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    seasons_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seasons_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    club_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    player_agreed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    matches_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    assists: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    earned: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    decided_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerNpc(Base):
    """A footballer of the game catalog at a manager club, bought (`kind`
    buy, 1-3 seasons) or on loan (one season). A footballer plays for one
    club at a time (partial unique index on the active rows). `auto` = the
    system signed him for an empty slot when the season started. `wage` =
    euros per season at the base rate (the division and «Бухгалтерия»
    adjust it when it is paid at the season start)."""

    __tablename__ = "manager_npc"
    __table_args__ = (
        Index(
            "uq_manager_npc_active_player", "player_id", unique=True,
            postgresql_where=text("status = 'active'"), sqlite_where=text("status = 'active'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    player_id: Mapped[int] = mapped_column(ForeignKey("players.id", ondelete="CASCADE"), nullable=False)
    kind: Mapped[str] = mapped_column(String(8), nullable=False, default="buy")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    wage: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    seasons_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    auto: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    goals: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    ended_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerSeason(Base):
    """One weekly season (key = ISO week, "2026-W43"). Created once when the
    preseason closes (its primary key makes the start happen once);
    `settled_at` once every league of it has finished and the pyramid moves
    (promotion / relegation) were applied. `depth` = how many divisions the
    pyramid had open at the start."""

    __tablename__ = "manager_seasons"

    key: Mapped[str] = mapped_column(String(10), primary_key=True)
    depth: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerLeague(Base):
    """One league of a division in a season: up to config.manager_league_size
    manager clubs of similar strength, bots from the «Карьера тренера» club
    list fill it, a single round robin at the manager slots. Teams (squads
    frozen at the season start, «Клубная база» snapshot), fixtures,
    schedule, results and player stats live in the JSON `state`."""

    __tablename__ = "manager_leagues"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False, index=True)
    division: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active", index=True)
    rounds_played: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    state: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    finished_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerValueHistory(Base):
    """A «Мой игрок»'s transfer value at each season start (the ▲/▼ trend
    and the chart)."""

    __tablename__ = "manager_value_history"

    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    season_key: Mapped[str] = mapped_column(String(10), primary_key=True)
    value: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rating: Mapped[int] = mapped_column(Integer, nullable=False)


class ManagerCosmetic(Base):
    """A cosmetic item (emblem part, kit pattern, share frame, stadium name
    rights) a club owns for good (manager_shop)."""

    __tablename__ = "manager_cosmetics"
    __table_args__ = (UniqueConstraint("club_id", "code", name="uq_manager_cosmetic"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerMerch(Base):
    """A fan's merchandise of another user's club (scarf, shirt…): bought
    with coins (burned), adds euros to that club's budget. One of each item
    per fan and club (a collection in the fan's profile)."""

    __tablename__ = "manager_merch"
    __table_args__ = (UniqueConstraint("user_id", "club_id", "code", name="uq_manager_merch"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    code: Mapped[str] = mapped_column(String(32), nullable=False)
    coins: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    eur: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerLedger(Base):
    """Every euro the club budget gains or loses («Кабинет президента»:
    the income and expense report by seasons). `season_key` = the season
    the money belongs to (preseason spending counts for the coming one);
    `ref` makes a payout happen once (unique per club; NULL = a plain
    entry)."""

    __tablename__ = "manager_ledger"
    __table_args__ = (
        UniqueConstraint("club_id", "ref", name="uq_manager_ledger_ref"),
        Index("ix_manager_ledger_club_season", "club_id", "season_key"),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False)
    kind: Mapped[str] = mapped_column(String(24), nullable=False)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False)
    ref: Mapped[Optional[str]] = mapped_column(String(64), nullable=True)
    note: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerDeal(Base):
    """A financial deal of the club for one season (manager_finance):
    sponsor, kit (shirt sponsor, 1-3 seasons, `seasons`), tour, tv, deposit, venture,
    farm. One of a kind per club and first season (unique row = the
    idempotency). `option` = the sponsor type / tour / brand; `amount` = the
    stake or price; `data` = terms frozen when signed (keys of the seasons
    it covers, rates, effects); status active → done | lost."""

    __tablename__ = "manager_deals"
    __table_args__ = (UniqueConstraint("club_id", "kind", "season_key", name="uq_manager_deal_season"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False)
    seasons: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    option: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    amount: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    result: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    data: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    settled_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerLoan(Base):
    """A bank loan of the club (manager_finance). `debt` grows by
    `rate_bp` (basis points) at every season start it is outstanding;
    when `seasons_left` has run out the season start collects it. Not
    enough budget → `overdue`: a penalty on the debt and no transfers until
    it is repaid. One open loan per club (partial unique index)."""

    __tablename__ = "manager_loans"
    __table_args__ = (
        Index(
            "uq_manager_loan_open", "club_id", unique=True,
            postgresql_where=text("status <> 'repaid'"), sqlite_where=text("status <> 'repaid'"),
        ),
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    principal: Mapped[int] = mapped_column(BigInteger, nullable=False)
    debt: Mapped[int] = mapped_column(BigInteger, nullable=False)
    rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    seasons_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seasons_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="active")
    last_season: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerMove(Base):
    """The transfer log of a club: who came and who left, when, for how much
    and why (`kind`). Append-only, written where the move happens; the
    «Трансферы» tab shows it. `season_key` = the season the move is for
    (a window's deals belong to the coming season)."""

    __tablename__ = "manager_moves"
    __table_args__ = (Index("ix_manager_moves_club", "club_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False)
    direction: Mapped[str] = mapped_column(String(4), nullable=False)  # in | out
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    who: Mapped[str] = mapped_column(String(64), nullable=False)
    position: Mapped[Optional[str]] = mapped_column(String(8), nullable=True)
    rating: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    other_club: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerStock(Base):
    """A club on the «Кабинет президента» exchange: `shares_total` shares, of
    which `floated` were put on the market by IPO (≤ 49%). `unsold` = IPO
    shares nobody bought yet (their money goes to the club), `pool` = shares
    holders sold back to the exchange (resold without paying the club).
    `price` (€ per share) changes only after a round / at a season start
    (the club value without its budget × the form); `history` keeps the
    last prices for the chart."""

    __tablename__ = "manager_stocks"

    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), primary_key=True)
    shares_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1000)
    floated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    unsold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    pool: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    base: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    history: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    raised_season: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    raised_eur: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    dividends_paid: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerShare(Base):
    """Shares of one club (`club_id`) held by another club (`holder_club_id`);
    `cost` = euros paid for them (the P&L), `dividends` = euros received;
    `listed` of them are offered to other clubs at `ask` € a share."""

    __tablename__ = "manager_shares"
    __table_args__ = (UniqueConstraint("club_id", "holder_club_id", name="uq_manager_share_holder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    holder_club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    shares: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    cost: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    dividends: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    listed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    ask: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)


class ManagerTrade(Base):
    """The exchange tape: ipo | buy | sell | buyback of `shares` of `club_id`
    by `holder_club_id` at `price` (€ per share), `fee` burnt."""

    __tablename__ = "manager_trades"
    __table_args__ = (Index("ix_manager_trades_club", "club_id", "id"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False)
    holder_club_id: Mapped[Optional[int]] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=True, index=True)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    shares: Mapped[int] = mapped_column(Integer, nullable=False)
    price: Mapped[int] = mapped_column(BigInteger, nullable=False)
    fee: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)


class ManagerBond(Base):
    """A club's bond: `units_total` units of `unit_eur` at `rate_bp` per
    season, sold in the window for `season_key` (status selling), then active
    for `seasons_total` seasons: a coupon at each season end, the principal
    at the last one. Not paid → default (no transfers until repaid)."""

    __tablename__ = "manager_bonds"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    season_key: Mapped[str] = mapped_column(String(10), nullable=False)
    seasons_total: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    seasons_left: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    rate_bp: Mapped[int] = mapped_column(Integer, nullable=False)
    unit_eur: Mapped[int] = mapped_column(BigInteger, nullable=False)
    units_total: Mapped[int] = mapped_column(Integer, nullable=False)
    units_sold: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="selling")
    last_season: Mapped[Optional[str]] = mapped_column(String(10), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    closed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ManagerBondHolding(Base):
    """Units of a bond held by a club; `received` = coupons and principal paid."""

    __tablename__ = "manager_bond_holdings"
    __table_args__ = (UniqueConstraint("bond_id", "holder_club_id", name="uq_manager_bond_holder"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    bond_id: Mapped[int] = mapped_column(ForeignKey("manager_bonds.id", ondelete="CASCADE"), nullable=False, index=True)
    holder_club_id: Mapped[int] = mapped_column(ForeignKey("manager_clubs.id", ondelete="CASCADE"), nullable=False, index=True)
    units: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    received: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0)
