from datetime import date, datetime
from typing import Optional

from sqlalchemy import BigInteger, Boolean, Date, ForeignKey, Integer, JSON, String, DateTime
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.database import Base
from app.models.mixins import TimestampMixin


class User(TimestampMixin, Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    telegram_id: Mapped[int] = mapped_column(BigInteger, unique=True, index=True, nullable=False)
    username: Mapped[Optional[str]] = mapped_column(String(64), index=True, nullable=True)
    first_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    last_name: Mapped[Optional[str]] = mapped_column(String(128), nullable=True)
    avatar_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)

    balance: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    is_admin: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    game_rewards_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Set by the bot (asyncpg, not this ORM) when a send_message attempt
    # raises TelegramForbiddenError; cleared when the user next sends /start.
    # Broadcasts/gifts/notifications should never queue a Telegram message
    # for a user with this set — see bot/services/notifier.py and
    # broadcast_service.py / gift_service.py's recipient queries.
    bot_blocked: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Admin-imposed trade ban (moderation tool) — distinct from accept_trades
    # below, which is the user's own opt-out preference. Blocks both sending
    # and accepting trade offers.
    is_trade_banned: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    experience: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    received_starting_bonus: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    last_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Card Arena stats
    matches_won: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_drawn: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    matches_lost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_for: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    goals_against: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arena_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Card Arena divisions (arena_ladder_service) — separate from
    # arena_rating, which keeps feeding the overall «Лига».
    arena_points: Mapped[int] = mapped_column(Integer, default=0, nullable=False, index=True)
    arena_shield_matches: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    arena_best_division: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Team strength at this user's last Arena kickoff — matchmaking only
    # picks opponents who actually play the Arena.
    arena_last_strength: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # The opponent found for the next match (shown before kickoff, kept until
    # that match is played so a player can't re-roll for an easier one).
    arena_pending_opponent: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    # Lifetime counters feeding `metric_counter` tasks (see task_service.py).
    arena_clean_sheet_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_levels_completed: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_levels_cleared: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Tactico stats
    tactics_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tactico_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tactico_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Penalty stats
    penalty_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Memory sequence
    memory_best_score: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    memory_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    memory_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Card Arena hourly limit
    match_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    match_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Saboteur
    saboteur_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    saboteur_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    saboteur_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Penalty
    penalty_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    penalty_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    penalty_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Free Kick
    free_kick_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_kick_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    free_kick_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    free_kick_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Football Hangman
    hangman_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hangman_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    hangman_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tournament_stars_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    tournament_cups_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    hangman_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Найди пару (card pairs memory match)
    pairs_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pairs_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    pairs_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    pairs_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Футбольное Стратего
    stratego_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Задача дня»: local day last solved (reward once a day) and lifetime count.
    stratego_puzzle_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    stratego_puzzles_solved: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stratego_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stratego_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    stratego_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    stratego_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # Pre-match preparation: {"cards": {slot: user_card_id}, "layout": {slot:
    # [row, col]}} (see stratego_service.get_squad). Placement is done here,
    # before any challenge, so a match starts straight in play — both sides
    # "placed simultaneously" because each prepared privately beforehand.
    # Stale/missing entries are auto-filled lazily; None = fully auto.
    stratego_squad: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # «Мордобой»: rating, the usual hourly/daily counter pairs and the saved
    # boxer (a user_card id; checked for ownership whenever it is used,
    # stale ids fall back to the strongest card).
    mordoboi_rating: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mordoboi_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mordoboi_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mordoboi_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    mordoboi_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    mordoboi_card_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # «Легенда ринга»: local day of the last rewarded legend win, lifetime wins.
    mordoboi_legend_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    mordoboi_legend_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # «Выход на ринг»: a preset nickname (mordoboi_look.NICKNAMES) and the
    # equipped ring cosmetics (kinds ring_gloves / ring_shorts / ring_entrance).
    mordoboi_nickname: Mapped[Optional[str]] = mapped_column(String(32), nullable=True)
    equipped_ring_gloves_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    equipped_ring_shorts_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    equipped_ring_entrance_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )

    # «Контратака»: saved squad {"cards": [card ids], "leader": card id}
    # (it is also the arena defence), arena rating, the usual hourly/daily
    # pairs (arena attacks), boss attempts per day, the current arena offers.
    kontra_squad: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    kontra_rating: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    kontra_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kontra_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    kontra_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kontra_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    kontra_boss_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    kontra_boss_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    kontra_arena_offers: Mapped[Optional[list]] = mapped_column(JSON, nullable=True)

    # Футбольный магнат
    magnate_wins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    magnate_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    magnate_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    magnate_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    magnate_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Shared hourly pool across every club-scoped mini-game (Повтори порядок,
    # Пенальти, Своя позиция) — a member gets club_games_hourly_limit plays
    # per hour TOTAL, spendable on any mix of these games, not N plays of
    # each independently. See club_game_limits_service.consume_club_game_slot.
    club_games_hourly_attempts: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_games_hour_started_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Club Sequence (club-scoped mini-game; reward credits the club's budget)
    # Daily reward cap only — hourly play is gated by the shared pool above.
    club_game_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_game_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Пенальти (club-scoped mini-game; reward credits the club's budget)
    # Daily reward cap only — hourly play is gated by the shared pool above.
    club_penalty_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_penalty_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Своя позиция (club-scoped mini-game; reward credits the club's budget)
    # Daily reward cap only — hourly play is gated by the shared pool above.
    club_position_match_rewarded_attempts_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    club_position_match_attempts_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # FUT Draft — best squad strength ever assembled, drives the leaderboard
    # (same "personal best" pattern as memory_best_score).
    fut_draft_best_squad_strength: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Free pack (every N hours)
    free_pack_available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    free_pack_notified: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Shop "предложение дня": the local date the discounted pack was last
    # bought (one discounted purchase per player per day, shop_offer_service).
    daily_offer_claimed_on: Mapped[Optional[date]] = mapped_column(Date, nullable=True)
    # "Мой игрок" XP (services/my_player_service.py). Lives on the user row so
    # wallet_service.credit_coins can grant it under the same row lock; it
    # accrues even before the player is created. today/day = daily cap window.
    my_player_xp: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    my_player_xp_today: Mapped[int] = mapped_column(Integer, default=0, server_default="0", nullable=False)
    my_player_xp_day: Mapped[Optional[date]] = mapped_column(Date, nullable=True)

    # Chat mode promo pack ("вкарта" command in group chats, every N hours) —
    # a separate cooldown from free_pack_available_at so the two mechanics
    # don't compete with each other.
    chat_pack_available_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Consecutive days played, tracked off daily-reward claims — unlike
    # DailyReward.streak_day (which cycles 1-7 to pick a reward tier), this
    # keeps counting up so the profile can show an uncapped "days in a row".
    daily_login_streak: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Paid coin packs (with a legendary chance) opened since the last
    # legendary — GameConfig.pity_packs guarantees one (migration 0183).
    pity_counter: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    wheel_free_spins_used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    wheel_spins_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # «21: Добавленное время» (see blackjack_service.py). The *_today pair
    # resets at local midnight (blackjack_day_reset_at); the two entry
    # banks don't expire — paid ones were bought with Stars, replay ones
    # were earned by a draw.
    blackjack_free_used_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blackjack_paid_bought_today: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blackjack_day_reset_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    blackjack_paid_entries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    blackjack_replay_entries: Mapped[int] = mapped_column(Integer, default=0, nullable=False)

    # Referrals
    referred_by_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    referral_count: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    referral_reward_granted: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)

    # Trade privacy
    accept_trades: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Saved default card filter (rarity/country/club/position/sort) for the
    # collection, album and Forge — see PUT /collection/filter-default.
    card_filter_default: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Currently-equipped Badge (if any), shown next to this user's name
    # everywhere a public identity is rendered. `lazy="joined"` so every
    # query touching User eager-loads it — this is read almost everywhere
    # User is serialized, and async SQLAlchemy can't lazy-load on demand.
    active_badge_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("badges.id", ondelete="SET NULL"), nullable=True
    )
    active_badge: Mapped[Optional["Badge"]] = relationship(lazy="joined")

    # Equipped cosmetics (models/monetization.py) — visual only. Stored as
    # ids; cosmetic_service resolves them to style keys for display.
    equipped_frame_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    equipped_background_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    equipped_card_skin_id: Mapped[Optional[int]] = mapped_column(
        ForeignKey("cosmetics.id", ondelete="SET NULL"), nullable=True
    )
    # When the one-time starter offer was first shown full-screen.
    starter_offer_seen_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    cards: Mapped[list["UserCard"]] = relationship(back_populates="owner", cascade="all, delete-orphan")

    def full_display_name(self) -> str:
        name = " ".join(filter(None, [self.first_name, self.last_name])).strip()
        return name or self.username or f"Player{self.telegram_id}"
