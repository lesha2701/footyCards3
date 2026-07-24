import enum


class Rarity(str, enum.Enum):
    common = "common"
    rare = "rare"
    epic = "epic"
    legendary = "legendary"


RARITY_ORDER = {Rarity.common: 0, Rarity.rare: 1, Rarity.epic: 2, Rarity.legendary: 3}


class Position(str, enum.Enum):
    GK = "GK"
    LB = "LB"
    CB = "CB"
    RB = "RB"
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
    admin_adjustment = "admin_adjustment"
    task_reward = "task_reward"


class TaskCategory(str, enum.Enum):
    regular = "regular"
    premium = "premium"


class TaskConditionType(str, enum.Enum):
    metric_counter = "metric_counter"
    match_min_rating = "match_min_rating"


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


class NotificationType(str, enum.Enum):
    trade_offer_received = "trade_offer_received"
    trade_offer_accepted = "trade_offer_accepted"
    trade_offer_rejected = "trade_offer_rejected"
    trade_offer_cancelled = "trade_offer_cancelled"
    trade_offer_expired = "trade_offer_expired"
    daily_reward_available = "daily_reward_available"
    special_pack = "special_pack"
    admin_message = "admin_message"
    premium_task_available = "premium_task_available"


class TradeCardSide(str, enum.Enum):
    offered = "offered"
    requested = "requested"
