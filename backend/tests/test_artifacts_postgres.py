"""«Артефакты» on real Postgres: taking a copy off / putting it on / gifting
locks the copy row, and the copy eager-loads its artifact with an outer
join — Postgres rejects a plain FOR UPDATE on that, which SQLite never
shows. Every row a test creates is deleted on teardown (real_pg)."""
import uuid
from types import SimpleNamespace

import pytest

from app.models.monetization import Artifact
from app.models.user import User
from app.services import artifact_service

CONFIG = SimpleNamespace(artifacts_enabled=True, artifact_slots=2, artifact_max_opp_pct=5, artifact_max_stat=6)


@pytest.fixture(autouse=True)
def _config(monkeypatch):
    # The shared test database's game_config row must not be changed.
    async def fake_get_config(_db):
        return CONFIG

    monkeypatch.setattr(artifact_service, "get_config", fake_get_config)
    yield


async def _setup(pg, n_artifacts=3):
    async with pg() as s:
        user = User(telegram_id=int(uuid.uuid4().int % 10**12), first_name="Art", balance=0)
        s.add(user)
        artifacts = [
            Artifact(name=f"Тест {i} {uuid.uuid4().hex[:6]}", target="my_player", effect="defense", effect_value=2)
            for i in range(n_artifacts)
        ]
        s.add_all(artifacts)
        await s.flush()
        copies = [await artifact_service.grant(s, user.id, a.id, "admin") for a in artifacts]
        await s.commit()
        return user.id, [c.id for c in copies]


async def _set(pg, user_id, copy_id, active):
    async with pg() as s:
        user = await s.get(User, user_id)
        return await artifact_service.set_active(s, user, copy_id, active)


async def test_take_off_put_on_and_swap(real_pg):
    user_id, (first, second, third) = await _setup(real_pg)
    # grant() filled both slots; the third went to the shelf.
    out = await _set(real_pg, user_id, first, False)
    assert {c["copy_id"]: c["equipped"] for c in out["shelf"]} == {first: False, second: True, third: False}

    out = await _set(real_pg, user_id, third, True)
    assert {c["copy_id"]: c["equipped"] for c in out["shelf"]} == {first: False, second: True, third: True}
    assert out["effects"]["my_player"] == [{"effect": "defense", "value": 4, "label": "+4 к защите"}]
