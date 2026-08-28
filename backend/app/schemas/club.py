from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from app.models.enums import ClubJoinRequestStatus, ClubLogoShape, ClubRole, ClubType


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


class ClubMemberOut(BaseModel):
    user_id: int
    username: Optional[str]
    first_name: Optional[str]
    avatar_url: Optional[str]
    role: ClubRole
    joined_at: datetime


class ClubSummaryOut(BaseModel):
    id: int
    name: str
    club_type: ClubType
    logo_shape: ClubLogoShape
    logo_color: str
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
