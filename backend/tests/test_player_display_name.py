"""The admin edits only a player's display name; the legacy first_name /
last_name columns (NOT NULL) follow it on create, update and CSV import."""
from app.schemas.player import split_display_name
from app.services.csv_service import CSV_COLUMNS, export_players_csv, import_players_csv
from tests.factories import create_player
from tests.utils import telegram_headers


async def _admin_headers(client, bot_token):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(999000001, bot_token))
    return {"Authorization": f"Bearer {resp.json()['admin_token']}"}


BASE = {"rating": 70, "rarity": "common", "country": "Бразилия", "club": "Сантос", "position": "ST"}


def test_split_display_name():
    assert split_display_name("Лионель Месси") == ("Лионель", "Месси")
    assert split_display_name("Пеле") == ("Пеле", "Пеле")
    assert split_display_name("  Кевин Де Брёйне ") == ("Кевин", "Де Брёйне")


async def test_create_with_display_name_only(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    resp = await client.post("/api/v1/admin/players", headers=headers, json={"display_name": "Пеле", **BASE})
    assert resp.status_code == 200
    body = resp.json()
    assert (body["display_name"], body["first_name"], body["last_name"]) == ("Пеле", "Пеле", "Пеле")


async def test_create_rejects_an_empty_display_name(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    resp = await client.post("/api/v1/admin/players", headers=headers, json={"display_name": "", **BASE})
    assert resp.status_code == 422


async def test_renaming_keeps_the_hidden_names_in_step(client, db_session, bot_token):
    headers = await _admin_headers(client, bot_token)
    player = await create_player(db_session)
    resp = await client.put(
        f"/api/v1/admin/players/{player.id}", headers=headers, json={"display_name": "Роналдо Назарио"}
    )
    assert resp.status_code == 200
    body = resp.json()
    assert (body["first_name"], body["last_name"]) == ("Роналдо", "Назарио")


async def test_csv_round_trip_without_name_columns(db_session):
    await create_player(db_session)
    exported = await export_players_csv(db_session)
    assert exported.splitlines()[0] == ",".join(CSV_COLUMNS)
    assert "first_name" not in CSV_COLUMNS

    header = "display_name,rating,rarity,country,club,position"
    result = await import_players_csv(db_session, f"{header}\nЗико,80,epic,Бразилия,Фламенго,CAM\n")
    assert result["created"] == 1 and not result["errors"]


async def test_csv_still_accepts_old_files_with_name_columns(db_session):
    header = "first_name,last_name,display_name,rating,rarity,country,club,position"
    result = await import_players_csv(db_session, f"{header}\nArthur,Coimbra,Зико,80,epic,Бразилия,Фламенго,CAM\n")
    assert result["created"] == 1 and not result["errors"]
