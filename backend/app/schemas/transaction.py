from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict

from app.models.enums import TransactionType


class CoinTransactionOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    amount: int
    balance_before: int
    balance_after: int
    type: TransactionType
    description: str
    related_object_type: Optional[str]
    related_object_id: Optional[int]
    created_at: datetime
