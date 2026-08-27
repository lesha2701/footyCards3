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
    card_upgrade = "card_upgrade"
    collection_reward = "collection_reward"
    stars_purchase = "stars_purchase"
    chat_pack = "chat_pack"
    gift = "gift"
    wheel = "wheel"
    league_reward = "league_reward"


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
    card_upgrade = "card_upgrade"
    referral_reward = "referral_reward"
    collection_reward = "collection_reward"
    tactico_reward = "tactico_reward"
    stars_coin_purchase = "stars_coin_purchase"
    stars_pack_bonus_coins = "stars_pack_bonus_coins"
    gift_coins = "gift_coins"
    wheel_spin_cost = "wheel_spin_cost"
    wheel_spin_reward = "wheel_spin_reward"
    league_reward = "league_reward"
    gift_purchase_coins = "gift_purchase_coins"
    premium_subscription_adjustment = "premium_subscription_adjustment"


class GiftKind(str, enum.Enum):
    bundle = "bundle"
    collectible = "collectible"


class ClubRole(str, enum.Enum):
    captain = "captain"
    assistant = "assistant"
    member = "member"


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


class ClubCardSource(str, enum.Enum):
    starter_seed = "starter_seed"
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


class PenaltyOpponentType(str, enum.Enum):
    friend = "friend"
    online = "online"


class TacticoMatchStatus(str, enum.Enum):
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
