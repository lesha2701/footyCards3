"""`GET /home`: the Mini App's first screen in one request. Every part is
exactly what its own endpoint answers; a failing one is listed in errors."""
from tests.utils import telegram_headers

API = "/api/v1"


async def test_home_parts_equal_their_own_endpoints(client, bot_token):
    headers = telegram_headers(990001, bot_token)
    await client.post(f"{API}/auth/session", headers=headers)

    response = await client.get(f"{API}/home", headers=headers)
    assert response.status_code == 200
    body = response.json()
    assert body["errors"] == {"/clubs/me": 404}  # not in a club: the app asks itself, gets its 404
    assert {"/profile/me", "/newbie", "/packs", "/my-player", "/presence"} <= set(body["data"])

    for path, part in body["data"].items():
        own = await client.get(f"{API}{path}", headers=headers)
        assert own.status_code == 200, path
        assert own.json() == part, path


async def test_home_needs_a_player(client):
    assert (await client.get(f"{API}/home")).status_code == 401
