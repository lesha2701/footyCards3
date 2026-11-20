from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from handlers import guest


def _message(text, user_id=42, first_name="Иван"):
    user = SimpleNamespace(id=user_id, first_name=first_name, username="ivan", last_name=None)
    return SimpleNamespace(text=text, caption=None, from_user=user, guest_query_id="gq1")


def test_query_strips_the_mention_in_any_case_and_extra_spaces():
    assert guest.query_of("@FootyCards_Bot   вкарта ", "footycards_bot") == "вкарта"
    assert guest.query_of("Глянь @footycards_bot Месси", "footycards_bot") == "Глянь Месси"
    assert guest.query_of("@footycards_bot", "footycards_bot") == ""
    assert len(guest.query_of("@footycards_bot " + "я" * 100, "footycards_bot")) == guest.MAX_QUERY


@pytest.mark.asyncio
async def test_empty_mention_answers_with_help():
    result = await guest.build_result(_message("@footycards_bot"), "footycards_bot")
    assert "вкарта" in result.input_message_content.message_text
    assert result.reply_markup.inline_keyboard[0][0].url.endswith("?start=chatpack")


@pytest.mark.asyncio
async def test_challenge_links_to_the_callers_referral():
    result = await guest.build_result(_message("@footycards_bot вызов", user_id=777), "footycards_bot")
    assert "Иван" in result.input_message_content.message_text
    assert result.reply_markup.inline_keyboard[0][0].url.endswith("?start=ref_777")


@pytest.mark.asyncio
async def test_pack_word_opens_the_chat_card_with_its_picture(monkeypatch):
    card = {"card": {"serial_number": 5, "player": {
        "display_name": "Месси", "rarity": "legendary", "position": "RW", "club": "Интер Майами",
        "country": "Аргентина", "rating": 93, "attack_rating": 95, "defense_rating": 40,
        "image_path": "players/legendary/messi.webp",
    }}}
    monkeypatch.setattr(guest, "request_chat_pack", AsyncMock(return_value=(200, {"cards": [card]})))
    result = await guest.build_result(_message("@footycards_bot Вкарта"), "footycards_bot")
    text = result.input_message_content.message_text
    assert "Иван открыл карту" in text and "Месси" in text
    preview = result.input_message_content.link_preview_options
    assert preview.url.endswith("/static/players/legendary/messi.webp") and preview.show_above_text


@pytest.mark.asyncio
async def test_pack_on_cooldown_says_when(monkeypatch):
    body = {"error": {"details": {"available_at": "2999-01-01T00:00:00+00:00"}}}
    monkeypatch.setattr(guest, "request_chat_pack", AsyncMock(return_value=(429, body)))
    result = await guest.build_result(_message("@footycards_bot вкарта"), "footycards_bot")
    assert "следующая карта будет доступна через" in result.input_message_content.message_text


@pytest.mark.asyncio
async def test_player_name_shows_the_best_match_and_others(monkeypatch):
    rows = [
        {"display_name": "Месси", "rating": 93, "attack_rating": 95, "defense_rating": 40, "rarity": "legendary",
         "position": "RW", "club": "Интер Майами", "country": "Аргентина", "image_path": "players/legendary/messi.webp"},
        {"display_name": "Месси (юный)", "rating": 61, "attack_rating": 64, "defense_rating": 30, "rarity": "diamond",
         "position": "RW", "club": "Барселона", "country": "Аргентина", "image_path": None},
    ]
    find = AsyncMock(return_value=rows)
    monkeypatch.setattr(guest.db, "find_players", find)
    result = await guest.build_result(_message("@footycards_bot месси"), "footycards_bot")
    find.assert_awaited_once_with("месси")
    text = result.input_message_content.message_text
    assert "<b>Месси</b>" in text and "#" not in text and "Ещё: 💎 Месси (юный) 61" in text


@pytest.mark.asyncio
async def test_unknown_player_says_not_found(monkeypatch):
    monkeypatch.setattr(guest.db, "find_players", AsyncMock(return_value=[]))
    result = await guest.build_result(_message("@footycards_bot Пупкин"), "footycards_bot")
    assert "Пупкин" in result.input_message_content.message_text
    assert result.input_message_content.link_preview_options.is_disabled
