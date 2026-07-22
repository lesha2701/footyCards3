import hashlib
import hmac
import json
import time
from typing import Optional
from urllib.parse import parse_qsl

import jwt
from pydantic import BaseModel

from app.config import get_settings

settings = get_settings()

INIT_DATA_MAX_AGE_SECONDS = 24 * 60 * 60


class TelegramAuthError(Exception):
    pass


class TelegramUser(BaseModel):
    id: int
    username: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    photo_url: Optional[str] = None


def validate_init_data(init_data: str, bot_token: str, max_age_seconds: int = INIT_DATA_MAX_AGE_SECONDS) -> TelegramUser:
    """Validate Telegram WebApp initData signature per the Mini Apps spec.

    https://core.telegram.org/bots/webapps#validating-data-received-via-the-mini-app
    """
    if not init_data:
        raise TelegramAuthError("empty init_data")

    pairs = parse_qsl(init_data, keep_blank_values=True, strict_parsing=False)
    data = dict(pairs)

    received_hash = data.pop("hash", None)
    if not received_hash:
        raise TelegramAuthError("missing hash")

    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))

    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if not hmac.compare_digest(computed_hash, received_hash):
        raise TelegramAuthError("invalid signature")

    auth_date = data.get("auth_date")
    if auth_date is not None:
        age = time.time() - int(auth_date)
        if age > max_age_seconds:
            raise TelegramAuthError("init_data expired")

    user_raw = data.get("user")
    if not user_raw:
        raise TelegramAuthError("missing user")

    try:
        user_json = json.loads(user_raw)
    except json.JSONDecodeError as exc:
        raise TelegramAuthError("invalid user payload") from exc

    return TelegramUser(
        id=user_json["id"],
        username=user_json.get("username"),
        first_name=user_json.get("first_name"),
        last_name=user_json.get("last_name"),
        photo_url=user_json.get("photo_url"),
    )


def create_admin_token(user_id: int, telegram_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "scope": "admin",
        "iat": int(time.time()),
        "exp": int(time.time()) + settings.jwt_expire_minutes * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_admin_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise TelegramAuthError(f"invalid admin token: {exc}") from exc


def create_session_token(user_id: int, telegram_id: int) -> str:
    payload = {
        "sub": str(user_id),
        "telegram_id": telegram_id,
        "scope": "session",
        "iat": int(time.time()),
        "exp": int(time.time()) + 30 * 24 * 60 * 60,
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm="HS256")


def decode_session_token(token: str) -> dict:
    try:
        return jwt.decode(token, settings.jwt_secret, algorithms=["HS256"])
    except jwt.PyJWTError as exc:
        raise TelegramAuthError(f"invalid session token: {exc}") from exc
