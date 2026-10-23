from app.models.admin_action import AdminAction
from app.models.badge import Badge, UserBadge
from app.models.blackjack import BlackjackMatch
from app.models.card import CardStarLedger, UserCard
from app.models.card_path import AcademyLedger, UserAcademy, CardPath, PathAttemptPurchase, PathPrestigeLedger, PathStage, PathStageTask, PathTalent, PathXpEvent
from app.models.card_skill import CardSkill, CardSkillLedger, UserSkillToken
from app.models.career import CareerClub, CareerParticipant, CareerProfile, CareerSeason, Friendship
from app.models.lifestyle import LifestyleItem, UserLifestyleItem
from app.models.club_base import ClubBaseLedger, UserBaseCosmetic, UserClubBase
from app.models.manager_club import (
    ManagerClub,
    ManagerContract,
    ManagerCosmetic,
    ManagerLeague,
    ManagerMerch,
    ManagerNpc,
    ManagerSeason,
    ManagerValueHistory,
)
from app.models.my_player import MyPlayer, MyPlayerDuel
from app.models.player_career import (
    PlayerCareerCup,
    PlayerCareerGoldenBall,
    PlayerCareerMonthStat,
    PlayerCareerSeason,
    PlayerCareerClubRecord,
    PlayerCareerFriendLeague,
    PlayerCareerFriendMember,
    PlayerCareerWeekStat,
    PlayerCareerWeeklyClaim,
)
from app.models.card_collection import CardCollection, UserCollectionReward
from app.models.card_upgrade import CardUpgradeAttempt, CardUpgradeRule
from app.models.club import Club, ClubJoinRequest, ClubMember
from app.models.club_budget import ClubBudgetTransaction
from app.models.club_card import ClubCard
from app.models.club_card_availability import ClubCardAvailability
from app.models.club_coach_card import ClubCoachCard
from app.models.club_daily_claim import ClubDailyClaim
from app.models.club_emblem import ClubDonation, ClubEmblemItem, ClubEmblemUnlock, ClubStarTransaction
from app.models.club_wall import ClubPost
from app.models.club_reward import ClubRewardClaim, ClubRewardGrant, ClubShopItem, ClubShopPurchase
from app.models.club_quest import ClubQuestCompletion, ClubQuestTemplate
from app.models.weekly_event import (
    ClubRaid,
    ClubRaidAttack,
    MatchDayFixture,
    MatchDayPrediction,
    WeeklyCupResult,
    WeeklyCupWeek,
)
from app.models.club_war import ClubWar, ClubWarRound
from app.models.club_league import ClubLeagueResult, ClubLeagueWeek, ClubSeasonResult
from app.models.club_lineup import ClubLineup, ClubLineupCard
from app.models.club_pack import ClubPack, ClubPackRarityProbability
from app.models.club_pack_opening import ClubPackOpening, ClubPackOpeningCard
from app.models.coach import Coach, CoachBoost
from app.models.coin_package import CoinPackage
from app.models.daily_reward import DailyReward
from app.models.game import GameSession, MemoryGameRound
from app.models.game_config import GameConfig
from app.models.gift import Gift, GiftSet
from app.models.league import LeagueTier, UserLeagueRewardClaim
from app.models.lineup import Lineup, LineupCard
from app.models.match import Match, MatchEvent
from app.models.notification import Notification
from app.models.pack import Pack, PackOpening, PackOpeningCard, PackRarityProbability, StarsInvoice
from app.models.penalty import PenaltyMatch
from app.models.personal_squad import PersonalSquad, PersonalSquadCard
from app.models.player_tournament import (
    PlayerTournament, PlayerTournamentMatch, PlayerTournamentParticipant, PlayerTournamentQueue,
    PlayerTournamentQueueEntry, PlayerTournamentQueueState, PlayerTournamentResult, PlayerTournamentStanding,
)
from app.models.player import Player
from app.models.stratego import StrategoMatch, StrategoQueueEntry
from app.models.mordoboi import MordoboiMatch, MordoboiQueueEntry
from app.models.kontra import KontraBattle, KontraGear
from app.models.magnate import MagnateMatch, MagnateSeat
from app.models.task import TaskDefinition, UserTask
from app.models.tournament_queue import TournamentQueue, TournamentQueueEntry, TournamentQueueState
from app.models.tournament import Tournament, TournamentClub
from app.models.tournament_match import TournamentMatch
from app.models.tournament_standing import TournamentClubStanding
from app.models.tournament_result import TournamentClubResult
from app.models.tournament_simulation_slot_log import TournamentSimulationSlotLog
from app.models.trade import TradeOffer, TradeOfferCard, TradeWish
from app.models.transaction import CoinTransaction
from app.models.trophy import TrophyDefinition, UserTrophy
from app.models.wheel import WheelPrize, WheelSpin
from app.models.user import User
from app.models.user_activity import UserDailyActivity
from app.models.stars_payment_receipt import StarsPaymentReceipt
from app.models.equipment import EquipmentCollection, EquipmentItem, UserEquipment
from app.models.muse import Muse, MuseAccessory, MuseCollection, MuseDailyClaim, MuseDate, UserMuse, UserMuseAccessory
from app.models.monetization import (
    Artifact,
    ClubSubscription,
    Cosmetic,
    LoginCalendarBonusClaim,
    LoginCalendarDay,
    Season,
    SeasonClaim,
    SeasonLevel,
    SeasonProgress,
    StarterOfferPurchase,
    UserArtifact,
    UserCosmetic,
)
from app.models.user_coach_card import UserCoachCard
from app.models.stadium import Stadium
from app.models.user_stadium_card import UserStadiumCard
from app.models.club_stadium_card import ClubStadiumCard

__all__ = [
    "ManagerClub",
    "ManagerContract",
    "ManagerLeague",
    "ManagerNpc",
    "ManagerSeason",
    "ManagerCosmetic",
    "ManagerMerch",
    "ManagerValueHistory",
    "AdminAction",
    "BlackjackMatch",
    "StrategoMatch",
    "MordoboiMatch",
    "KontraBattle",
    "KontraGear",
    "MordoboiQueueEntry",
    "StrategoQueueEntry",
    "Badge",
    "UserBadge",
    "UserCard",
    "CardStarLedger",
    "CardPath",
    "PathAttemptPurchase",
    "PathPrestigeLedger",
    "UserAcademy",
    "UserClubBase",
    "ClubBaseLedger",
    "UserBaseCosmetic",
    "AcademyLedger",
    "PathStage",
    "PathStageTask",
    "PathTalent",
    "PathXpEvent",
    "CardCollection",
    "UserCollectionReward",
    "CardUpgradeAttempt",
    "CardUpgradeRule",
    "Club",
    "ClubJoinRequest",
    "ClubMember",
    "ClubBudgetTransaction",
    "ClubCard",
    "ClubCardAvailability",
    "ClubCoachCard",
    "ClubDailyClaim",
    "ClubDonation",
    "ClubEmblemItem",
    "ClubEmblemUnlock",
    "ClubStarTransaction",
    "ClubPost",
    "ClubWar",
    "ClubWarRound",
    "ClubSeasonResult",
    "ClubQuestCompletion",
    "ClubRaid",
    "ClubRaidAttack",
    "MatchDayFixture",
    "MatchDayPrediction",
    "WeeklyCupResult",
    "WeeklyCupWeek",
    "ClubQuestTemplate",
    "ClubRewardClaim",
    "ClubRewardGrant",
    "ClubShopItem",
    "ClubShopPurchase",
    "ClubLeagueResult",
    "ClubLeagueWeek",
    "ClubLineup",
    "ClubLineupCard",
    "ClubPack",
    "ClubPackRarityProbability",
    "ClubPackOpening",
    "ClubPackOpeningCard",
    "Coach",
    "CoachBoost",
    "CoinPackage",
    "DailyReward",
    "GameSession",
    "MemoryGameRound",
    "GameConfig",
    "Gift",
    "GiftSet",
    "LeagueTier",
    "UserLeagueRewardClaim",
    "Lineup",
    "LineupCard",
    "Match",
    "MatchEvent",
    "Notification",
    "Pack",
    "PackOpening",
    "PackOpeningCard",
    "PackRarityProbability",
    "StarsInvoice",
    "PenaltyMatch",
    "PersonalSquad",
    "PersonalSquadCard",
    "PlayerTournament",
    "PlayerTournamentMatch",
    "PlayerTournamentParticipant",
    "PlayerTournamentQueue",
    "PlayerTournamentQueueEntry",
    "PlayerTournamentQueueState",
    "PlayerTournamentResult",
    "PlayerTournamentStanding",
    "Player",
    "TaskDefinition",
    "UserTask",
    "TradeOffer",
    "TradeOfferCard",
    "TradeWish",
    "TournamentQueue",
    "TournamentQueueEntry",
    "TournamentQueueState",
    "Tournament",
    "TournamentClub",
    "TournamentMatch",
    "TournamentClubStanding",
    "TournamentClubResult",
    "TournamentSimulationSlotLog",
    "CoinTransaction",
    "TrophyDefinition",
    "UserTrophy",
    "WheelPrize",
    "WheelSpin",
    "User",
    "UserDailyActivity",
    "StarsPaymentReceipt",
    "ClubSubscription",
    "Cosmetic",
    "LoginCalendarBonusClaim",
    "LoginCalendarDay",
    "Season",
    "SeasonClaim",
    "SeasonLevel",
    "SeasonProgress",
    "StarterOfferPurchase",
    "UserCosmetic",
    "Artifact",
    "UserArtifact",
    "EquipmentCollection",
    "EquipmentItem",
    "UserEquipment",
    "UserCoachCard",
    "Stadium",
    "UserStadiumCard",
    "ClubStadiumCard",
    "CardSkill",
    "CardSkillLedger",
    "UserSkillToken",
    "CareerSeason",
    "CareerParticipant",
    "Friendship",
    "MyPlayer",
    "MyPlayerDuel",
    "LifestyleItem",
    "UserLifestyleItem",
    "PlayerCareerSeason",
    "PlayerCareerCup",
    "PlayerCareerMonthStat",
    "PlayerCareerGoldenBall",
    "PlayerCareerClubRecord",
    "PlayerCareerFriendLeague",
    "PlayerCareerFriendMember",
    "PlayerCareerWeekStat",
    "PlayerCareerWeeklyClaim",
]
