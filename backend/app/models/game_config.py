from datetime import datetime
from typing import Optional

from sqlalchemy import JSON, BigInteger, Boolean, DateTime, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base
from app.models.mixins import TimestampMixin

# «Клубная база» defaults (GameConfig.club_base_buildings / club_base_caps;
# the 0180 migration writes the same values). Lists are per level.
# 25 levels like the whole «Академия»: costs and build hours grow smoothly,
# effects go linearly from level 1 to level 25 (the caps below still apply).
_LEVELS = 25


def _nice(v: float) -> int:
    step = 100 if v < 10000 else 500 if v < 100000 else 1000
    return int(round(v / step) * step)


def _costs(base: int, k: float) -> list[int]:
    return [_nice(base + k * lv ** 1.9) for lv in range(1, _LEVELS + 1)]


def _hours(base: float, k: float) -> list[int]:
    return [int(round(base + k * lv ** 2)) for lv in range(1, _LEVELS + 1)]


def _line(first: int, last: int, step: int = 1) -> list[int]:
    return [int(round((first + (last - first) * (lv - 1) / (_LEVELS - 1)) / step) * step) for lv in range(1, _LEVELS + 1)]


_BASE_COSTS, _BASE_HOURS = _costs(600, 220), _hours(3, 0.3)
DEFAULT_CLUB_BASE_BUILDINGS: dict = {
    "hq": {"costs": _costs(500, 165), "hours": _hours(2, 0.25), "cap": list(range(1, _LEVELS + 1))},
    "stadium": {"costs": _costs(1500, 350), "hours": _hours(6, 0.45), "matchday": _line(10, 150),
                "capacity": _line(3000, 90000, 500)},
    "hotel": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "matchday_pct": _line(2, 55)},
    "training": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "familiarity_pct": _line(2, 55),
                 "my_player_xp_pct": _line(1, 25)},
    "medical": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "injury_pct": _line(2, 42), "recovery": _line(1, 14)},
    "analytics": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "prep_pct": _line(1, 20)},
    "media": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "rep_pct": _line(1, 25)},
    "marketing": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "daily": _line(20, 300), "matchday_pct": _line(1, 25)},
    "shop": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "daily": _line(15, 210), "sell_pct": _line(1, 10)},
    "accounting": {"costs": _BASE_COSTS, "hours": _BASE_HOURS, "discount_pct": _line(1, 15)},
}
# Stadium cosmetics shop: one item per look option that is not the default.
# coins/stars 0 = not sold for that currency (both 0 = free); min_level =
# stadium level needed to buy and to use it.
def _cosmetic(code: str, kind: str, value: str, name: str, coins: int, stars: int, min_level: int = 1) -> dict:
    return {"code": code, "kind": kind, "value": value, "name": name, "coins": coins, "stars": stars,
            "min_level": min_level, "enabled": True}


DEFAULT_CLUB_BASE_COSMETICS: list = [
    _cosmetic("seats_blue", "seats", "blue", "Синие кресла", 0, 0),
    *[_cosmetic(f"seats_{v}", "seats", v, n, 3000, 20) for v, n in (
        ("sky", "Голубые кресла"), ("green", "Зелёные кресла"), ("yellow", "Жёлтые кресла"),
        ("white", "Белые кресла"), ("black", "Чёрные кресла"), ("purple", "Фиолетовые кресла"),
        ("orange", "Оранжевые кресла"))],
    _cosmetic("roof_canopy", "roof", "canopy", "Козырьки над трибунами", 15000, 75, 5),
    _cosmetic("roof_full", "roof", "full", "Крыша по кругу", 60000, 250, 15),
    _cosmetic("lights", "lights", "on", "Прожекторы", 25000, 120, 10),
    _cosmetic("screen", "screen", "on", "Видеотабло", 40000, 180, 20),
    _cosmetic("pitch_checks", "pitch", "checks", "Газон в клетку", 5000, 30),
    _cosmetic("pitch_diagonal", "pitch", "diagonal", "Газон по диагонали", 8000, 45, 5),
    _cosmetic("facade_brick", "facade", "brick", "Кирпичный фасад", 6000, 35, 3),
    _cosmetic("facade_glass", "facade", "glass", "Стеклянный фасад", 15000, 75, 10),
    _cosmetic("facade_gold", "facade", "gold", "Золотой фасад", 100000, 500, 25),
]

DEFAULT_CLUB_BASE_CAPS: dict = {
    "matchday_pct": 100, "injury_pct": 50, "recovery": 15, "familiarity_pct": 60, "my_player_xp_pct": 30,
    "prep_pct": 25, "rep_pct": 30, "sell_pct": 15, "discount_pct": 25, "daily": 600,
}


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

    # Card Arena balance (arena_tactics.compute_balance): style matchup
    # bonus, how sharply the strength gap decides possession / chances, and
    # the rating edge every roll gets from the strength ratio.
    arena_style_matchup_bonus_pct: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    arena_share_exponent: Mapped[float] = mapped_column(Numeric(4, 2), default=1.2, nullable=False)
    arena_shot_exponent: Mapped[float] = mapped_column(Numeric(4, 2), default=0.8, nullable=False)
    arena_edge_rating_per_10pct: Mapped[float] = mapped_column(Numeric(4, 2), default=2.0, nullable=False)
    arena_edge_rating_max: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    # Scale of arena_tactics.FORMATION_SHIFT (100 = as tabled, 0 = formations
    # only matter through positions and chemistry).
    arena_formation_effect_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Card Arena divisions (arena_ladder_service): Elo-like points, division
    # N = index N-1 of these parallel lists (first threshold is always 0).
    arena_points_k: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    arena_points_scale: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    arena_shield_matches: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    arena_matchmaking_window: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    arena_division_min_points: Mapped[list] = mapped_column(
        JSON, default=lambda: [0, 100, 200, 300, 400, 550, 700, 850, 1000, 1200], nullable=False,
    )
    arena_division_reward_coins: Mapped[list] = mapped_column(
        JSON, default=lambda: [0, 100, 150, 200, 300, 400, 500, 700, 1000, 1500], nullable=False,
    )
    arena_division_coin_pct: Mapped[list] = mapped_column(
        JSON, default=lambda: [100, 105, 110, 115, 120, 125, 130, 135, 140, 150], nullable=False,
    )

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
    # Player-to-player trades (migration 0163): off = no new offers and no
    # accepting; pending ones can still be cancelled / rejected.
    trades_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
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

    # --- "Лига клубов" (services/club_league_service.py) ---
    # Weekly table: members' activity (finished games/matches, coin pack
    # purchases, completed tasks) earns their club points, capped per member
    # per week; places get club_league_rewards[i] into the club budget.
    club_league_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    club_league_points_game: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    club_league_points_pack: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    club_league_points_task: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_league_member_weekly_cap: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    club_league_rewards: Mapped[list] = mapped_column(
        JSON, default=lambda: [1500, 1000, 750, 500, 400, 300, 200, 150, 100, 100], nullable=False,
    )

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
    # Tactics (career_tactics_service; seasons created after migration 0141).
    # Axis levers and interaction strengths: overrides on top of
    # career_tactics_service.DEFAULT_TUNING (empty = defaults).
    career_tactics_tuning: Mapped[dict] = mapped_column(JSON, default=dict, nullable=False)
    # Familiarity grows by step tenths of a % rating per match with the same
    # formation + tactic up to max; a new formation keeps keep_pct of it,
    # each changed tactical axis keeps axis_keep_pct.
    career_familiarity_step_tenths: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    career_familiarity_max_tenths: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    career_familiarity_keep_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    career_familiarity_axis_keep_pct: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    # Season squad (заявка) size for new seasons.
    career_squad_size: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    # Board objectives [survive, mid, promote]: bonus % of the place reward
    # when met, reputation when met / missed. Reputation for a title,
    # promotion, relegation; thresholds for the coach's reputation levels.
    career_ambition_bonus_pct: Mapped[list] = mapped_column(JSON, default=lambda: [10, 25, 50], nullable=False)
    career_ambition_rep_success: Mapped[list] = mapped_column(JSON, default=lambda: [5, 10, 20], nullable=False)
    career_ambition_rep_fail: Mapped[list] = mapped_column(JSON, default=lambda: [-3, -6, -15], nullable=False)
    career_rep_title: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    career_rep_promotion: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    career_rep_relegation: Mapped[int] = mapped_column(Integer, default=-10, nullable=False)
    career_rep_levels: Mapped[list] = mapped_column(JSON, default=lambda: [0, 40, 120, 250, 500], nullable=False)
    # Cup alongside the league (16 teams, knock-out after league rounds 4,
    # 6, 10 and 14): coins for [winner, finalist, semi-finalist] (x division
    # reward % is NOT applied) and reputation for the winner.
    career_cup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    career_cup_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [800, 400, 200], nullable=False)
    career_rep_cup: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Off-season: the next season is created automatically right after the
    # last round (first round the next day) unless the coach hasn't opened
    # the career for inactive_days — then no new season and one division
    # down. Core: with >= core_min cards kept and the same formation,
    # core_keep_pct of the familiarity carries over.
    career_offseason_auto: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    career_inactive_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    career_core_min: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    career_core_keep_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Preseason camp: physical = less fatigue gained in the first rounds;
    # tactical = familiarity bonus (tenths of a %) while the system is kept.
    career_camp_physical_pct: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    career_camp_physical_rounds: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    career_camp_tactical_tenths: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # Club tenure: +1 career-only rating per N minutes played, up to max.
    career_tenure_minutes_per_point: Mapped[int] = mapped_column(Integer, default=900, nullable=False)
    career_tenure_max: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Bot clubs per division in the catalog («Сформировать» in the admin).
    career_division_club_count: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Live match centre: the second half of a round with a human waits this
    # many minutes after kick-off for half-time instructions.
    career_live_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    career_halftime_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Coins for each career achievement unlocked; weekly Telegram digest.
    career_achievement_reward: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    career_digest_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Match plan limits: conditional instructions and substitutions per match.
    career_max_plan_rules: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    career_max_substitutions: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # [amateur, pro, legend]: chance (%) a bot plays a counter to the human
    # opponent's last played style.
    career_bot_counter_chance_pct: Mapped[list] = mapped_column(JSON, default=lambda: [0, 60, 85], nullable=False)
    # Divisions (career_service): a new player starts in the lowest one; the
    # top N places go up, the bottom N go down (leaving a season = down).
    # Lists are per division, index 0 = the top division: bot rating offset
    # vs. the squad, reward multiplier (%) and bot level
    # (amateur / pro / legend — counter-picking and in-match instructions).
    career_division_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    career_division_promote: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    career_division_relegate: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    career_division_rating_offset: Mapped[list] = mapped_column(JSON, default=lambda: [6, 3, 0, -3, -6], nullable=False)
    career_division_reward_pct: Mapped[list] = mapped_column(JSON, default=lambda: [250, 200, 150, 125, 100], nullable=False)
    career_division_bot_level: Mapped[list] = mapped_column(
        JSON, default=lambda: ["legend", "legend", "pro", "pro", "amateur"], nullable=False,
    )

    # --- "Мой игрок" (services/my_player_service.py) ---
    my_player_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # XP for every rewarded game action (any credit of a game/match/daily/task
    # reward, see wallet_service.credit_coins), capped per day.
    my_player_xp_per_reward: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    my_player_xp_daily_cap: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    # Bonus when the player's own card took part in a "Карьера тренера" match.
    my_player_xp_career_match: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Level L -> L+1 costs base + step * (L - 1) XP.
    my_player_xp_level_base: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    my_player_xp_level_step: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    my_player_points_per_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Overall rating ceiling, so the own card never outclasses top pack cards.
    my_player_rating_cap: Mapped[int] = mapped_column(Integer, default=88, nullable=False)
    # Frame tiers by rating: [silver, gold, legend] thresholds (below = bronze).
    my_player_tier_thresholds: Mapped[list] = mapped_column(JSON, default=lambda: [65, 75, 85], nullable=False)
    # Daily training mini-game: XP = base + per_hit x hits (0-3), once a day,
    # on top of the daily XP cap.
    my_player_training_xp_base: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    my_player_training_xp_per_hit: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Extra trainings on top of the free daily one: max bought per day and
    # the price of one (coins / Telegram Stars; 0 = not sold for that currency).
    my_player_extra_trainings_max: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    my_player_extra_training_coins: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    my_player_extra_training_stars: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Training streak: every `days` free trainings in a row pay `tokens`
    # skill tokens (of the player's skill, or one that fits the position).
    my_player_streak_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    my_player_streak_tokens: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Freshness (0-100): -per_match for every «Карьера игрока» match,
    # +regen_per_hour over time, +training per training run. At 0 freshness
    # the match rating drops by fatigue_max_penalty (linearly from 100).
    # Defaults: two matches a day cost a little more than a day of rest
    # gives back, so the daily training is what keeps him fresh all season.
    my_player_freshness_per_match: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    my_player_freshness_regen_per_hour: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    my_player_freshness_training: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    my_player_fatigue_max_penalty: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Friend duels: per day, coins for a win/draw (challenger only), XP per duel.
    my_player_duels_per_day: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    my_player_duel_reward_win: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    my_player_duel_reward_draw: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    my_player_duel_xp: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Changing the line (e.g. CM -> ST): price in coins / Stars (0 = not sold).
    my_player_role_change_coins: Mapped[int] = mapped_column(Integer, default=25000, nullable=False)
    my_player_role_change_stars: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # --- «Карьера игрока» (services/player_career_service.py) ---
    player_career_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # A club is open if its rating <= player rating + margin and the
    # player's prestige (MyPlayer.reputation) >= star_prestige[stars - 1] +
    # level_prestige[league level - 1].
    player_career_rating_margin: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    player_career_rep_per_goal: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    player_career_rep_per_assist: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    player_career_rep_per_win: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    player_career_rep_title: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    player_career_match_reward_win: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    player_career_match_reward_draw: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    player_career_goal_reward: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    player_career_match_xp: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    player_career_place_rewards: Mapped[list] = mapped_column(
        JSON, default=lambda: [1000, 700, 500, 350, 250, 180, 120, 80], nullable=False,
    )
    # Cosmetics shop: {code: price in coins}; a code missing here (or 0) is not for sale.
    my_player_cosmetic_prices: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {
            "headband": 300, "earring": 400, "chain": 600, "goggles": 800,
            "bg_sunset": 500, "bg_neon": 700, "bg_gold": 1200,
            "captain": 700, "headphones": 900, "bg_night": 900,
        },
    )
    # The same for Telegram Stars; an item may be sold for either or both.
    my_player_cosmetic_stars_prices: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {
            "crown": 150, "bg_galaxy": 75, "bg_champions": 100,
            "fx_sparkle": 50, "fx_fire": 75, "fx_lightning": 100,
            "hair_neymar": 120, "hair_cr7": 100, "hair_pogba": 90, "aviators": 60, "diamond_chain": 90,
            "bg_goal": 75, "bg_national": 75,
            "cel_siu": 100, "cel_plane": 75, "cel_heart": 50, "cel_dance": 150,
        },
    )
    # «Карьера игрока»: every completed club objective pays objective_coins
    # and objective_rep (prestige).
    player_career_objective_coins: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    player_career_objective_rep: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # By division of the «Карьера тренера» club list (1 = top … 5): base
    # squad rating of clubs without cards, base salary per season, prestige
    # needed on top of the club's stars.
    player_career_level_ratings: Mapped[list] = mapped_column(JSON, default=lambda: [80, 74, 68, 62, 54], nullable=False)
    player_career_level_salary: Mapped[list] = mapped_column(JSON, default=lambda: [1500, 1000, 600, 350, 150], nullable=False)
    player_career_level_prestige: Mapped[list] = mapped_column(JSON, default=lambda: [150, 80, 30, 10, 0], nullable=False)
    # Club stars 1..5: prestige needed, and +star_salary_pct salary per star above 1.
    player_career_star_prestige: Mapped[list] = mapped_column(JSON, default=lambda: [0, 30, 80, 160, 300], nullable=False)
    player_career_star_salary_pct: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    # +1% salary per 10 prestige, up to this many percent.
    player_career_prestige_salary_cap: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Contract length; once it runs out without a new deal, only divisions
    # free_agent_level and lower are open.
    player_career_contract_seasons: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    player_career_free_agent_level: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    # Transfer window: offers per window, and the per-counter-offer odds
    # (club accepts with base - raise% x raise_penalty - counters x
    # repeat_penalty, in percent).
    player_career_offers_max: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    player_career_haggle_base: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    player_career_haggle_raise_penalty: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    player_career_haggle_repeat_penalty: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Champions League: top N of a division-1 season; coins per round won (QF,
    # SF, final) and prestige for the title.
    player_career_cl_places: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    player_career_cl_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [300, 600, 1500], nullable=False)
    player_career_cl_prestige: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # National team: prestige for a call-up (tournament every two weeks),
    # coins per round won, prestige for the title.
    player_career_national_prestige: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    player_career_national_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [200, 400, 1000], nullable=False)
    player_career_national_win_prestige: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # «Золотой мяч»: monthly; minimum matches, prize coins and prestige.
    player_career_golden_ball_min_matches: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    player_career_golden_ball_coins: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    player_career_golden_ball_prestige: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Key moments in the player's league match (+1 with «Карьера Pro»).
    player_career_moments: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Key moment: +% success for a good timing hit.
    player_career_moment_hit_pct: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    # Key moments wait at most this long (or until the next round).
    player_career_moment_window_hours: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    # Rating this far below the club average = bench (unless the coach trusts him).
    player_career_bench_gap: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # A bench player comes on in this % of matches.
    player_career_bench_play_pct: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # Coach's trust that guarantees a starting place.
    player_career_trust_starter: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    # Coach's trust for the captain's armband (a starter at or above the club average).
    player_career_trust_captain: Mapped[int] = mapped_column(Integer, default=85, nullable=False)
    # Captain's salary bonus, %.
    player_career_captain_salary_pct: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Below this freshness a match can injure him.
    player_career_injury_freshness: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    # Injury chance at 0 freshness, % (linear to 0 at the threshold).
    player_career_injury_max_pct: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    # Heal an injury: coins (0 = not sold).
    player_career_heal_coins: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    # Heal an injury: Telegram Stars (0 = not sold).
    player_career_heal_stars: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    # Full freshness: coins (0 = not sold).
    player_career_refresh_coins: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # Full freshness: Telegram Stars (0 = not sold).
    player_career_refresh_stars: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Story events: at most one per this many rounds.
    player_career_event_every: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Story events: base coins (choices pay multiples).
    player_career_event_coins: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Story events: base prestige (choices give multiples).
    player_career_event_prestige: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Friends' league: reward multiplier for a derby (friend v friend).
    player_career_derby_multiplier: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # «Карьера Pro» pass: Telegram Stars (0 = not sold).
    player_career_pro_stars: Mapped[int] = mapped_column(Integer, default=299, nullable=False)
    # «Карьера Pro» pass length, days.
    player_career_pro_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # «Карьера Pro»: +% XP from career matches.
    player_career_pro_xp_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Agent for one transfer window: Telegram Stars (0 = not sold).
    player_career_agent_stars: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Agent: +% chance per counter-offer.
    player_career_agent_haggle_bonus: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Bring back a club that walked away: Telegram Stars (0 = not sold).
    player_career_save_offer_stars: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # Fast season on sale at all (off until the admin decides).
    player_career_fast_season_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Fast season: Telegram Stars (0 = not sold).
    player_career_fast_season_stars: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # Fast season: minutes between rounds.
    player_career_fast_round_minutes: Mapped[int] = mapped_column(Integer, default=120, nullable=False)
    # Daily career chest: coins from.
    player_career_chest_coins_min: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Daily career chest: coins up to.
    player_career_chest_coins_max: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    # Daily career chest: % chance of a skill token.
    player_career_chest_token_pct: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Weekly task: goals.
    player_career_weekly_goals: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Weekly task: matches.
    player_career_weekly_matches: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Weekly task: average rating x10 (70 = 7.0) over 5+ matches.
    player_career_weekly_rating_x10: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    # Weekly tasks rewards: goals, matches, rating.
    player_career_weekly_coins: Mapped[list] = mapped_column(JSON, default=lambda: [300, 200, 400], nullable=False)
    # Friends' league: coins for places 1-3 (friends only).
    player_career_friends_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [800, 500, 300], nullable=False)
    # «Менеджер» (manager_service / manager_shop): own clubs, money in club euros, the
    # 10-division pyramid, weekly seasons, the market of «Мои игроки» and footballers.
    manager_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    manager_found_cost: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    manager_min_level: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    manager_max_live: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    manager_squad_max: Mapped[int] = mapped_column(Integer, default=22, nullable=False)
    manager_league_size: Mapped[int] = mapped_column(Integer, default=16, nullable=False)
    manager_divisions: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    manager_promote: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    manager_preseason_hours: Mapped[int] = mapped_column(Integer, default=72, nullable=False)
    manager_style_edge_pct: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    manager_formation_effect_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    manager_wage_pct: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    manager_loan_fee_pct: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    manager_sell_back_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    manager_live_wage_max: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    manager_wage_eur_per_coin: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    manager_form_bonus_pct: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    manager_form_bonus_cap: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    manager_income_win: Mapped[int] = mapped_column(Integer, default=300000, nullable=False)
    manager_income_draw: Mapped[int] = mapped_column(Integer, default=150000, nullable=False)
    manager_income_loss: Mapped[int] = mapped_column(Integer, default=60000, nullable=False)
    manager_ticket_eur_per_level: Mapped[int] = mapped_column(Integer, default=20000, nullable=False)
    manager_sponsor_eur_per_level: Mapped[int] = mapped_column(Integer, default=100000, nullable=False)
    manager_merch_eur_per_level: Mapped[int] = mapped_column(Integer, default=60000, nullable=False)
    manager_budget_per_base_level: Mapped[int] = mapped_column(Integer, default=20000, nullable=False)
    manager_base_bonus_cap_pct: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    manager_promotion_bonus_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    manager_parachute_pct: Mapped[int] = mapped_column(Integer, default=33, nullable=False)
    manager_match_xp: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    manager_freshness_cost: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    manager_merch_cap_eur: Mapped[int] = mapped_column(Integer, default=15000000, nullable=False)
    manager_pro_stars: Mapped[int] = mapped_column(Integer, default=299, nullable=False)
    manager_pro_days: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    manager_value_ratings: Mapped[list] = mapped_column(JSON, default=lambda: [45, 50, 55, 60, 65, 70, 75, 80, 85, 90, 95], nullable=False)
    manager_value_eur: Mapped[list] = mapped_column(JSON, default=lambda: [50000, 80000, 150000, 400000, 1000000, 3500000, 12000000, 35000000, 80000000, 160000000, 220000000], nullable=False)
    manager_division_budget: Mapped[list] = mapped_column(JSON, default=lambda: [120000000, 70000000, 40000000, 22000000, 12000000, 7000000, 4500000, 3000000, 2500000, 2000000], nullable=False)
    manager_division_income_pct: Mapped[list] = mapped_column(JSON, default=lambda: [300, 250, 200, 170, 140, 120, 110, 100, 100, 100], nullable=False)
    manager_division_wage_pct: Mapped[list] = mapped_column(JSON, default=lambda: [180, 160, 140, 125, 115, 105, 100, 100, 100, 100], nullable=False)
    manager_division_rating: Mapped[list] = mapped_column(JSON, default=lambda: [80, 77, 74, 71, 68, 65, 63, 61, 59, 57], nullable=False)
    manager_place_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [1000, 600, 300], nullable=False)
    manager_place_budget: Mapped[list] = mapped_column(JSON, default=lambda: [3000000, 2000000, 1000000], nullable=False)
    manager_slots: Mapped[list] = mapped_column(JSON, default=lambda: ["13:00", "17:00", "21:00"], nullable=False)
    manager_cosmetics: Mapped[list] = mapped_column(JSON, default=lambda: [{"code": "shape_shield", "kind": "shape", "name": "Щит", "value": "shield", "coins": 0, "stars": 0}, {"code": "shape_circle", "kind": "shape", "name": "Круг", "value": "circle", "coins": 0, "stars": 0}, {"code": "shape_hexagon", "kind": "shape", "name": "Шестигранник", "value": "hexagon", "coins": 5000, "stars": 49}, {"code": "shape_crest", "kind": "shape", "name": "Герб", "value": "crest", "coins": 6000, "stars": 59}, {"code": "shape_crown", "kind": "shape", "name": "Корона", "value": "crown", "coins": 8000, "stars": 79}, {"code": "shape_diamond", "kind": "shape", "name": "Ромб", "value": "diamond", "coins": 0, "stars": 99}, {"code": "shape_star", "kind": "shape", "name": "Звезда", "value": "star", "coins": 0, "stars": 129}, {"code": "shape_castle", "kind": "shape", "name": "Замок", "value": "castle", "coins": 0, "stars": 149}, {"code": "symbol_ball", "kind": "symbol", "name": "Мяч", "value": "⚽", "coins": 0, "stars": 0}, {"code": "symbol_star", "kind": "symbol", "name": "Звезда", "value": "⭐", "coins": 0, "stars": 0}, {"code": "symbol_lion", "kind": "symbol", "name": "Лев", "value": "🦁", "coins": 4000, "stars": 39}, {"code": "symbol_eagle", "kind": "symbol", "name": "Орёл", "value": "🦅", "coins": 4000, "stars": 39}, {"code": "symbol_wolf", "kind": "symbol", "name": "Волк", "value": "🐺", "coins": 4000, "stars": 39}, {"code": "symbol_bear", "kind": "symbol", "name": "Медведь", "value": "🐻", "coins": 4000, "stars": 39}, {"code": "symbol_tiger", "kind": "symbol", "name": "Тигр", "value": "🐯", "coins": 5000, "stars": 49}, {"code": "symbol_bull", "kind": "symbol", "name": "Бык", "value": "🐂", "coins": 5000, "stars": 49}, {"code": "symbol_shark", "kind": "symbol", "name": "Акула", "value": "🦈", "coins": 5000, "stars": 49}, {"code": "symbol_horse", "kind": "symbol", "name": "Конь", "value": "🐎", "coins": 5000, "stars": 49}, {"code": "symbol_anchor", "kind": "symbol", "name": "Якорь", "value": "⚓", "coins": 6000, "stars": 59}, {"code": "symbol_bolt", "kind": "symbol", "name": "Молния", "value": "⚡", "coins": 0, "stars": 69}, {"code": "symbol_fire", "kind": "symbol", "name": "Пламя", "value": "🔥", "coins": 0, "stars": 79}, {"code": "symbol_rocket", "kind": "symbol", "name": "Ракета", "value": "🚀", "coins": 0, "stars": 89}, {"code": "symbol_dragon", "kind": "symbol", "name": "Дракон", "value": "🐉", "coins": 0, "stars": 129}, {"code": "symbol_crown", "kind": "symbol", "name": "Корона", "value": "👑", "coins": 0, "stars": 149}, {"code": "kit_plain", "kind": "kit", "name": "Однотонная", "value": "plain", "coins": 0, "stars": 0}, {"code": "kit_stripes", "kind": "kit", "name": "Полосы", "value": "stripes", "coins": 3000, "stars": 29}, {"code": "kit_hoops", "kind": "kit", "name": "Обручи", "value": "hoops", "coins": 3000, "stars": 29}, {"code": "kit_pinstripes", "kind": "kit", "name": "Тонкая полоса", "value": "pinstripes", "coins": 4000, "stars": 39}, {"code": "kit_halves", "kind": "kit", "name": "Половинки", "value": "halves", "coins": 5000, "stars": 49}, {"code": "kit_quarters", "kind": "kit", "name": "Четверти", "value": "quarters", "coins": 6000, "stars": 59}, {"code": "kit_sash", "kind": "kit", "name": "Диагональ", "value": "sash", "coins": 0, "stars": 69}, {"code": "kit_chevron", "kind": "kit", "name": "Шеврон", "value": "chevron", "coins": 0, "stars": 79}, {"code": "kit_checks", "kind": "kit", "name": "Клетка", "value": "checks", "coins": 0, "stars": 89}, {"code": "kit_gradient", "kind": "kit", "name": "Градиент", "value": "gradient", "coins": 0, "stars": 99}, {"code": "frame_classic", "kind": "frame", "name": "Классика", "value": "classic", "coins": 0, "stars": 0}, {"code": "frame_retro", "kind": "frame", "name": "Ретро", "value": "retro", "coins": 8000, "stars": 69}, {"code": "frame_ruby", "kind": "frame", "name": "Рубин", "value": "ruby", "coins": 0, "stars": 89}, {"code": "frame_ice", "kind": "frame", "name": "Лёд", "value": "ice", "coins": 0, "stars": 89}, {"code": "frame_neon", "kind": "frame", "name": "Неон", "value": "neon", "coins": 0, "stars": 99}, {"code": "frame_fire", "kind": "frame", "name": "Огонь", "value": "fire", "coins": 0, "stars": 119}, {"code": "frame_galaxy", "kind": "frame", "name": "Галактика", "value": "galaxy", "coins": 0, "stars": 149}, {"code": "frame_gold", "kind": "frame", "name": "Золото", "value": "gold", "coins": 0, "stars": 199}, {"code": "theme_night", "kind": "theme", "name": "Ночь", "value": "night", "coins": 0, "stars": 0}, {"code": "theme_ocean", "kind": "theme", "name": "Океан", "value": "ocean", "coins": 6000, "stars": 49}, {"code": "theme_forest", "kind": "theme", "name": "Лес", "value": "forest", "coins": 6000, "stars": 49}, {"code": "theme_sunset", "kind": "theme", "name": "Закат", "value": "sunset", "coins": 0, "stars": 79}, {"code": "theme_royal", "kind": "theme", "name": "Королевский", "value": "royal", "coins": 0, "stars": 99}, {"code": "theme_gold", "kind": "theme", "name": "Золотой", "value": "gold", "coins": 0, "stars": 149}, {"code": "stadium_name", "kind": "stadium_name", "name": "Имя стадиона", "value": "", "coins": 0, "stars": 199}], nullable=False)
    manager_merch: Mapped[list] = mapped_column(JSON, default=lambda: [{"code": "scarf", "name": "Шарф", "emoji": "🧣", "coins": 500, "eur": 300000}, {"code": "cap", "name": "Кепка", "emoji": "🧢", "coins": 800, "eur": 500000}, {"code": "shirt", "name": "Футболка", "emoji": "👕", "coins": 1500, "eur": 900000}, {"code": "ball", "name": "Мяч с автографами", "emoji": "⚽", "coins": 2500, "eur": 1500000}, {"code": "flag", "name": "Флаг на трибуну", "emoji": "🚩", "coins": 4000, "eur": 2500000}, {"code": "season_ticket", "name": "Абонемент", "emoji": "🎟️", "coins": 8000, "eur": 5000000}], nullable=False)
    # 10-division pyramid, weekly seasons, the market of «Мои игроки» and footballers.
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

    # Футбольное Стратего (see stratego_engine.py for the rules these drive).
    # board_size / move_limit / piece counts are snapshotted into each
    # match's server_state at creation, so edits never break a live match.
    # 8×8+ boards also get two 2×2 lakes in the middle (stratego_engine.default_lakes).
    stratego_board_size: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    stratego_wall_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    stratego_tackler_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    stratego_speedster_count: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    stratego_regular_count: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    # Total plies (both sides' moves together); reaching it ends the match on
    # remaining strength (sum of power of surviving mobile pieces).
    stratego_move_limit: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    # Squad composition rules over the card pieces (see stratego_service.rarity_violations).
    stratego_max_legendary_cards: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    stratego_max_diamond_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stratego_min_rare_cards: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    stratego_min_common_cards: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Highest card rarity allowed on the special-ability roles — a legendary
    # wall-breaker / star-killer / long-range scout makes those abilities
    # trivial. common/rare/epic/legendary/diamond.
    stratego_tackler_max_rarity: Mapped[str] = mapped_column(String(16), default="epic", nullable=False)
    stratego_provocateur_max_rarity: Mapped[str] = mapped_column(String(16), default="epic", nullable=False)
    stratego_speedster_max_rarity: Mapped[str] = mapped_column(String(16), default="epic", nullable=False)
    # Easy bot pays this % of the normal rewards (and a win is capped at +1 rating).
    stratego_bot_easy_reward_pct: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    # Matchmaking ("online") matches are played live: seconds per move.
    stratego_live_move_seconds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    # Card skill level × this = power bonus in a fight (attacking skills when
    # the piece attacks, defending skills when it is attacked).
    stratego_skill_bonus_per_level: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # «Задача дня» reward, paid once per local day.
    stratego_puzzle_reward: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # XP for «Мой игрок» per finished match it was fielded in (daily XP cap applies).
    stratego_my_player_xp: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    stratego_challenge_expiry_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    stratego_move_timeout_hours: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    # Consecutive timed-out moves auto-played for one side before that side
    # forfeits — keeps an absent player from being carried by the autopilot.
    stratego_max_auto_moves: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    stratego_reward_win: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    stratego_reward_draw: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    stratego_reward_loss: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    stratego_daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)

    # «Футбольный магнат» (rules in magnate_engine.py). Money here is the
    # in-match budget, not coins. Everything below except the rewards/limits
    # is snapshotted into a match at its start.
    magnate_start_money: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    magnate_pass_start_bonus: Mapped[int] = mapped_column(Integer, default=200, nullable=False)
    magnate_jail_fine: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Failed doubles attempts before the fine is forced and the player moves.
    magnate_max_jail_turns: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    magnate_fine_amount: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # % of a building's cost the bank pays back when it is sold to cover a debt.
    magnate_building_sell_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # Rounds (every player moves once) and wall-clock minutes; whichever ends
    # first decides the winner by capital (cash + property + buildings).
    magnate_max_rounds: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    magnate_time_limit_minutes: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    # Per decision; on timeout the autopilot plays the turn, and after this
    # many timed-out turns in a row a bot takes the seat for good.
    magnate_turn_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    magnate_max_missed_turns: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Public lobby: empty seats are filled with bots after this wait.
    magnate_lobby_wait_seconds: Mapped[int] = mapped_column(Integer, default=45, nullable=False)
    # Private room: starts with bots in the empty seats after this many
    # minutes if a friend joined, otherwise it is cancelled.
    magnate_room_wait_minutes: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    # Bot policy: buys when it keeps at least this much cash, builds likewise.
    magnate_bot_buy_reserve: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    magnate_bot_build_reserve: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    # Coins by final place (index 0 = 1st), within magnate_daily_limit
    # rewarded matches per day; the vs-bots mode pays magnate_bot_reward_pct %.
    magnate_place_rewards: Mapped[list] = mapped_column(JSON, default=lambda: [150, 75, 35, 10], nullable=False)
    magnate_bot_reward_pct: Mapped[int] = mapped_column(Integer, default=70, nullable=False)
    magnate_daily_limit: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Rent for owning 1..4 stadiums.
    magnate_stadium_rents: Mapped[list] = mapped_column(JSON, default=lambda: [25, 50, 100, 200], nullable=False)
    # NULL = magnate_engine.DEFAULT_BOARD / DEFAULT_CARDS.
    magnate_board: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    magnate_cards: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

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

    # «21: Добавленное время» (blackjack_service.py). Rewards themselves are
    # the golden/jackpot WheelPrize pools (admin «Колесо фортуны» page).
    # blackjack_paid_daily_limit = 0 turns paid entries off (free-only).
    blackjack_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    blackjack_free_per_day: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    blackjack_stars_cost: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    blackjack_paid_daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    blackjack_consolation_coins: Mapped[int] = mapped_column(Integer, default=25, nullable=False)

    # «Мордобой» (mordoboi_service.py): boxing on one card. Off by default.
    mordoboi_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    mordoboi_rounds: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    mordoboi_exchanges_per_round: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    mordoboi_base_hp: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    mordoboi_reward_win: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    mordoboi_reward_draw: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    mordoboi_reward_loss: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    mordoboi_reward_ko_bonus: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    mordoboi_daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    mordoboi_bot_easy_reward_pct: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    mordoboi_challenge_expiry_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    mordoboi_move_timeout_hours: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    mordoboi_live_move_seconds: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    mordoboi_max_auto_moves: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # «Контратака» (kontra_service.py): arena + weekly boss. Off by default.
    kontra_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    kontra_arena_reward_win: Mapped[int] = mapped_column(Integer, default=80, nullable=False)
    kontra_arena_reward_loss: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    kontra_daily_limit: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    kontra_rating_win: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    kontra_rating_loss: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    kontra_arena_max_rounds: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    kontra_boss_daily_attempts: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    kontra_boss_max_rounds: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    kontra_boss_week_hp: Mapped[int] = mapped_column(BigInteger, default=50_000_000, nullable=False)
    # Damage of one boss attempt -> coins: [[min damage, coins], …] ascending.
    kontra_boss_reward_tiers: Mapped[list] = mapped_column(
        JSON, default=lambda: [[0, 20], [20000, 50], [60000, 100], [150000, 200], [400000, 400]], nullable=False,
    )
    kontra_gear_drop_boss_pct: Mapped[int] = mapped_column(Integer, default=35, nullable=False)
    kontra_gear_drop_arena_pct: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    kontra_chest_coins: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    kontra_chest_stars: Mapped[int] = mapped_column(Integer, default=25, nullable=False)

    # «Легенда ринга»: the daily boss's rating and its once-a-day win reward.
    mordoboi_legend_rating: Mapped[int] = mapped_column(Integer, default=90, nullable=False)
    mordoboi_legend_reward: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    # «Клубный ринг»: war points for a «Мордобой» win over a member of the
    # club you're at war with, capped per member per war.
    club_ring_win_points: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    club_ring_member_cap: Mapped[int] = mapped_column(Integer, default=300, nullable=False)

    bingo_reward_coins: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bingo_reward_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    ptour_match_reward_win: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    ptour_match_reward_draw: Mapped[int] = mapped_column(Integer, default=40, nullable=False)
    ptour_match_reward_loss: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    # Tactics (Card Arena's, manager_tactics): the edge of the style that
    # beats the opponent's, % to every player, and the formation tilt, %.
    ptour_style_edge_pct: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    ptour_formation_effect_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
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

    # --- «Химия карточек» (services/chemistry_service.py) ---
    # Off = every mode keeps the old flat club/country bonus byte-for-byte.
    # On = Card Arena lineups, player-tournament squads and club squads use neighbour
    # links instead (FUT Draft always keeps its own formula). Only NEW
    # matches/rounds read it: an Arena match freezes its strengths at start,
    # player and club tournaments freeze the rules at their own start.
    chemistry_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Link value between two adjacent slots: same club AND country / one of them.
    chemistry_link_strong: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    chemistry_link_medium: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # A player's link sum reaching each threshold = +1 chemistry point.
    chemistry_threshold_1: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chemistry_threshold_2: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    chemistry_threshold_3: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    chemistry_player_max: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Minimum chemistry of an on-position player («пол для новичков»).
    chemistry_player_floor: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Match-rating points per chemistry point (the card's shown rating is untouched).
    chemistry_rating_per_point: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Extra match-rating penalty off the slot's ideal position (on top of the
    # existing 0.9/0.75 position fit, so 0 = no double penalty by default).
    chemistry_off_position_penalty: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Extra chemistry points (capped at chemistry_player_max) for an
    # on-position player whose country = the coach's (Coach.country) and
    # whose club = the stadium's (Stadium.club; home matches only).
    chemistry_coach_country_points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    chemistry_stadium_club_points: Mapped[int] = mapped_column(Integer, default=1, nullable=False)

    # --- «Звёзды карточек» (services/card_star_service.py) ---
    # Off = no new duplicates can be fed and no new stars claimed; stars
    # already earned keep their rating bonus either way (like card skills).
    card_stars_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    card_stars_max: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Duplicates of the same player needed for star 1, 2, 3 — per rarity.
    # Diamond is never listed: diamond cards have their own upgrade.
    card_star_dupes_per_level: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {"common": [10, 15, 25], "rare": [10, 15, 25], "epic": [10, 15, 25], "legendary": [10, 15, 25]},
    )
    # Coins charged when star 1, 2, 3 is claimed — per rarity.
    card_star_coin_cost: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {
            "common": [100, 200, 400], "rare": [300, 600, 1200], "epic": [1000, 2000, 4000],
            "legendary": [3000, 6000, 12000],
        },
    )
    card_star_rating_per_star: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Ceiling on the rating stars can add to one card (the card itself is
    # always kept at or below 99 on top of that).
    card_star_bonus_cap: Mapped[int] = mapped_column(Integer, default=6, nullable=False)

    # --- «Академия» (services/path_service.py, docs/path-cards.md) ---
    # Off = no new experience / purchases and talents give nothing in new
    # matches; levels already earned keep their rating bonus.
    path_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Shown name of the mechanic, its collection and its pack.
    path_title: Mapped[str] = mapped_column(String(64), default="Академия", nullable=False)
    # Experience to go from rating r to r+1: base + step * (r - start_rating).
    path_xp_base: Mapped[int] = mapped_column(Integer, default=75, nullable=False)
    path_xp_step: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    path_start_rating: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    path_rating_per_level: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Experience per match that earns it (same in every mode).
    path_xp_match: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    path_xp_win: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    path_xp_draw: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    path_xp_goal: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    path_xp_assist: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Per card per local day: free Card Arena attempts, and matches of the
    # career / player tournament that count (they never use Arena attempts).
    path_daily_free_arena: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    path_daily_career: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    path_daily_ptour: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Price of the 1st, 2nd, … extra Arena attempt bought for a card today;
    # the list length is the daily purchase limit per card.
    path_coin_attempt_prices: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [300, 400, 500, 600, 700],
    )
    path_stars_attempt_prices: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [3, 4, 5, 6, 7],
    )
    # Talents: ceiling on what all talents together add to one card in one
    # match (the match rating itself always stays <= 99).
    path_talent_cap: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    # Squad limits for path cards, separate from the diamond limits (a path
    # card does not take a diamond slot).
    match_max_path_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    tactico_max_path_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    stratego_max_path_cards: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # «Академия» prestige (services/path_prestige_service.py): duplicates of
    # the same player raise THIS copy's prestige tier — status, never rating.
    # Lists are per tier (their length = number of tiers).
    path_prestige_dupes: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: [1, 2, 3, 5])
    path_prestige_coins: Mapped[list] = mapped_column(JSON, nullable=False, default=lambda: [0, 0, 0, 0])
    path_prestige_names: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: ["Бронза", "Серебро", "Золото", "Икона"],
    )
    # One-off reward per tier reached: coins, bought Arena attempts, skill tokens.
    path_prestige_rewards: Mapped[list] = mapped_column(
        JSON, nullable=False,
        default=lambda: [
            {"coins": 300, "attempts": 1, "skill_tokens": 0}, {"coins": 600, "attempts": 2, "skill_tokens": 0},
            {"coins": 1000, "attempts": 3, "skill_tokens": 1}, {"coins": 2000, "attempts": 5, "skill_tokens": 2},
        ],
    )
    # Soft bonuses per tier: experience %, capped; free Arena attempts a day;
    # quick-sell price %.
    path_prestige_xp_pct: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    path_prestige_xp_cap_pct: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    path_prestige_free_attempts: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    path_prestige_sell_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    # One duplicate of the SAME player = this many spare copies of other
    # «Академия» players (prestige material exchange rate).
    path_prestige_other_ratio: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # «Академия» building (services/academy_service.py): per wing — coin cost,
    # build time in hours and the effect value at each level (list index =
    # level - 1). Effects: scout — +percentage points to the «Академия» card
    # chance of a slot in the «Академия» pack; training — +% path experience;
    # dorm — +free Card Arena attempts a day per card; staff — −% of stage
    # task targets; hall — +profile showcase slots.
    academy_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    academy_buildings: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {
            "scout": {"costs": [3000, 8000, 16000, 32000, 60000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 2, 2, 3]},
            "training": {"costs": [3000, 8000, 16000, 32000, 60000], "hours": [24, 48, 72, 120, 168], "effect": [2, 4, 6, 8, 10]},
            "dorm": {"costs": [4000, 10000, 20000, 40000, 75000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 1, 1, 2]},
            "staff": {"costs": [3500, 9000, 18000, 36000, 65000], "hours": [24, 48, 72, 120, 168], "effect": [3, 5, 7, 9, 12]},
            "hall": {"costs": [1500, 4000, 8000, 16000, 30000], "hours": [24, 48, 72, 120, 168], "effect": [1, 1, 2, 2, 3]},
        },
    )
    # --- Trade anti-farming (services/trade_service.py) ---
    # Coins in trades (either side) at all, and whether both sides must put
    # in at least one card (off = one-way card gifts allowed).
    trade_coins_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    trade_cards_both_sides: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # «Поиск обменов» (services/trade_finder_service.py): list sizes and how
    # recently a partner must have played to be suggested.
    trade_finder_max_wants: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    trade_finder_max_gives: Mapped[int] = mapped_column(Integer, default=20, nullable=False)
    trade_finder_active_days: Mapped[int] = mapped_column(Integer, default=7, nullable=False)
    # «У игрока появилась карточка из твоего «Ищу»»: at most one per wish per
    # this many hours (0 = notifications off).
    trade_finder_notify_hours: Mapped[int] = mapped_column(Integer, default=24, nullable=False)
    # Giving anything in a trade (coins or cards, on either side) needs an
    # account at least this many days old that was active on at least this
    # many distinct days (user_daily_activity). 0 = no requirement.
    trade_send_min_account_age_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    trade_send_min_active_days: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Max coins one player may receive through trades per local day (0 = no cap).
    trade_daily_coins_receive_cap: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    # Percent of the coin part of a trade burned on accept, paid by the
    # side that receives the coins (rounded up; 0 = no tax).
    trade_coin_tax_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Admin report «suspicious trade flows»: a giver counts as young if their
    # account was younger than this at trade time; a receiver is listed once
    # they took value from at least this many distinct young accounts.
    trade_suspicious_young_days: Mapped[int] = mapped_column(Integer, default=14, nullable=False)
    trade_suspicious_min_donors: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Stakes in open chat challenges (services/stake_guard_service.py): max
    # stake per side (0 = no stakes), staked matches the same pair may start
    # per day, and the daily cap on a player's net stake winnings (0 = off).
    stake_max_coins: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    stake_pair_daily_limit: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    stake_daily_profit_cap: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    # Shop sales boosters (migration 0183), 0 = off:
    # - pity_packs: a paid coin pack with a legendary chance that comes after
    #   this many such packs without a legendary turns one card legendary
    #   (User.pity_counter, pack_service.apply_pity);
    # - bulk10_discount_pct: discount on opening 10+ copies of a pack at once;
    # - first_coin_purchase_bonus_pct: extra coins on the player's first coin
    #   purchase for Stars (stars_payment_service).
    pity_packs: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    bulk10_discount_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    first_coin_purchase_bonus_pct: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    # Stars to finish a construction now: per started remaining hour (min 1).
    academy_stars_per_hour: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Free scouting report (scout wing >= 1), per scout level: chance of an
    # «Академия» card, days between reports, coins when no card was found.
    academy_scout_report: Mapped[dict] = mapped_column(
        JSON, nullable=False,
        default=lambda: {"chance_pct": [10, 12, 14, 16, 20], "cooldown_days": [10, 9, 8, 8, 7],
                         "consolation_coins": [100, 150, 200, 250, 300]},
    )
    # «Клубная база» (services/club_base_service.py): per building — coin
    # cost, build hours and named effect lists (index = level - 1). One
    # construction queue for the whole base, the «Академия» wings included.
    # Effects (see club_base_service.BUILDINGS): hq.cap — max level of every
    # other base building; stadium.matchday — coins per home league match of
    # «Карьера тренера» (capacity is shown only); hotel/marketing — +% to that
    # matchday income; training — +% familiarity growth (career) and +% XP of
    # «Мой игрок» trainings; medical — −% injury chance, +fatigue recovery;
    # analytics — +% to the «Разбор соперника»/«Стандарты» training effect;
    # media — +% positive reputation; marketing/shop — coins a day (sponsors,
    # merchandise); shop.sell_pct — +% quick-sell price; accounting — −% to
    # every construction cost. club_base_caps clamps each summed effect.
    club_base_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    club_base_buildings: Mapped[dict] = mapped_column(
        JSON, nullable=False, default=lambda: {k: dict(v) for k, v in DEFAULT_CLUB_BASE_BUILDINGS.items()},
    )
    club_base_caps: Mapped[dict] = mapped_column(JSON, nullable=False, default=lambda: dict(DEFAULT_CLUB_BASE_CAPS))
    club_base_stars_per_hour: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Sponsors/merchandise accrue at most this many days of income unclaimed.
    club_base_income_max_days: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # Admin art: {"background": path, "buildings": {code: path}} (static/
    # club_base/uploads); empty = the built-in drawn map.
    club_base_art: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict)
    # Stadium cosmetics shop (club_base_service.COSMETIC_KINDS): items bought
    # for coins and/or Stars; see DEFAULT_CLUB_BASE_COSMETICS.
    club_base_cosmetics: Mapped[list] = mapped_column(
        JSON, nullable=False, default=lambda: [dict(i) for i in DEFAULT_CLUB_BASE_COSMETICS],
    )

    # --- Monetization (models/monetization.py) ---------------------------
    # Monthly login calendar: catching up a missed day of the current month.
    # 0 = that currency is off.
    calendar_catchup_coins: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    calendar_catchup_stars: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    calendar_catchup_max_per_month: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # «Клубный абонемент» (monthly Stars subscription) and its perks.
    # Off until an admin sets it up and launches it.
    club_pass_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    club_pass_stars: Mapped[int] = mapped_column(Integer, default=199, nullable=False)
    club_pass_daily_coins: Mapped[int] = mapped_column(Integer, default=300, nullable=False)
    club_pass_daily_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    club_pass_extra_rewarded_attempts: Mapped[int] = mapped_column(Integer, default=2, nullable=False)
    # Granted with every paid month (first payment and each renewal).
    club_pass_bonus_coins: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    club_pass_bonus_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    club_pass_bonus_card_rarity: Mapped[Optional[str]] = mapped_column(String(16), nullable=True, default="epic")
    # +% season pass XP while subscribed; free calendar catch-ups a month.
    club_pass_season_xp_bonus_pct: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    club_pass_free_catchups: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    # «Статус» of «Мой игрок» while the pass is active / with the current
    # season's premium track (lifestyle_service.extra_prestige).
    club_pass_status: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    season_premium_status: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    club_pass_frame_cosmetic_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    club_pass_badge_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Reserved for when ads exist: subscribers won't see them.
    club_pass_ad_free: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # «Сезонный пропуск»: XP per rewarded game and per calendar claim.
    season_pass_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    season_xp_per_game: Mapped[int] = mapped_column(Integer, default=10, nullable=False)
    season_xp_per_daily_claim: Mapped[int] = mapped_column(Integer, default=25, nullable=False)
    # One-time starter offer for new players.
    starter_offer_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starter_offer_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    starter_offer_stars: Mapped[int] = mapped_column(Integer, default=50, nullable=False)
    starter_offer_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    starter_offer_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    starter_offer_cosmetic_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # «Для всех, кто не купил»: also players older than starter_offer_hours get
    # it, with their window counted from starter_offer_all_since (stamped by
    # the admin endpoint when the switch goes on), so a launch is one
    # campaign with one deadline for the existing players.
    starter_offer_for_all: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    starter_offer_all_since: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    # «Артефакты» (club / «Мой игрок»): off until an admin launches them; active slots
    # and per-effect caps on the summed bonus (see artifact_service.EFFECTS).
    artifacts_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    artifact_slots: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    artifact_max_opp_pct: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    artifact_max_stat: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    # Club emblem constructor (club_emblem_service): prices live on the
    # club_emblem_items catalog; this only switches the shop off.
    club_emblems_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # «Казна за Stars»: any member tops up the club budget. Coins per Star,
    # the Stars amounts offered, and the total Stars for the silver / gold
    # sponsor badge (any donation at all = bronze). Off until launched.
    club_donation_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    club_donation_coins_per_star: Mapped[int] = mapped_column(Integer, default=15, nullable=False)
    club_donation_star_options: Mapped[list] = mapped_column(
        JSON, default=lambda: [25, 50, 100, 250, 500], nullable=False,
    )
    club_sponsor_silver_stars: Mapped[int] = mapped_column(Integer, default=250, nullable=False)
    club_sponsor_gold_stars: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    # «Лишние карты» клуба (club_market_service): sell a non-squad club card
    # into the budget for Player.quick_sell_price x this %, or exchange N of
    # one rarity for one of the next.
    club_card_market_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    club_card_sell_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    club_card_exchange_count: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Club pack the spare cards are burned for; None = the cheapest active club pack.
    club_card_exchange_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # «Стена клуба»: one bot-delivered announcement per club per this many minutes.
    club_announcement_cooldown_minutes: Mapped[int] = mapped_column(Integer, default=60, nullable=False)
    # «Задания недели» клуба (club_quest_service; the quests themselves are club_quest_templates).
    club_quests_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # «Лига клубов» divisions (Бронза → Серебро → Золото): a season is this
    # many league weeks; at its end the top N of a division go up and the
    # bottom N go down. Weekly prizes are club_league_rewards x the division %.
    club_league_season_weeks: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    club_league_promote_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_league_relegate_count: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_league_division_reward_pct: Mapped[list] = mapped_column(
        JSON, default=lambda: [100, 150, 200], nullable=False,
    )
    # «Клубные войны» (club_war_service): weekly 48-hour club-vs-club, start
    # weekday 0=Mon..6=Sun / hour in the app timezone; prizes into the budget,
    # winners' members each claim `club_war_win_member_coins`.
    club_war_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    club_war_start_weekday: Mapped[int] = mapped_column(Integer, default=4, nullable=False)
    club_war_start_hour: Mapped[int] = mapped_column(Integer, default=18, nullable=False)
    club_war_duration_hours: Mapped[int] = mapped_column(Integer, default=48, nullable=False)
    club_war_min_members: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_war_member_cap: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    club_war_win_budget: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    club_war_draw_budget: Mapped[int] = mapped_column(Integer, default=1500, nullable=False)
    club_war_loss_budget: Mapped[int] = mapped_column(Integer, default=500, nullable=False)
    club_war_win_member_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    # --- «Экипировка» (services/equipment_service.py) ---
    # Off = the shop and equipping are closed and worn things give nothing.
    equipment_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Ceilings on what all things worn by ONE card add up to (set bonus included).
    equipment_max_rating: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    equipment_max_pp: Mapped[int] = mapped_column(Integer, default=8, nullable=False)
    equipment_max_chemistry: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    # Ceiling on what talismans add per card (+% «Академия» experience, +% coins for an Arena win).
    equipment_max_talisman_pct: Mapped[int] = mapped_column(Integer, default=15, nullable=False)

    # --- «Музы» (services/muse_service.py) ---
    # Off = Muse bonuses stop, gifts and the daily claim close, the pack drops footballers only.
    muses_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # Ceilings on the active Muse's bonus (accessories included).
    muse_max_stat: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    muse_max_pp: Mapped[int] = mapped_column(Integer, default=12, nullable=False)
    muse_max_xp_pct: Mapped[int] = mapped_column(Integer, default=30, nullable=False)
    muse_max_daily_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    # Ceiling on what all gifts of one Muse add, in percent.
    muse_max_accessory_pct: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    # «Свидание»: once a day a random mini-game with the Muse on an extra
    # attempt (no hourly / daily limits burnt, any result counts).
    muse_date_games: Mapped[list] = mapped_column(JSON, default=lambda: ["memory", "pairs", "hangman"], nullable=False)
    muse_date_coins: Mapped[int] = mapped_column(Integer, default=150, nullable=False)
    # On = her bonus works only while inspired by a date (for this many hours).
    muse_date_required: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    muse_inspiration_hours: Mapped[int] = mapped_column(Integer, default=36, nullable=False)
    # Coins for one spare copy of a Muse, by rarity.
    muse_spare_coins: Mapped[dict] = mapped_column(
        JSON, default=lambda: {"common": 150, "rare": 400, "epic": 1000, "legendary": 3000}, nullable=False,
    )

    # --- «Неделя мини-игры» (services/weekly_cup_service.py) ---
    weekly_cup_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    # Rotation by week: penalty | free_kick | memory | saboteur | pairs.
    weekly_cup_games: Mapped[list] = mapped_column(
        JSON, default=lambda: ["penalty", "free_kick", "memory", "saboteur", "pairs"], nullable=False,
    )
    # The score is the sum of a player's N best games of the week.
    weekly_cup_best_of: Mapped[int] = mapped_column(Integer, default=5, nullable=False)
    # Coins for places 1, 2, 3, …
    weekly_cup_prizes: Mapped[list] = mapped_column(
        JSON, default=lambda: [5000, 3000, 2000, 1000, 1000, 500, 500, 500, 500, 500], nullable=False,
    )

    # --- «Матч дня» (services/match_day_service.py) ---
    match_day_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    match_day_exact_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    match_day_diff_coins: Mapped[int] = mapped_column(Integer, default=400, nullable=False)
    match_day_outcome_coins: Mapped[int] = mapped_column(Integer, default=200, nullable=False)

    # --- «Клубный рейд» (services/club_raid_service.py) ---
    club_raid_enabled: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    club_raid_hp_per_member: Mapped[int] = mapped_column(Integer, default=3000, nullable=False)
    club_raid_attacks_per_day: Mapped[int] = mapped_column(Integer, default=3, nullable=False)
    club_raid_shots: Mapped[int] = mapped_column(Integer, default=6, nullable=False)
    club_raid_damage_per_goal: Mapped[int] = mapped_column(Integer, default=100, nullable=False)
    club_raid_reward_coins: Mapped[int] = mapped_column(Integer, default=1000, nullable=False)
    club_raid_reward_pack_id: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    club_raid_reward_budget: Mapped[int] = mapped_column(Integer, default=2000, nullable=False)
    # Automatic matches from API-Football (services/match_day_auto.py, key in API_FOOTBALL_KEY):
    # the bot picks the best upcoming match by league priority and fetches its score.
    match_day_auto_enabled: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    # API-Football league ids, most wanted first (2 ЛЧ, 39 АПЛ, 140 Ла Лига, 235 РПЛ, …).
    match_day_leagues: Mapped[list] = mapped_column(
        JSON, default=lambda: [2, 39, 140, 235, 135, 78, 61, 3, 848, 1, 4], nullable=False,
    )
    match_day_auto_status: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    match_day_auto_checked_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
