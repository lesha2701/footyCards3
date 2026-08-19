from app import backfill_player_stats
from app.models.enums import Position
from app.schemas.player import PlayerOut
from app.services.player_stats_service import compute_default_attack_defense
from tests.factories import create_player
from tests.utils import telegram_headers


async def _admin_headers(client, bot_token):
    headers = telegram_headers(999000001, bot_token)
    resp = await client.post("/api/v1/auth/session", headers=headers)
    admin_token = resp.json()["admin_token"]
    return {"Authorization": f"Bearer {admin_token}"}


def test_compute_default_attack_defense_skews_by_position_and_clamps():
    attack, defense = compute_default_attack_defense(70, Position.ST)
    assert attack > 70 > defense

    attack, defense = compute_default_attack_defense(70, Position.CB)
    assert defense > 70 > attack

    attack, defense = compute_default_attack_defense(70, Position.CM)
    assert attack == 70
    assert defense == 70

    attack, _ = compute_default_attack_defense(95, Position.ST)  # 95 + 16 -> clamp 99
    assert attack == 99
    attack, _ = compute_default_attack_defense(5, Position.CB)  # 5 - 14 -> clamp 1
    assert attack == 1


async def test_create_player_without_stats_auto_computes_from_position(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/players", headers=headers,
        json={
            "first_name": "Test", "last_name": "Striker", "display_name": "Test Striker",
            "rating": 70, "rarity": "common", "country": "Тестландия", "club": "ФК Тест",
            "position": "ST",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    expected_attack, expected_defense = compute_default_attack_defense(70, Position.ST)
    assert body["attack_rating"] == expected_attack
    assert body["defense_rating"] == expected_defense


async def test_create_player_with_explicit_stats_keeps_them(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    resp = await client.post(
        "/api/v1/admin/players", headers=headers,
        json={
            "first_name": "Test", "last_name": "Custom", "display_name": "Test Custom",
            "rating": 70, "attack_rating": 40, "defense_rating": 90,
            "rarity": "common", "country": "Тестландия", "club": "ФК Тест", "position": "ST",
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["attack_rating"] == 40
    assert body["defense_rating"] == 90


async def test_toggle_pack_droppable(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    player = await create_player(db_session)
    assert player.is_pack_droppable is True

    resp = await client.post(f"/api/v1/admin/players/{player.id}/toggle-pack-droppable", headers=headers)
    assert resp.status_code == 200
    assert resp.json()["is_pack_droppable"] is False

    resp2 = await client.post(f"/api/v1/admin/players/{player.id}/toggle-pack-droppable", headers=headers)
    assert resp2.json()["is_pack_droppable"] is True


async def test_player_out_falls_back_to_rating_when_stats_null(db_session):
    player = await create_player(db_session, rating=77, position=Position.CM)
    assert player.attack_rating is None
    assert player.defense_rating is None

    out = PlayerOut.model_validate(player)
    assert out.attack_rating == 77
    assert out.defense_rating == 77


async def test_backfill_fills_only_null_stats_and_is_idempotent(db_session):
    fresh = await create_player(db_session, rating=80, position=Position.ST)
    preset = await create_player(
        db_session, rating=60, position=Position.CB, attack_rating=33, defense_rating=44
    )
    assert fresh.attack_rating is None

    count = await backfill_player_stats.backfill(db_session)
    assert count == 1

    await db_session.refresh(fresh)
    await db_session.refresh(preset)
    expected_attack, expected_defense = compute_default_attack_defense(80, Position.ST)
    assert fresh.attack_rating == expected_attack
    assert fresh.defense_rating == expected_defense
    assert preset.attack_rating == 33
    assert preset.defense_rating == 44

    second_count = await backfill_player_stats.backfill(db_session)
    assert second_count == 0
