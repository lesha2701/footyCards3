"""«Ты здесь?»: after every presence_check_minutes of continuous play
(anti_bot_service's stretch of play) the player must pick the number shown
on a server-drawn picture out of four. Until then games don't pay or rate
(User.game_rewards_blocked); presence_check_max_wrong wrong answers in a row
pause rewards for presence_check_lock_minutes.

A human answers in a second; a script calling the API directly would have
to read a noisy picture — the answer is never in any JSON. Not unbeatable,
but it turns a trivial loop into real work.

The challenge lives on users.presence_challenge: {token, answer, options,
wrong}; users.presence_due_at is when the next one is due.
"""
import io
import random
import secrets
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Optional

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.exceptions import ConflictError, NotFoundError
from app.core.timeutil import ensure_aware
from app.models.game_config import GameConfig
from app.models.user import User
from app.services.wallet_service import lock_user_for_update

FONT = Path(__file__).resolve().parent.parent / "assets" / "fonts" / "benzin-extrabold.woff2"


def _new_challenge() -> dict:
    answer = random.randint(10, 99)
    options = {answer}
    while len(options) < 4:
        options.add(random.randint(10, 99))
    shuffled = list(options)
    random.shuffle(shuffled)
    return {"token": secrets.token_urlsafe(12), "answer": answer, "options": shuffled, "wrong": 0}


def due(user: User, config: GameConfig, now: datetime) -> bool:
    if not config.presence_check_enabled or user.presence_challenge is not None:
        return False
    return user.presence_due_at is not None and ensure_aware(user.presence_due_at) <= now


def next_values(user: User, config: GameConfig, now: datetime, new_stretch: bool) -> dict:
    """Presence fields to write with a tracked game action (anti_bot_service.track_play)."""
    if not config.presence_check_enabled:
        return {}
    if new_stretch or user.presence_due_at is None:
        if user.presence_challenge is None:
            return {"presence_due_at": now + timedelta(minutes=max(5, config.presence_check_minutes))}
        return {}
    if due(user, config, now):
        return {"presence_challenge": _new_challenge()}
    return {}


def view(user: User) -> Optional[dict]:
    c = user.presence_challenge
    if not c:
        return None
    return {"token": c["token"], "options": c["options"], "image_url": f"/api/v1/presence/image/{c['token']}"}


def render(user: User, token: str) -> bytes:
    c = user.presence_challenge
    if not c or c.get("token") != token:
        raise NotFoundError("Проверка не найдена")
    rng = random.Random(token)
    img = Image.new("RGB", (240, 120), (24, 28, 34))
    draw = ImageDraw.Draw(img)
    for _ in range(14):
        draw.line([(rng.randint(0, 240), rng.randint(0, 120)), (rng.randint(0, 240), rng.randint(0, 120))],
                  fill=(rng.randint(60, 140), rng.randint(60, 140), rng.randint(60, 140)), width=2)
    try:
        font = ImageFont.truetype(str(FONT), 64)
    except OSError:
        font = ImageFont.load_default()
    x = 50
    for ch in str(c["answer"]):
        glyph = Image.new("RGBA", (80, 90), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text((8, 4), ch, font=font, fill=(200 + rng.randint(0, 55), 230, 120 + rng.randint(0, 80)))
        glyph = glyph.rotate(rng.randint(-25, 25), expand=False)
        img.paste(glyph, (x, 15 + rng.randint(-8, 8)), glyph)
        x += 70
    for _ in range(300):
        draw.point((rng.randint(0, 239), rng.randint(0, 119)), fill=(rng.randint(80, 200),) * 3)
    img = img.filter(ImageFilter.SMOOTH)
    out = io.BytesIO()
    img.save(out, format="PNG")
    return out.getvalue()


async def answer(db: AsyncSession, user: User, token: str, value: int, config: GameConfig) -> dict:
    locked = await lock_user_for_update(db, user.id)
    c = dict(locked.presence_challenge or {})
    if not c or c.get("token") != token:
        raise ConflictError("Эта проверка уже неактуальна — обнови экран")
    now = datetime.now(timezone.utc)
    if int(value) == int(c["answer"]):
        locked.presence_challenge = None
        locked.presence_due_at = now + timedelta(minutes=max(5, config.presence_check_minutes))
        await db.commit()
        return {"ok": True, "challenge": None}
    wrong = int(c.get("wrong", 0)) + 1
    if wrong >= max(1, config.presence_check_max_wrong):
        # Too many misses: rewards rest for a while, then a fresh check.
        locked.presence_challenge = None
        locked.rest_required_until = now + timedelta(minutes=max(1, config.presence_check_lock_minutes))
        locked.presence_due_at = now
        await db.commit()
        return {"ok": False, "locked_until": locked.rest_required_until, "challenge": None}
    fresh = _new_challenge()
    fresh["wrong"] = wrong
    locked.presence_challenge = fresh
    await db.commit()
    return {"ok": False, "challenge": view(locked)}
