from typing import Literal, Optional

from pydantic import BaseModel


class SharePrepareIn(BaseModel):
    kind: Literal[
        "card", "match", "trophy", "my_player", "trade_wishes", "manager_player", "manager_transfer", "mordoboi_win",
    ]
    # Ignored for "my_player", "manager_player" and "trade_wishes" (always the
    # caller's own); "manager_transfer" = the manager contract id;
    # "mordoboi_win" = a won «Мордобой» bout (with its «Бруталити», if any).
    id: int = 0


class SharePrepareOut(BaseModel):
    # Set when Telegram accepted a prepared inline message (send it with
    # WebApp.shareMessage); None in dev or if Telegram refused — then use share_url.
    prepared_message_id: Optional[str] = None
    # None for text-only shares («Поиск обменов»).
    image_url: Optional[str] = None
    caption: str
    link: str
    share_url: str
