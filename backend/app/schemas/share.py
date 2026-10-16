from typing import Literal, Optional

from pydantic import BaseModel


class SharePrepareIn(BaseModel):
    kind: Literal["card", "match", "trophy"]
    id: int


class SharePrepareOut(BaseModel):
    # Set when Telegram accepted a prepared inline message (send it with
    # WebApp.shareMessage); None in dev or if Telegram refused — then use share_url.
    prepared_message_id: Optional[str] = None
    image_url: str
    caption: str
    link: str
    share_url: str
