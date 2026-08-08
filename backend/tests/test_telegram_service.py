import httpx

from app.services.telegram_service import check_channel_membership


async def test_check_channel_membership_fails_closed_on_network_error(monkeypatch):
    async def raise_read_error(self, *args, **kwargs):
        raise httpx.ReadError("connection reset")

    monkeypatch.setattr(httpx.AsyncClient, "get", raise_read_error)

    result = await check_channel_membership(123456, "@some_channel")
    assert result is False


async def test_check_channel_membership_true_for_member(monkeypatch):
    class FakeResponse:
        def json(self):
            return {"ok": True, "result": {"status": "member"}}

    async def fake_get(self, *args, **kwargs):
        return FakeResponse()

    monkeypatch.setattr(httpx.AsyncClient, "get", fake_get)

    result = await check_channel_membership(123456, "@some_channel")
    assert result is True
