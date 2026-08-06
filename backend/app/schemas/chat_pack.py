from pydantic import BaseModel


class ChatPackOpenIn(BaseModel):
    telegram_user_id: int
