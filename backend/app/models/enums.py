import enum


class Rarity(str, enum.Enum):
    common = "common"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"
    diamond = "diamond"


RARITY_ORDER = {Rarity.common: 0, Rarity.rare: 1, Rarity.epic: 2, Rarity.legendary: 3, Rarity.diamond: 4}


class CoachBoostType(str, enum.Enum):
    ATTACK_CENTRAL = "attack_central"
    ATTACK_WING = "attack_wing"
    MIDFIELD_CONTROL = "midfield_control"
    DEFENCE_CENTRAL = "defence_central"
    DEFENCE_WING = "defence_wing"
    GOALKEEPING = "goalkeeping"
    PASSING_ACCURACY = "passing_accuracy"
    BALL_CONTROL = "ball_control"
    DEFENSIVE_DISCIPLINE = "defensive_discipline"
    COUNTER_MASTERY = "counter_mastery"
    SQUAD_STABILITY = "squad_stability"


class Position(str, enum.Enum):
    GK = "GK"
    LB = "LB"
    CB = "CB"
    RB = "RB"
    # Wing-backs: defenders (DEF line), interchangeable with LB/RB for
    # "on position" (lineup_service.on_ideal_position).
    LWB = "LWB"
    RWB = "RWB"
    CDM = "CDM"
    CM = "CM"
    CAM = "CAM"
    LM = "LM"
    RM = "RM"
    LW = "LW"
    RW = "RW"
    ST = "ST"


class CardSource(str, enum.Enum):
    pack = "pack"
    daily_reward = "daily_reward"
    trade = "trade"
    admin_grant = "admin_grant"
    achievement = "achievement"
    game_reward = "game_reward"
    seed = "seed"
    task = "task"
    free_pack = "free_pack"
    card_upgrade = "card_upgrade"
    collection_reward = "collection_reward"
    stars_purchase = "stars_purchase"
    chat_pack = "chat_pack"
    gift = "gift"
    wheel = "wheel"
    league_reward = "league_reward"
    club_reward = "club_reward"


class TransactionType(str, enum.Enum):
    starting_balance = "starting_balance"
    daily_reward = "daily_reward"
    pack_purchase = "pack_purchase"
    card_sale = "card_sale"
    game_reward = "game_reward"
    match_reward = "match_reward"
    achievement_reward = "achievement_reward"
    trade_coins_sent = "trade_coins_sent"
    trade_coins_received = "trade_coins_received"
    trade_coin_tax = "trade_coin_tax"
    admin_adjustment = "admin_adjustment"
    task_reward = "task_reward"
    card_upgrade = "card_upgrade"
    referral_reward = "referral_reward"
    collection_reward = "collection_reward"
    tactico_reward = "tactico_reward"
    stars_coin_purchase = "stars_coin_purchase"
    stars_pack_bonus_coins = "stars_pack_bonus_coins"
    gift_coins = "gift_coins"
    wheel_spin_cost = "wheel_spin_cost"
    wheel_spin_reward = "wheel_spin_reward"
    fut_draft_entry = "fut_draft_entry"
    league_reward = "league_reward"
    gift_purchase_coins = "gift_purchase_coins"
    premium_subscription_adjustment = "premium_subscription_adjustment"
    bingo_reward = "bingo_reward"
    club_tournament_match_reward = "club_tournament_match_reward"
    player_tournament_match_reward = "player_tournament_match_reward"
    player_tournament_place_reward = "player_tournament_place_reward"
    tactico_stake_lock = "tactico_stake_lock"
    tactico_stake_win = "tactico_stake_win"
    tactico_stake_refund = "tactico_stake_refund"
    penalty_stake_lock = "penalty_stake_lock"
    penalty_stake_win = "penalty_stake_win"
    penalty_stake_refund = "penalty_stake_refund"
    card_skill_purchase = "card_skill_purchase"
    career_reward = "career_reward"
    my_player_cosmetic = "my_player_cosmetic"
    my_player_extra_training = "my_player_extra_training"
    lifestyle_purchase = "lifestyle_purchase"
    player_career_reward = "player_career_reward"
    stratego_reward = "stratego_reward"
    stratego_stake_lock = "stratego_stake_lock"
    stratego_stake_win = "stratego_stake_win"
    stratego_stake_refund = "stratego_stake_refund"
    mordoboi_reward = "mordoboi_reward"
    mordoboi_stake_lock = "mordoboi_stake_lock"
    mordoboi_stake_win = "mordoboi_stake_win"
    mordoboi_stake_refund = "mordoboi_stake_refund"
    mordoboi_brutality_bonus = "mordoboi_brutality_bonus"
    mordoboi_legend_reward = "mordoboi_legend_reward"
    blackjack_consolation = "blackjack_consolation"
    magnate_reward = "magnate_reward"
    card_star_upgrade = "card_star_upgrade"
    path_attempt_purchase = "path_attempt_purchase"
    path_prestige = "path_prestige"
    path_prestige_reward = "path_prestige_reward"
    academy_upgrade = "academy_upgrade"
    academy_scout_reward = "academy_scout_reward"
    club_base_upgrade = "club_base_upgrade"
    club_base_income = "club_base_income"
    club_base_matchday = "club_base_matchday"
    club_base_cosmetic = "club_base_cosmetic"
    arena_division_reward = "arena_division_reward"
    my_player_duel_reward = "my_player_duel_reward"
    my_player_role_change = "my_player_role_change"
    manager_club_found = "manager_club_found"
    manager_salary = "manager_salary"
    manager_reward = "manager_reward"
    manager_cosmetic = "manager_cosmetic"
    manager_merch = "manager_merch"
    lifestyle_income = "lifestyle_income"
    calendar_catchup = "calendar_catchup"
    cosmetic_purchase = "cosmetic_purchase"
    club_pass_reward = "club_pass_reward"
    season_pass_reward = "season_pass_reward"
    starter_offer_reward = "starter_offer_reward"
    artifact_purchase = "artifact_purchase"
    equipment_purchase = "equipment_purchase"
    muse_daily_coins = "muse_daily_coins"
    muse_accessory_purchase = "muse_accessory_purchase"
    muse_spare_sale = "muse_spare_sale"
    muse_date_reward = "muse_date_reward"
    club_reward = "club_reward"
    weekly_cup_prize = "weekly_cup_prize"
    match_day_reward = "match_day_reward"


class GiftKind(str, enum.Enum):
    bundle = "bundle"
    collectible = "collectible"


class ClubRole(str, enum.Enum):
    captain = "captain"
    assistant = "assistant"
    member = "member"
    # One per club: a manager who also edits the emblem and takes over
    # first when the captain leaves.
    vice_captain = "vice_captain"
    # One per club: may spend the club budget (packs, emblem, spare cards)
    # without squad/membership powers.
    treasurer = "treasurer"


class ClubType(str, enum.Enum):
    open = "open"
    closed = "closed"


class ClubJoinRequestStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"


class ClubBudgetTransactionType(str, enum.Enum):
    daily_claim = "daily_claim"
    pack_purchase = "pack_purchase"
    tournament_reward = "tournament_reward"
    club_game_reward = "club_game_reward"
    club_missing_item_reward = "club_missing_item_reward"
    club_penalty_reward = "club_penalty_reward"
    tournament_match_reward = "tournament_match_reward"
    # Zero writers left anywhere in the codebase — the dedicated ClubCoachPack system
    # that produced this value was removed (see 0095_drop_club_coach_packs.py). Do NOT
    # delete this member: Postgres cannot drop a single enum value once added, so the
    # real DB enum still carries 'coach_pack_purchase' and removing the Python member
    # would break parity with it.
    coach_pack_purchase = "coach_pack_purchase"
    admin_adjustment = "admin_adjustment"
    club_position_match_reward = "club_position_match_reward"
    league_reward = "league_reward"
    stars_donation = "stars_donation"
    emblem_purchase = "emblem_purchase"
    card_sale = "card_sale"
    shop_purchase = "shop_purchase"
    quest_reward = "quest_reward"
    war_reward = "war_reward"
    raid_reward = "raid_reward"


class TournamentQueueStatus(str, enum.Enum):
    open = "open"
    formed = "formed"


class TournamentStatus(str, enum.Enum):
    active = "active"
    completed = "completed"


class ClubCardAvailabilityReason(str, enum.Enum):
    red_card = "red_card"
    injury = "injury"


class ClubCardSource(str, enum.Enum):
    starter_seed = "starter_seed"
    club_pack = "club_pack"
    exchange = "exchange"


class ClubCoachCardSource(str, enum.Enum):
    club_pack = "club_pack"


class ClubStadiumCardSource(str, enum.Enum):
    club_pack = "club_pack"


class ClubLogoShape(str, enum.Enum):
    shield = "shield"
    circle = "circle"
    hexagon = "hexagon"
    star = "star"
    diamond = "diamond"
    banner = "banner"
    crest = "crest"
    chevron = "chevron"


class TaskCategory(str, enum.Enum):
    regular = "regular"
    premium = "premium"


class TaskConditionType(str, enum.Enum):
    metric_counter = "metric_counter"
    match_min_rating = "match_min_rating"
    match_same_country = "match_same_country"
    penalty_win_max_rating = "penalty_win_max_rating"


class TradeStatus(str, enum.Enum):
    pending = "pending"
    accepted = "accepted"
    rejected = "rejected"
    cancelled = "cancelled"
    expired = "expired"


class GameType(str, enum.Enum):
    memory_sequence = "memory_sequence"
    card_arena = "card_arena"
    saboteur = "saboteur"
    penalty = "penalty"
    free_kick = "free_kick"
    football_hangman = "football_hangman"
    card_pairs = "card_pairs"
    # Retired the same day it shipped — moved into the club games instead
    # (see club_position_match below). Zero writers left; kept only because
    # Postgres cannot drop a single enum value once added (same precedent as
    # ClubBudgetTransactionType.coach_pack_purchase).
    position_match = "position_match"
    club_sequence = "club_sequence"
    club_missing_item = "club_missing_item"
    club_penalty = "club_penalty"
    club_position_match = "club_position_match"
    fut_draft = "fut_draft"


class GameSessionStatus(str, enum.Enum):
    in_progress = "in_progress"
    won = "won"
    lost = "lost"
    rewarded = "rewarded"
    expired = "expired"


class MatchDifficulty(str, enum.Enum):
    easy = "easy"
    medium = "medium"
    hard = "hard"


class MatchResult(str, enum.Enum):
    win = "win"
    draw = "draw"
    loss = "loss"


class MatchStatus(str, enum.Enum):
    in_progress = "in_progress"
    finished = "finished"


class TacticoOpponentType(str, enum.Enum):
    bot = "bot"
    friend = "friend"
    online = "online"
    chat = "chat"


class PenaltyOpponentType(str, enum.Enum):
    friend = "friend"
    online = "online"
    chat = "chat"


class TacticoMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


class StrategoOpponentType(str, enum.Enum):
    bot = "bot"
    friend = "friend"
    online = "online"
    chat = "chat"


class StrategoMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


class MordoboiOpponentType(str, enum.Enum):
    bot = "bot"
    friend = "friend"
    online = "online"
    # Open challenge shared into a Telegram chat: whoever accepts first plays.
    chat = "chat"


class MordoboiMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


class PenaltyMatchStatus(str, enum.Enum):
    pending_accept = "pending_accept"
    in_progress = "in_progress"
    finished = "finished"
    declined = "declined"
    cancelled = "cancelled"
    expired = "expired"


class NotificationType(str, enum.Enum):
    trade_offer_received = "trade_offer_received"
    trade_offer_accepted = "trade_offer_accepted"
    trade_offer_rejected = "trade_offer_rejected"
    trade_offer_cancelled = "trade_offer_cancelled"
    trade_offer_expired = "trade_offer_expired"
    trade_wish_available = "trade_wish_available"
    club_donation = "club_donation"
    club_member_joined = "club_member_joined"
    club_announcement = "club_announcement"
    club_reward_available = "club_reward_available"
    club_league_promoted = "club_league_promoted"
    club_league_relegated = "club_league_relegated"
    club_war_started = "club_war_started"
    club_war_finished = "club_war_finished"
    club_base_built = "club_base_built"
    daily_reward_available = "daily_reward_available"
    special_pack = "special_pack"
    admin_message = "admin_message"
    premium_task_available = "premium_task_available"
    referral_joined = "referral_joined"
    collection_completed = "collection_completed"
    tactico_challenge_received = "tactico_challenge_received"
    tactico_challenge_accepted = "tactico_challenge_accepted"
    tactico_challenge_declined = "tactico_challenge_declined"
    tactico_challenge_cancelled = "tactico_challenge_cancelled"
    tactico_challenge_expired = "tactico_challenge_expired"
    tactico_your_turn = "tactico_your_turn"
    tactico_match_finished = "tactico_match_finished"
    penalty_challenge_received = "penalty_challenge_received"
    penalty_challenge_accepted = "penalty_challenge_accepted"
    penalty_challenge_declined = "penalty_challenge_declined"
    penalty_challenge_cancelled = "penalty_challenge_cancelled"
    penalty_challenge_expired = "penalty_challenge_expired"
    trophy_granted = "trophy_granted"
    league_promoted = "league_promoted"
    club_join_request_received = "club_join_request_received"
    club_join_request_accepted = "club_join_request_accepted"
    club_join_request_rejected = "club_join_request_rejected"
    club_role_changed = "club_role_changed"
    club_kicked = "club_kicked"
    club_captain_transferred = "club_captain_transferred"
    club_match = "club_match"
    club_lineup_reminder = "club_lineup_reminder"
    player_tournament_match = "player_tournament_match"
    player_tournament_results_ready = "player_tournament_results_ready"
    player_tournament_reminder = "player_tournament_reminder"
    club_tournament_results_ready = "club_tournament_results_ready"
    club_tournament_apply_available = "club_tournament_apply_available"
    premium_task_coins_withdrawn = "premium_task_coins_withdrawn"
    premium_task_coins_restored = "premium_task_coins_restored"
    club_activity_reminder = "club_activity_reminder"
    friend_request = "friend_request"
    friend_accepted = "friend_accepted"
    career_invite = "career_invite"
    career_round_result = "career_round_result"
    career_season_finished = "career_season_finished"
    career_reminder = "career_reminder"
    career_digest = "career_digest"
    player_career_round_result = "player_career_round_result"
    player_career_season_finished = "player_career_season_finished"
    club_league_reward = "club_league_reward"
    stratego_challenge_received = "stratego_challenge_received"
    stratego_challenge_accepted = "stratego_challenge_accepted"
    stratego_your_turn = "stratego_your_turn"
    stratego_match_finished = "stratego_match_finished"
    mordoboi_challenge_received = "mordoboi_challenge_received"
    mordoboi_challenge_accepted = "mordoboi_challenge_accepted"
    mordoboi_your_turn = "mordoboi_your_turn"
    mordoboi_match_finished = "mordoboi_match_finished"
    mordoboi_brutality = "mordoboi_brutality"
    mordoboi_helmet = "mordoboi_helmet"
    my_player_duel = "my_player_duel"
    player_career_event = "player_career_event"
    manager_event = "manager_event"
    weekly_cup_result = "weekly_cup_result"
    match_day_result = "match_day_result"


class TradeCardSide(str, enum.Enum):
    offered = "offered"
    requested = "requested"


class WheelPrizeType(str, enum.Enum):
    coins = "coins"
    pack = "pack"
    card_rarity = "card_rarity"
    badge = "badge"


class WheelSpinSource(str, enum.Enum):
    free = "free"
    coins = "coins"
    stars = "stars"
    # Reward spin won in «21: Добавленное время» (golden/jackpot pools).
    blackjack = "blackjack"


class WheelPrizePool(str, enum.Enum):
    """Which wheel a WheelPrize belongs to. regular = the classic «Колесо
    фортуны» (WheelPage); golden/jackpot = the reward wheels of «21» (a win
    / a natural «Хет-трик»)."""

    regular = "regular"
    golden = "golden"
    jackpot = "jackpot"


class BingoGoalType(str, enum.Enum):
    """A weekly Bingo goal's metric. New game types are added here, plus one
    increment call at the relevant event site — see bingo_service.py."""

    packs_opened = "packs_opened"
    rare_drops = "rare_drops"
    epic_drops = "epic_drops"
    legendary_drops = "legendary_drops"
    tactico_matches_played = "tactico_matches_played"
    penalty_matches_played = "penalty_matches_played"
    arena_matches_played = "arena_matches_played"
    trades_completed = "trades_completed"
