"""Load test: a wave of brand-new players opening the Mini App at once.

Each virtual player gets a fresh Telegram id, signs its initData with the
backend's bot token (the same HMAC Telegram uses), then does what the app
does on a first open: POST /auth/session, the first screen (the ~38 GETs
the app used to send in parallel, or with --bundle the one GET /home), the
«Пак дебютанта», and a few polls of the home screen.

Run it only against an isolated stand (never prod: real ids, real stats):

    python ops/loadtest/newcomers.py --base http://localhost:18000/api/v1 \
        --token 123456:LOADTEST --users 300 --ramp 30

--ramp spreads the arrivals over N seconds (0 = everyone in the same second).
"""
import argparse
import asyncio
import hashlib
import hmac
import json
import random
import statistics
import time
from collections import defaultdict
from urllib.parse import urlencode

import aiohttp

# What the app asked for on its first screen before `GET /home` (captured
# in a browser): layout, home, popups. --bundle sends /home instead.
HOME_GETS = [
    "/profile/me", "/feature-flags", "/announcement", "/maintenance", "/updates/status",
    "/my-player", "/leagues/status", "/wheel/status", "/newbie", "/starter-offer", "/presence",
    "/academy", "/matches/stats", "/career", "/club-base", "/clubs/me", "/player-tournaments/current",
    "/town", "/artifacts", "/cosmetics", "/packs/daily-offer", "/packs",
    "/streak-rewards/unseen", "/loyalty/unseen", "/comeback-gifts/unseen", "/stars-patron/letters",
    "/muses", "/halloween", "/fans", "/anniversary", "/loyalty/status", "/daily-rewards/calendar", "/tasks",
    "/free-pack/status", "/manager/summary", "/prospect", "/profile/me/attention", "/weekly-top/awards",
]
# With the bundle: /home, plus what it leaves to the app (404 «не в клубе»).
BUNDLE_GETS = ["/home", "/clubs/me"]
# What keeps polling on the home screen afterwards.
POLL_GETS = ["/feature-flags", "/announcement", "/maintenance", "/updates/status"]


def init_data(telegram_id: int, token: str) -> str:
    user = json.dumps({"id": telegram_id, "first_name": "Load", "language_code": "ru"}, separators=(",", ":"))
    data = {"auth_date": str(int(time.time())), "query_id": f"lt{telegram_id}", "user": user}
    check = "\n".join(f"{k}={v}" for k, v in sorted(data.items()))
    secret = hmac.new(b"WebAppData", token.encode(), hashlib.sha256).digest()
    data["hash"] = hmac.new(secret, check.encode(), hashlib.sha256).hexdigest()
    return urlencode(data)


class Stats:
    def __init__(self):
        self.lat = defaultdict(list)
        self.codes = defaultdict(lambda: defaultdict(int))
        self.journeys = []
        self.base = ""

    async def call(self, client, method, path, headers, label=None):
        label = label or path
        t = time.perf_counter()
        try:
            async with client.request(method, self.base + path, headers=headers) as r:
                await r.read()
                code = r.status
        except Exception as exc:  # timeout, reset, refused
            code = type(exc).__name__
        self.lat[label].append(time.perf_counter() - t)
        self.codes[label][code] += 1
        return code


async def newcomer(client, stats, telegram_id, token, delay, home_rounds, first_screen):
    await asyncio.sleep(delay)
    start = time.perf_counter()
    headers = {"X-Telegram-Init-Data": init_data(telegram_id, token)}
    ok = await stats.call(client, "POST", "/auth/session", headers) == 200
    if ok:
        await asyncio.gather(*(stats.call(client, "GET", p, headers) for p in first_screen))
        await stats.call(client, "POST", "/newbie/first-pack", headers)
        for _ in range(home_rounds):
            await asyncio.sleep(random.uniform(1, 4))
            await asyncio.gather(*(stats.call(client, "GET", p, headers) for p in POLL_GETS))
    stats.journeys.append((ok, time.perf_counter() - start))


def pct(values, p):
    values = sorted(values)
    return values[min(len(values) - 1, int(len(values) * p))] if values else 0


def report(stats, wall):
    print(f"\n{'endpoint':28} {'n':>5} {'p50':>7} {'p95':>7} {'max':>7}  codes")
    for label in sorted(stats.lat, key=lambda k: -pct(stats.lat[k], 0.95)):
        v = stats.lat[label]
        codes = " ".join(f"{c}:{n}" for c, n in sorted(stats.codes[label].items(), key=str))
        print(f"{label:28} {len(v):5} {pct(v, .5):7.2f} {pct(v, .95):7.2f} {max(v):7.2f}  {codes}")
    total = sum(len(v) for v in stats.lat.values())
    errors = sum(n for c in stats.codes.values() for code, n in c.items() if code != 200)
    journeys = [d for ok, d in stats.journeys]
    print(f"\nrequests {total}, not-200 {errors}, {total / wall:.0f} req/s over {wall:.0f}s")
    print(f"journeys {len(journeys)}: ok {sum(ok for ok, _ in stats.journeys)}, "
          f"p50 {statistics.median(journeys):.1f}s, p95 {pct(journeys, .95):.1f}s")


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://localhost:18000/api/v1")
    ap.add_argument("--token", required=True)
    ap.add_argument("--users", type=int, default=100)
    ap.add_argument("--ramp", type=float, default=10)
    ap.add_argument("--home-rounds", type=int, default=3)
    ap.add_argument("--id-base", type=int, default=None)
    ap.add_argument("--bundle", action="store_true", help="the first screen as one GET /home")
    args = ap.parse_args()

    id_base = args.id_base or 9_000_000_000 + int(time.time()) % 1_000_000 * 1000
    stats = Stats()
    stats.base = args.base
    timeout = aiohttp.ClientTimeout(total=60)
    async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(limit=0, force_close=True), timeout=timeout) as client:
        t = time.perf_counter()
        await asyncio.gather(*(
            newcomer(client, stats, id_base + i, args.token, random.uniform(0, args.ramp), args.home_rounds,
                     BUNDLE_GETS if args.bundle else HOME_GETS)
            for i in range(args.users)
        ))
        report(stats, time.perf_counter() - t)


if __name__ == "__main__":
    asyncio.run(main())
