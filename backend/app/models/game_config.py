from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class GameConfig(TimestampMixin, Base):
    """Singleton row (id=1) holding admin-tunable game economy settings."""

    __tablename__ = "game_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)

    memory_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    memory_reward_cap: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    suspicious_memory_score_threshold: Mapped[int] = mapped_column(Integer, default=400, nullable=False)

    match_reward_win: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    match_reward_draw: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    match_reward_loss: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    difficulty_easy_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=0.85, nullable=False)
    difficulty_medium_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.0, nullable=False)
    difficulty_hard_multiplier: Mapped[float] = mapped_column(Numeric(4, 2), default=1.2, nullable=False)
    suspicious_score_margin: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    match_shot_miss_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.08, nullable=False)
    match_shot_miss_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.30, nullable=False)
    match_defender_block_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.10, nullable=False)
    match_defender_block_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.35, nullable=False)
    match_shot_type_in_box_weight: Mapped[int] = mapped_column(Integer, default=55, nullable=False)
    match_shot_type_long_range_weight: Mapped[int] = mapped_column(Integer, default=35, nullable=False)
    match_shot_type_empty_net_weight: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    match_attack_shoot_miss_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.08, nullable=False)
    match_attack_shoot_miss_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.32, nullable=False)
    match_pass_fail_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.05, nullable=False)
    match_pass_fail_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.28, nullable=False)
    match_receiver_shot_miss_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.05, nullable=False)
    match_receiver_shot_miss_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.22, nullable=False)
    match_tackle_foul_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.06, nullable=False)
    match_tackle_foul_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.30, nullable=False)
    match_tackle_red_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.05, nullable=False)
    match_tackle_red_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.22, nullable=False)
    match_block_fail_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.10, nullable=False)
    match_block_fail_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.32, nullable=False)
    match_keeper_save_chance_min: Mapped[float] = mapped_column(Numeric(4, 2), default=0.35, nullable=False)
    match_keeper_save_chance_max: Mapped[float] = mapped_column(Numeric(4, 2), default=0.75, nullable=False)
    match_red_card_strength_penalty_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=0.12, nullable=False)
    match_penalty_gk_rating_penalty: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    saboteur_line_base_reward: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    saboteur_line_growth: Mapped[float] = mapped_column(Numeric(4, 2), default=1.15, nullable=False)
    saboteur_daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    saboteur_max_steward_count: Mapped[int] = mapped_column(Integer, default=4, nullable=False)

    penalty_reward_win: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    penalty_reward_draw: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    penalty_reward_loss: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    penalty_bot_miss_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.12, nullable=False)
    penalty_daily_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    penalty_challenge_expiry_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)

    free_kick_period_min_ms: Mapped[int] = mapped_column(Integer, default=1100, nullable=False)
    free_kick_period_max_ms: Mapped[int] = mapped_column(Integer, default=1700, nullable=False)
    free_kick_base_stake: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    free_kick_daily_limit: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    hourly_game_limit: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    hangman_daily_limit: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    hangman_reward_correct: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    hangman_max_wrong: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    pairs_daily_limit: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    pairs_reward_perfect: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    pairs_reward_min: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Reward drops by pairs_bracket_penalty for every pairs_error_bracket_size
    # wrong attempts, e.g. (40, 10, 10) -> 0-10 wrong = 40 coins, 11-20 = 30,
    # 21-30 = 20, ... floored at pairs_reward_min. See pairs_service._tiered_reward.
    pairs_error_bracket_size: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    pairs_bracket_penalty: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    pairs_bonus_coins: Mapped[int] = mapped_column(Integer, default=25, nullable=False)

    free_pack_interval_hours: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    free_pack_pack_slug: Mapped[str] = mapped_column(String, default="basic", nullable=False)

    # "вкарта" command in group chats — reuses free_pack_pack_slug's pack but
    # on its own cooldown.
    chat_pack_interval_hours: Mapped[int] = mapped_column(Integer, default=4, nullable=False)

    referral_referred_reward: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    referral_referrer_reward: Mapped[int] = mapped_column(Integer, default=400, nullable=False)

    tactico_challenge_expiry_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    tactico_round_timeout_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    tactico_phase_bonus_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=0.20, nullable=False)
    tactico_reward_win: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    tactico_reward_draw: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    tactico_reward_loss: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    tactico_bot_optimal_pick_chance_easy: Mapped[float] = mapped_column(Numeric(4, 2), default=0.40, nullable=False)
    tactico_bot_optimal_pick_chance_medium: Mapped[float] = mapped_column(Numeric(4, 2), default=0.65, nullable=False)
    tactico_bot_optimal_pick_chance_hard: Mapped[float] = mapped_column(Numeric(4, 2), default=0.90, nullable=False)
    tactico_max_legendary_cards: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    tactico_max_epic_cards: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Set by an admin right before deploying an update (see routers/maintenance.py);
    # the Mini App shows a "may be flaky for a few minutes" banner while now() < this.
    maintenance_banner_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamp of the last admin update broadcast (see routers/broadcasts.py). The
    # Mini App shows a dismissible "update available" banner whenever this is newer
    # than what the client last dismissed (tracked client-side, not here).
    last_update_broadcast_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
