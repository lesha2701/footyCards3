from pydantic import BaseModel


class FeatureFlagsOut(BaseModel):
    matchmaking_enabled: bool
    wheel_enabled: bool
    trades_enabled: bool = True
    leagues_enabled: bool
