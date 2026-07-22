import hashlib
import hmac
import json
import time
from urllib.parse import urlencode


def make_init_data(user: dict, bot_token: str, auth_date: int | None = None) -> str:
    """Builds a Telegram WebApp initData string signed the same way the real
    Telegram client would, so tests exercise the real validate_init_data() path."""
    auth_date = auth_date or int(time.time())
    data = {
        "auth_date": str(auth_date),
        "query_id": "test_query_id",
        "user": json.dumps(user, separators=(",", ":")),
    }
    data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
    computed_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    data["hash"] = computed_hash
    return urlencode(data)


def telegram_headers(telegram_id: int, bot_token: str, username: str | None = None, first_name: str = "Test") -> dict:
    user = {"id": telegram_id, "first_name": first_name}
    if username:
        user["username"] = username
    return {"X-Telegram-Init-Data": make_init_data(user, bot_token)}
