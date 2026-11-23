from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from aiogram.exceptions import TelegramBadRequest

from handlers import user


def _message(text):
    return SimpleNamespace(
        text=text,
        from_user=SimpleNamespace(id=42, first_name="Иван"),
        answer=AsyncMock(),
        answer_photo=AsyncMock(),
    )


@pytest.fixture
def db(monkeypatch):
    monkeypatch.setattr(user.db, "mark_bot_unblocked_by_telegram_id", AsyncMock())
    lookup = AsyncMock(return_value=None)
    monkeypatch.setattr(user.db, "get_user_by_telegram_id", lookup)
    return lookup


@pytest.mark.asyncio
async def test_newcomer_from_an_ad_gets_the_pack_picture(db):
    msg = _message("/start ad_karam")
    await user.cmd_start(msg)
    msg.answer.assert_not_called()
    (photo,), kwargs = msg.answer_photo.call_args
    assert photo.endswith("/static/bot/welcome-pack.jpg")
    assert "Твой первый пак уже ждёт" in kwargs["caption"]
    button = kwargs["reply_markup"].inline_keyboard[0][0]
    assert button.text == user.FREE_PACK_BUTTON
    assert button.web_app.url.endswith("?src=ad_karam")


@pytest.mark.asyncio
async def test_newcomer_with_a_bare_start_gets_it_too(db):
    msg = _message("/start")
    await user.cmd_start(msg)
    assert msg.answer_photo.call_args.kwargs["reply_markup"].inline_keyboard[0][0].text == user.FREE_PACK_BUTTON


@pytest.mark.asyncio
async def test_existing_player_keeps_the_plain_hello(db):
    db.return_value = {"id": 1}
    msg = _message("/start ad_karam")
    await user.cmd_start(msg)
    msg.answer_photo.assert_not_called()
    assert "Добро пожаловать" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_penalty_link_keeps_its_own_message(db):
    msg = _message("/start penalty_karam")
    await user.cmd_start(msg)
    msg.answer_photo.assert_not_called()
    assert "Ворота ждут" in msg.answer.call_args.args[0]


@pytest.mark.asyncio
async def test_picture_failure_falls_back_to_text(db):
    msg = _message("/start ad_x")
    msg.answer_photo.side_effect = TelegramBadRequest(method=None, message="wrong file")
    await user.cmd_start(msg)
    assert "Твой первый пак" in msg.answer.call_args.args[0]
