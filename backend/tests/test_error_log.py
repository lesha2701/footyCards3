from fastapi import APIRouter
from httpx import ASGITransport, AsyncClient
from sqlalchemy import select

from app.main import app
from app.models.server_error import ServerError
from app.services import error_log_service
from tests.conftest import TestSessionLocal

_boom = APIRouter()


@_boom.get("/api/v1/test-boom/{item_id}")
async def _explode(item_id: int):
    raise RuntimeError(f"kaboom {item_id}")


app.include_router(_boom)


def _client():
    # Starlette re-raises an unhandled error after its handler has answered;
    # a real server just logs it, so the test client mustn't raise either.
    return AsyncClient(transport=ASGITransport(app=app, raise_app_exceptions=False), base_url="http://test")


async def test_unhandled_error_is_answered_500_and_recorded(db_session, monkeypatch):
    monkeypatch.setattr(error_log_service, "session_factory", TestSessionLocal)
    async with _client() as client:
        resp = await client.get("/api/v1/test-boom/42")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"
    row = (await db_session.execute(select(ServerError))).scalar_one()
    assert row.method == "GET" and row.path == "/api/v1/test-boom/{id}"
    assert row.error == "RuntimeError: kaboom 42" and "kaboom" in row.traceback


async def test_recording_failure_never_changes_the_response(db_session, monkeypatch):
    def broken():
        raise OSError("db down")

    monkeypatch.setattr(error_log_service, "session_factory", broken)
    async with _client() as client:
        resp = await client.get("/api/v1/test-boom/1")
    assert resp.status_code == 500
    assert resp.json()["error"]["code"] == "internal_error"


async def test_deep_health_reaches_the_database(client, db_session):
    resp = await client.get("/api/health/deep")
    assert resp.status_code == 200 and resp.json() == {"status": "ok"}
