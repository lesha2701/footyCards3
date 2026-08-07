from typing import Optional

from pydantic import BaseModel


class ChatPackOpenIn(BaseModel):
    telegram_user_id: int
    # Only used to register a brand-new user on the spot if this is their
    # first interaction with the bot — ignored for an existing user.
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
