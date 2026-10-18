from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.models.enums import ClubJoinRequestStatus, ClubLogoShape, ClubRole, ClubType
from app.schemas.club_emblem import ClubEmblemOut, SponsorTier


class ClubCreationCostOut(BaseModel):
    creation_cost_coins: int


class ClubCreate(BaseModel):
    name: str = Field(min_length=3, max_length=64)
    description: str = Field(default="", max_length=512)
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str = Field(min_length=4, max_length=16)


class ClubUpdate(BaseModel):
    description: Optional[str] = Field(default=None, max_length=512)
    logo_shape: Optional[ClubLogoShape] = None
    logo_color: Optional[str] = Field(default=None, min_length=4, max_length=16)


class ClubTypeUpdate(BaseModel):
    club_type: ClubType


class ClubMemberOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    role: ClubRole
    joined_at: datetime
    personal_reward_enabled: bool
    # «Казна за Stars»: bronze/silver/gold patron of this club, null = never donated.
    sponsor_tier: Optional[SponsorTier] = None


class ClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
    member_count: int
    cups_count: int
    stars_count: int


class ClubDetailOut(BaseModel):
    id: int
    name: str
    description: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
    emblem: Optional[ClubEmblemOut] = None
    captain_id: int
    founded_at: datetime
    member_count: int
    budget: int
    cups_count: int
    stars_count: int
    members: list[ClubMemberOut]
    # Only populated when the requester is a member — never leak an
    # invite code to an outsider browsing the club list.
    invite_code: Optional[str] = None
    my_role: Optional[ClubRole] = None
    # Seconds until the requester can claim the club's daily reward again — null if it's
    # available right now. Computed against the requester, not the club as a whole, since
    # each member claims individually (see club_service.claim_daily_reward).
    daily_reward_seconds_remaining: Optional[int] = None
    # All-time sum of this requester's own personal club-tournament-match reward credits
    # (TransactionType.club_tournament_match_reward) — null for a non-member, 0 if they're a
    # member with no such credits yet. See club_service._personal_match_earnings.
    personal_match_earnings: Optional[int] = None
    # Captain's switch: only captain / vice-captain / treasurer spend the budget.
    budget_treasurer_only: bool = False
    # Whether the requester may spend the budget (packs, emblem, spare cards).
    can_spend_budget: bool = False
    # «Стена клуба»: posts the requester hasn't seen yet (null for a non-member).
    wall_unread: Optional[int] = None
    # Club rewards (shop, quests, wars) the requester can still claim.
    rewards_unclaimed: Optional[int] = None


class ClubJoinRequestOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    created_at: datetime
    status: ClubJoinRequestStatus


class JoinByInviteIn(BaseModel):
    invite_code: str


class TransferCaptainIn(BaseModel):
    user_id: int


class PersonalRewardToggleIn(BaseModel):
    enabled: bool


class MemberRoleIn(BaseModel):
    role: ClubRole


class BudgetPolicyIn(BaseModel):
    treasurer_only: bool
