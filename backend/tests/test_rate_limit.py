import pytest

import app.core.rate_limit as rl
from app.core.exceptions import RateLimitedError


@pytest.fixture(autouse=True)
def _clean():
    rl._hits.clear()
    yield
    rl._hits.clear()


async def test_in_memory_window_blocks_after_max_calls():
    for _ in range(3):
        await rl.check_rate_limit("t:1", 3, 60)
    with pytest.raises(RateLimitedError):
        await rl.check_rate_limit("t:1", 3, 60)
    await rl.check_rate_limit("t:2", 3, 60)  # other keys are independent


class _FakePipe:
    def __init__(self, store):
        self.store, self.ops = store, []

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False

    def zremrangebyscore(self, key, lo, hi):
        self.ops.append(lambda: self.store.__setitem__(key, {m: s for m, s in self.store.get(key, {}).items() if not lo <= s <= hi}))

    def zadd(self, key, mapping):
        self.ops.append(lambda: self.store.setdefault(key, {}).update(mapping))

    def zcard(self, key):
        self.ops.append(lambda: len(self.store.get(key, {})))

    def expire(self, key, seconds):
        self.ops.append(lambda: True)

    async def execute(self):
        return [op() for op in self.ops]


class _FakeRedis:
    def __init__(self):
        self.store = {}

    def pipeline(self, transaction=True):
        return _FakePipe(self.store)

    async def zrem(self, key, member):
        self.store.get(key, {}).pop(member, None)


async def test_redis_backend_shares_window_and_drops_rejected_hits(monkeypatch):
    fake = _FakeRedis()
    monkeypatch.setattr(rl, "_redis_client", lambda: fake)
    await rl.check_rate_limit("t:3", 2, 60)
    await rl.check_rate_limit("t:3", 2, 60)
    with pytest.raises(RateLimitedError):
        await rl.check_rate_limit("t:3", 2, 60)
    assert len(fake.store["rl:t:3"]) == 2  # the rejected hit removed itself
    assert not rl._hits  # in-memory backend untouched


async def test_redis_outage_fails_open(monkeypatch):
    class _Broken:
        def pipeline(self, transaction=True):
            raise ConnectionError("down")

    monkeypatch.setattr(rl, "_redis_client", lambda: _Broken())
    await rl.check_rate_limit("t:4", 1, 60)
    await rl.check_rate_limit("t:4", 1, 60)  # still allowed while Redis is down
