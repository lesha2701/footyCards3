import io
from pathlib import Path

import pytest
from PIL import Image

from app.models.card import UserCard
from app.models.enums import CardSource, MatchDifficulty, MatchResult, MatchStatus, Position, Rarity
from app.models.match import Match
from app.models.trophy import TrophyDefinition, UserTrophy
from app.services import share_service
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

API = "/api/v1"


@pytest.fixture(autouse=True)
def _share_dir(tmp_path, monkeypatch):
    """Rendered images go to a temp dir, not the real backend/static/share."""
    monkeypatch.setattr(share_service, "SHARE_DIR", tmp_path / "share")


async def _login(client, db, tg_id, bot_token):
    headers = telegram_headers(tg_id, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)
    return headers, await get_user_by_telegram_id(db, tg_id)


async def _card(db, owner, rarity=Rarity.legendary, name="Тест Легенда"):
    player = await create_player(db, rarity=rarity, rating=90, position=Position.ST, display_name=name)
    card = UserCard(owner_id=owner.id, player_id=player.id, source=CardSource.pack)
    db.add(card)
    await db.commit()
    return card


def _jpeg_at(image_url: str) -> tuple[str, tuple[int, int]]:
    data = Path(share_service.SHARE_DIR / image_url.removeprefix("/static/share/")).read_bytes()
    with Image.open(io.BytesIO(data)) as img:
        return img.format, img.size


async def test_share_own_legendary_card_returns_image_and_referral_link(client, db_session, bot_token):
    headers, user = await _login(client, db_session, 860001, bot_token)
    card = await _card(db_session, user)

    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "card", "id": card.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["link"].endswith(f"?start=ref_{user.telegram_id}")
    assert "Тест Легенда" in body["caption"]
    assert body["share_url"].startswith("https://t.me/share/url?url=")
    # Dev settings (no public HTTPS URL, dev bot token): no prepared Telegram message, plain link instead.
    assert body["prepared_message_id"] is None
    assert _jpeg_at(body["image_url"]) == ("JPEG", (800, 800))


async def test_cannot_share_someone_elses_card_or_a_common_one(client, db_session, bot_token):
    headers, _me = await _login(client, db_session, 860002, bot_token)
    _h, other = await _login(client, db_session, 860003, bot_token)
    theirs = await _card(db_session, other)
    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "card", "id": theirs.id})
    assert resp.status_code == 404

    mine_common = await _card(db_session, _me, rarity=Rarity.common, name="Обычный")
    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "card", "id": mine_common.id})
    assert resp.status_code == 409


async def _match(db, user, result):
    match = Match(
        user_id=user.id, opponent_name="Соперник", difficulty=MatchDifficulty.medium,
        user_team_strength=900, opponent_team_strength=880, user_score=3, opponent_score=1,
        status=MatchStatus.finished, result=result,
    )
    db.add(match)
    await db.commit()
    return match


async def test_share_only_own_arena_wins(client, db_session, bot_token):
    headers, user = await _login(client, db_session, 860004, bot_token)
    win = await _match(db_session, user, MatchResult.win)
    loss = await _match(db_session, user, MatchResult.loss)

    ok = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "match", "id": win.id})
    assert ok.status_code == 200 and "3:1" in ok.json()["caption"]
    # The opponent's name (another player's) is not put on the public image or caption.
    assert "Соперник" not in ok.json()["caption"]
    assert (await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "match", "id": loss.id})).status_code == 409

    other_headers, _other = await _login(client, db_session, 860005, bot_token)
    assert (await client.post(f"{API}/share/prepare", headers=other_headers, json={"kind": "match", "id": win.id})).status_code == 404


async def test_share_own_trophy(client, db_session, bot_token):
    headers, user = await _login(client, db_session, 860006, bot_token)
    definition = TrophyDefinition(code="share_test_cup", name="Кубок теста", description="За тесты")
    db_session.add(definition)
    await db_session.flush()
    trophy = UserTrophy(user_id=user.id, trophy_definition_id=definition.id)
    db_session.add(trophy)
    await db_session.commit()

    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "trophy", "id": trophy.id})
    assert resp.status_code == 200
    assert "Кубок теста" in resp.json()["caption"]


async def test_prepared_telegram_message_when_app_is_public(client, db_session, bot_token, monkeypatch):
    headers, user = await _login(client, db_session, 860007, bot_token)
    card = await _card(db_session, user, rarity=Rarity.diamond, name="Тест Бриллиант")
    monkeypatch.setattr(share_service.settings, "mini_app_url", "https://footycards.example")
    monkeypatch.setattr(share_service, "_can_prepare_messages", lambda: True)  # real bot + public HTTPS
    calls = []

    async def fake_save(u, photo_url, caption, link):
        calls.append((u.telegram_id, photo_url, caption, link))
        return "prep-42"

    monkeypatch.setattr(share_service, "_save_prepared_message", fake_save)
    resp = await client.post(f"{API}/share/prepare", headers=headers, json={"kind": "card", "id": card.id})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["prepared_message_id"] == "prep-42"
    (tg_id, photo_url, caption, link), = calls
    assert tg_id == user.telegram_id
    assert photo_url.startswith("https://footycards.example/static/share/card_")
    assert "бриллиант" in caption and link.endswith(f"ref_{user.telegram_id}")
