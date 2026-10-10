from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin


class GameConfig(TimestampMixin, Base):
    """Singleton row (id=1) holding admin-tunable game economy settings."""

    __tablename__ = "game_config"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    club_creation_cost_coins: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    club_daily_reward_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    club_tournament_cooldown_hours: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    club_form_window_matches: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_form_bonus_per_result: Mapped[float] = mapped_column(Numeric(4, 2), default=0.02, nullable=False)
    club_tournament_budget_place_1: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    club_tournament_budget_place_2: Mapped[int] = mapped_column(Integer, default=750, nullable=False)
    club_tournament_budget_place_3: Mapped[int] = mapped_column(Integer, default=550, nullable=False)
    club_tournament_budget_place_4: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    club_tournament_budget_place_5: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    club_tournament_budget_place_6: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    club_tournament_budget_place_7: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    club_tournament_budget_place_8: Mapped[int] = mapped_column(Integer, default=60, nullable=False)

    club_match_reward_win: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    club_match_reward_draw: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    club_match_reward_loss: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    club_member_match_reward_win: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    club_member_match_reward_draw: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    club_member_match_reward_loss: Mapped[int] = mapped_column(Integer, default=50, nullable=False)

    club_training_boost_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=0.10, nullable=False)
    club_training_uses_per_tournament: Mapped[int] = mapped_column(Integer, default=3, nullable=False)

    # Shared hourly pool across every club-scoped mini-game — see
    # User.club_games_hourly_attempts / club_game_limits_service.
    club_games_hourly_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)

    club_game_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_game_reward_cap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)

    club_penalty_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_penalty_reward_win: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    club_penalty_reward_loss: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    club_penalty_bot_miss_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.12, nullable=False)

    club_position_match_daily_reward_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_position_match_max_mistakes: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_position_match_reward_perfect: Mapped[int] = mapped_column(Integer, default=35, nullable=False)
    club_position_match_reward_min: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    club_position_match_penalty_per_mistake: Mapped[int] = mapped_column(Integer, default=8, nullable=False)

    fut_draft_entry_cost: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    # Chance (0-100, all five must sum to 100) that a given slot's pick is
    # dealt from each tier — see fut_draft_service.TIER_COMPOSITIONS for the
    # exact rarity mix each tier deals. Legendary only ever appears via the
    # jackpot tier, keeping it rare across the whole draft on purpose.
    fut_draft_weak_chance: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    fut_draft_normal_chance: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    fut_draft_strong_chance: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    fut_draft_top_chance: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    fut_draft_jackpot_chance: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Reward (coins) by number of match wins reached (0-4) before the run ended.
    fut_draft_reward_win_0: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    fut_draft_reward_win_1: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    fut_draft_reward_win_2: Mapped[int] = mapped_column(Integer, default=350, nullable=False)
    fut_draft_reward_win_3: Mapped[int] = mapped_column(Integer, default=700, nullable=False)
    fut_draft_reward_win_4: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    # Extra team-strength bonus on top of calculate_base_strength's own
    # (much smaller) built-in chemistry bonus — per additional pick sharing
    # the draft's most common club/country. FUT Draft's own economy, not a
    # change to the shared personal-lineup formula.
    fut_draft_club_bonus_per_extra: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    fut_draft_country_bonus_per_extra: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    # Bots get progressively tougher across the 4-match series, on top of
    # their own easy/medium difficulty multiplier — this is the percentage
    # the final (4th) match's bot strength is boosted by, ramped up linearly
    # from 0% in match 1. Keeps a very strong squad from steamrolling every
    # round at the same relative difficulty, without making the bots brutal.
    fut_draft_round_bot_boost_pct: Mapped[float] = mapped_column(Numeric(4, 2), default=20.0, nullable=False)

    club_tactical_phases_per_match_min: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    club_tactical_phases_per_match_max: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    club_tactical_promoted_chance_target_min: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    club_tactical_promoted_chance_target_max: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    club_tactical_fit_formation_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.40, nullable=False)
    club_tactical_fit_playstyle_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.40, nullable=False)
    club_tactical_fit_mentality_weight: Mapped[float] = mapped_column(Numeric(4, 2), default=0.20, nullable=False)
    club_tactical_tackle_attempt_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.20, nullable=False)
    club_tactical_injury_chance: Mapped[float] = mapped_column(Numeric(4, 2), default=0.35, nullable=False)

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

    # Emergency kill switches — hide these app-wide without a deploy if a
    # bug turns up right after launch (see routers/feature_flags.py).
    # matchmaking_enabled hides only the "Играть" (opponent search) button
    # on the Tactico/Penalty matches screens — bot and friend-challenge play
    # stay available either way.
    matchmaking_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    wheel_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Hides the league banner on the home screen and profile — the rest of
    # the leagues feature (backend rating tracking, reward granting, admin
    # tier management) keeps running either way, same "hide the entry
    # point, not the underlying feature" shape as the two flags above.
    leagues_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

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
    # Bot daily digest (bot/services/daily_reminder.py): one message a day to
    # players with an unclaimed daily reward and/or finished-but-unclaimed
    # tasks, sent after this hour in the bot's timezone. Off by default.
    bot_daily_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    bot_daily_digest_hour: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    # Shop "предложение дня" (services/shop_offer_service.py): one coin pack a
    # day at a discount, once per player per day. pack_id = None rotates
    # through the active coin packs by date. Off by default.
    shop_daily_offer_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    shop_daily_offer_discount_pct: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    shop_daily_offer_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # --- "Карьера тренера" (services/career_service.py) ---
    career_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Coins by final place, index 0 = 1st ... 7 = 8th; x the difficulty %.
    career_place_rewards: Mapped[list] = mapped_column(
        JSON, default=lambda: [1500, 1000, 700, 500, 350, 250, 150, 100], nullable=False,
    )
    # [amateur, pro, legend]: reward multiplier (%) and bot rating offset vs. the squad.
    career_difficulty_reward_pct: Mapped[list] = mapped_column(JSON, default=lambda: [100, 150, 200], nullable=False)
    career_difficulty_rating_offset: Mapped[list] = mapped_column(JSON, default=lambda: [-6, 0, 4], nullable=False)
    career_match_reward_win: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    career_match_reward_draw: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Bots get stronger through the season: +N tenths of a rating point per round.
    career_bot_growth_tenths: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Fatigue (0-100): +per match played, -per round rested; at 100 a player
    # plays at -penalty% rating. Injury chance per match played (doubled
    # above 70 fatigue) rules the card out for 1-2 rounds.
    career_fatigue_per_match: Mapped[int] = mapped_column(Integer, default=35, nullable=False)
    career_fatigue_recovery: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    career_fatigue_penalty_pct: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    career_injury_chance_pct: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Discipline per match played: a yellow (N yellows = one round out) or a
    # straight red (one round out). Form: after a win a player may get
    # +1..+max rating for the next match, after a defeat -1.
    career_yellow_chance_pct: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    career_red_chance_pct: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    career_yellows_for_ban: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    career_form_max: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    career_reminders_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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
    tactico_max_diamond_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    match_max_diamond_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # Soft ceiling on diamond card leveling (feed_cards never lets a card's
    # rating cross this via NEW feeding) — separate from the absolute 99
    # technical ceiling every card is clamped to. Disabling it just lifts
    # the soft ceiling back to 99; it never downgrades a card that already
    # sits above the configured cap (e.g. from before this setting existed).
    diamond_rating_cap: Mapped[int] = mapped_column(Integer, default=95, nullable=False)
    diamond_rating_cap_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)

    # Set by an admin right before deploying an update (see routers/maintenance.py);
    # the Mini App shows a "may be flaky for a few minutes" banner while now() < this.
    maintenance_banner_until: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Timestamp of the last admin update broadcast (see routers/broadcasts.py). The
    # Mini App shows a dismissible "update available" banner whenever this is newer
    # than what the client last dismissed (tracked client-side, not here).
    last_update_broadcast_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # Admin-authored text shown to every player as a dismissible banner throughout the
    # Mini App (see routers/announcement.py) — a pure in-app notice, unlike the Telegram
    # push broadcasts.py sends. NULL means no banner. announcement_updated_at is stamped
    # whenever the text changes so the client re-shows it even if a player already
    # dismissed a previous announcement (dismissal itself is tracked client-side, not here).
    announcement_text: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    announcement_updated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    wheel_free_spins_per_day: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    wheel_spin_cost_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    wheel_spin_cost_stars: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    wheel_duplicate_badge_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    bingo_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bingo_reward_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    ptour_match_reward_win: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    ptour_match_reward_draw: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    ptour_match_reward_loss: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Index 0 = 1st place ... index 15 = 16th place.
    ptour_place_rewards: Mapped[list] = mapped_column(
        JSON, default=lambda: [3000, 2000, 1500, 1000, 750, 500, 400, 300, 250, 200, 150, 100, 75, 50, 25, 0], nullable=False,
    )
    ptour_stars_by_place: Mapped[list] = mapped_column(
        JSON, default=lambda: [5, 4, 3, 2, 1, 0, 0, 0, 0, 0, 0, -1, -2, -3, -4, -5], nullable=False,
    )

    # --- Card skills (services/card_skill_service.py, card_skill_effects.py) ---
    # Global switch: off = no assign/upgrade/replace, and NEW matches snapshot
    # no skill effects. Owned skills and tokens are untouched either way;
    # matches already started keep the rules frozen in their own state.
    card_skills_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Additive percentage points a skill adds to its one specific event.
    card_skill_level_1_bonus_pp: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    card_skill_level_2_bonus_pp: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    card_skill_level_3_bonus_pp: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    # Ceiling on the SUMMED same-direction skill bonus applied to one roll.
    card_skill_event_bonus_cap_pp: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    # Bounds a skill-adjusted probability is kept within (percent). Applied only
    # when a skill actually moved the roll, and never pulls a base probability
    # that already sits outside them back inside — so existing coach/stadium/
    # rating curves are never clipped by this.
    card_skill_probability_floor_pct: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    card_skill_probability_ceiling_pct: Mapped[int] = mapped_column(Integer, default=95, nullable=False)
    card_skill_assign_token_cost: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    card_skill_assign_coin_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    card_skill_upgrade_2_token_cost: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    card_skill_upgrade_2_coin_cost: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    card_skill_upgrade_3_token_cost: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    card_skill_upgrade_3_coin_cost: Mapped[int] = mapped_column(Integer, default=1200, nullable=False)
    card_skill_replace_token_cost: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    card_skill_replace_coin_cost: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # Player-tournament place rewards in skill tokens: index 0 = 1st place;
    # each entry is null or {"skill_code": str, "quantity": int}. Empty = none.
    ptour_place_skill_tokens: Mapped[list] = mapped_column(JSON, default=list, nullable=False)
