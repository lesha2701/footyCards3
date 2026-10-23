from pydantic import BaseModel


class FeatureFlagsOut(BaseModel):
    matchmaking_enabled: bool
    wheel_enabled: bool
    trades_enabled: bool = True
    leagues_enabled: bool
    # Largest stake per side in open chat challenges (0 = stakes off).
    stake_max_coins: int = 0
