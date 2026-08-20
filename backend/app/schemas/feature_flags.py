from pydantic import BaseModel


class FeatureFlagsOut(BaseModel):
    matchmaking_enabled: bool
    wheel_enabled: bool
    leagues_enabled: bool
