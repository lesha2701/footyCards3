"""«Мордобой», second wave: «Легенда ринга», «Выход на ринг», «Каска», the
knockout GIF share and «Клубный ринг»."""
import random

import pytest
from sqlalchemy import select

import app.core.rate_limit as rate_limit_module
from app.core.timeutil import local_today
from app.models.club_war import ClubWar
from app.models.enums import CardSource, NotificationType, Position, TransactionType
from app.models.game_config import GameConfig
from app.models.monetization import Cosmetic, UserCosmetic
from app.models.notification import Notification
from app.models.transaction import CoinTransaction
from app.services import mordoboi_engine as engine
from app.services import mordoboi_legends, share_service
from app.services.card_creation import create_user_card
from app.services.club_league_service import week_start_for
from tests.factories import create_player, get_user_by_telegram_id
from tests.test_mordoboi import _friend_bout, _ko_ready, _load_match, _pick, _player, _rewrite_state, _set_config
from tests.utils import telegram_headers

API = "/api/v1/mordoboi"


@pytest.fixture(autouse=True)
async def _setup(db_session, tmp_path, monkeypatch):
    rate_limit_module._hits.clear()
    monkeypatch.setattr(share_service, "SHARE_DIR", tmp_path / "share")
    await _set_config(db_session, mordoboi_enabled=True)
    yield


async def _cosmetic(db_session, kind, style_key, name, coins=100, stars=0):
    item = Cosmetic(kind=kind, name=name, style_key=style_key, coins_price=coins, stars_price=stars)
    db_session.add(item)
    await db_session.commit()
    return item.id


# ---------------------------------------------------------------------------
# «Легенда ринга»
# ---------------------------------------------------------------------------

def test_legend_styles_are_readable():
    def picks(style, last=None, n=200):
        s = engine.new_state(
            engine.new_fighter({"power": 70, "speed": 70, "guard": 60, "max_hp": 100, "max_stamina": 200}, None),
            engine.new_fighter({"power": 70, "speed": 70, "guard": 60, "max_hp": 100, "max_stamina": 200}, None),
            3, 4,
        )
        if last:
            s["log"].append({"actions": {"user": last, "opponent": "block"}})
        return [engine.bot_choose(s, "opponent", random.Random(i), style=style) for i in range(n)]

    assert picks("hooker").count("hook") > 100
    assert picks("wall").count("block") > 100
    assert picks("copy", last="uppercut").count("uppercut") > 100
    countered = picks("counter", last="hook")
    assert countered.count("dodge") + countered.count("uppercut") > 120
    assert all(engine.bot_choose(engine.new_state(
        engine.new_fighter({"power": 1, "speed": 1, "guard": 1, "max_hp": 1, "max_stamina": 1}, None),
        engine.new_fighter({"power": 1, "speed": 1, "guard": 1, "max_hp": 100, "max_stamina": 100}, None), 1, 1,
    ), "opponent", random.Random(0), style=style) in engine.ACTIONS for style in engine.STYLES)


def test_every_legend_has_a_known_style_and_rotates_daily():
    assert all(legend[3] in engine.STYLES for legend in mordoboi_legends.LEGENDS)
    today = local_today()
    codes = {mordoboi_legends.legend_for(today.fromordinal(today.toordinal() + i))["code"] for i in range(7)}
    assert len(codes) == len(mordoboi_legends.LEGENDS)


async def test_legend_bout_pays_once_a_day_and_never_blocks_real_bouts(client, db_session, bot_token):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1, mordoboi_legend_reward=150)
    headers, _, _ = await _player(client, db_session, bot_token, 990001)
    info = (await client.get(f"{API}/legend", headers=headers)).json()
    assert info["tagline"] and info["reward"] == 150 and not info["beaten_today"] and info["active_match_id"] is None

    match = (await client.post(f"{API}/legend/start", headers=headers)).json()
    assert match["mode"] == "legend" and match["legend_tagline"] == info["tagline"]
    assert match["opponent"]["look"]["nickname"] == info["nickname"]
    again = (await client.post(f"{API}/legend/start", headers=headers)).json()
    assert again["id"] == match["id"]  # resumes the bout already going
    # A legend bout is not «the one active bout»: a real one can start alongside.
    real = await client.post(f"{API}/matches/bot", headers=headers)
    assert real.status_code == 200
    await client.post(f"{API}/matches/{real.json()['id']}/forfeit", headers=headers)
    listed = (await client.get(f"{API}/matches", headers=headers)).json()
    assert all(m["mode"] == "normal" for m in listed)

    await _rewrite_state(db_session, match["id"], _ko_ready)
    end = (await _pick(client, headers, match, "jab")).json()
    assert end["result"] == "win" and end["reward_coins"] == 150 and end["rating_delta"] == 0
    assert end["can_brutality"] is False

    second = (await client.post(f"{API}/legend/start", headers=headers)).json()
    await _rewrite_state(db_session, second["id"], _ko_ready)
    end2 = (await _pick(client, headers, second, "jab")).json()
    assert end2["result"] == "win" and end2["reward_coins"] == 0  # once a day
    info = (await client.get(f"{API}/legend", headers=headers)).json()
    assert info["beaten_today"] and info["wins_total"] == 2
    user = await get_user_by_telegram_id(db_session, 990001)
    txs = (await db_session.execute(select(CoinTransaction).where(
        CoinTransaction.user_id == user.id, CoinTransaction.type == TransactionType.mordoboi_legend_reward,
    ))).scalars().all()
    assert len(txs) == 1


# ---------------------------------------------------------------------------
# «Выход на ринг»
# ---------------------------------------------------------------------------

async def test_nickname_and_ring_look_go_into_the_bout(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 990010)
    boxer = (await client.get(f"{API}/boxer", headers=headers)).json()
    assert "Железный" in boxer["nickname_options"] and boxer["look"]["nickname"] is None
    assert (await client.put(f"{API}/nickname", headers=headers, json={"nickname": "Хулиган123"})).status_code == 409
    set_ = (await client.put(f"{API}/nickname", headers=headers, json={"nickname": "Железный"})).json()
    assert set_["look"]["nickname"] == "Железный"

    gloves = await _cosmetic(db_session, "ring_gloves", "fire", "Огненные перчатки")
    entrance = await _cosmetic(db_session, "ring_entrance", "fireworks", "Фейерверк")
    for item in (gloves, entrance):
        assert (await client.post(f"/api/v1/cosmetics/{item}/buy", headers=headers)).status_code == 200
    # Bought ring items go into their empty slots; equipping works like frames.
    catalog = (await client.post("/api/v1/cosmetics/equip", headers=headers, json={"kind": "ring_gloves", "cosmetic_id": gloves})).json()
    assert next(i for i in catalog["items"] if i["id"] == gloves)["equipped"]
    match = (await client.post(f"{API}/matches/bot", headers=headers)).json()
    assert match["me"]["look"] == {"nickname": "Железный", "gloves": "fire", "shorts": None, "entrance": "fireworks"}


# ---------------------------------------------------------------------------
# «Каска» and the knockout GIF
# ---------------------------------------------------------------------------

async def _won_bout(client, db_session, bot_token, a, b):
    await _set_config(db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1)
    headers_a, headers_b, user_a, user_b, match = await _friend_bout(client, db_session, bot_token, a, b)
    ids = (user_a.id, user_b.id)
    await _rewrite_state(db_session, match["id"], _ko_ready)
    await _pick(client, headers_a, match, "jab")
    await _pick(client, headers_b, match, "block")
    won = (await client.get(f"{API}/matches/{match['id']}", headers=headers_a)).json()
    assert won["result"] == "win" and won["win_reason"] == "ko"
    return headers_a, headers_b, ids, won


async def test_helmet_bounces_the_brutality_once(client, db_session, bot_token):
    finisher = await _cosmetic(db_session, "brutality", "underpants", "Труханы на голову")
    helmet = await _cosmetic(db_session, "helmet", "helmet", "Каска", coins=200)
    headers_a, headers_b, (a_id, b_id), match = await _won_bout(client, db_session, bot_token, 990020, 990021)
    await client.post(f"/api/v1/cosmetics/{finisher}/buy", headers=headers_a)
    assert (await client.post(f"/api/v1/cosmetics/{helmet}/buy", headers=headers_b)).status_code == 200
    assert (await client.post("/api/v1/cosmetics/equip", headers=headers_b, json={"kind": "helmet", "cosmetic_id": helmet})).status_code == 409

    done = (await client.post(f"{API}/matches/{match['id']}/brutality", headers=headers_a, json={"cosmetic_id": finisher})).json()
    assert done["brutality"]["reflected"] and "Каска соперника отразила" in done["brutality"]["text"]
    seen_by_b = (await client.get(f"{API}/matches/{match['id']}", headers=headers_b)).json()
    assert seen_by_b["brutality"]["reflected"] and "Твоя Каска" in seen_by_b["brutality"]["text"]
    gone = (await db_session.execute(select(UserCosmetic).where(UserCosmetic.user_id == b_id, UserCosmetic.cosmetic_id == helmet))).first()
    assert gone is None  # used up — can be bought again
    assert (await client.post(f"/api/v1/cosmetics/{helmet}/buy", headers=headers_b)).status_code == 200
    notes = (await db_session.execute(select(Notification).where(
        Notification.user_id == b_id, Notification.type == NotificationType.mordoboi_helmet,
    ))).scalars().all()
    assert len(notes) == 1

    # The beaten side may brag about the bounce.
    shared = (await client.post("/api/v1/share/prepare", headers=headers_b, json={"kind": "mordoboi_win", "id": match["id"]})).json()
    assert "моя Каска отразила" in shared["caption"] and shared["image_url"] is None


async def test_knockout_is_shared_as_a_gif(client, db_session, bot_token):
    headers_a, headers_b, _, match = await _won_bout(client, db_session, bot_token, 990030, 990031)
    shared = (await client.post("/api/v1/share/prepare", headers=headers_a, json={"kind": "mordoboi_win", "id": match["id"]})).json()
    assert shared["image_url"].endswith(".gif") and "Я победил игрока" in shared["caption"]
    data = (share_service.SHARE_DIR / shared["image_url"].removeprefix("/static/share/")).read_bytes()
    assert data[:6] in (b"GIF87a", b"GIF89a")
    assert (await client.post("/api/v1/share/prepare", headers=headers_b, json={"kind": "mordoboi_win", "id": match["id"]})).status_code == 409


# ---------------------------------------------------------------------------
# «Клубный ринг»
# ---------------------------------------------------------------------------

async def _club_with_boxer(client, db_session, bot_token, telegram_id, name):
    from app.models.club import Club

    # A new club gets a starting squad drawn from the player pool.
    for position in (Position.GK, Position.GK, Position.LB, Position.LB, Position.CB, Position.CB, Position.RB,
                     Position.RB, Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM, Position.LW,
                     Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)
    headers = telegram_headers(telegram_id, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    club_id = (await client.post("/api/v1/clubs", headers=headers, json={
        "name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000",
    })).json()["id"]
    user = await get_user_by_telegram_id(db_session, telegram_id)
    player = await create_player(db_session, rating=80, position=Position.ST, display_name=f"Ring {telegram_id}")
    await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()
    assert await db_session.get(Club, club_id)
    return club_id, user.id, headers


async def test_club_ring_wins_score_war_points(client, db_session, bot_token):
    from datetime import datetime, timedelta, timezone

    await _set_config(
        db_session, mordoboi_rounds=1, mordoboi_exchanges_per_round=1, club_ring_win_points=30, club_ring_member_cap=300,
        club_war_enabled=True,
    )
    a, user_a, headers_a = await _club_with_boxer(client, db_session, bot_token, 990040, "Ринг А")
    b, user_b, headers_b = await _club_with_boxer(client, db_session, bot_token, 990041, "Ринг Б")
    now = datetime.now(timezone.utc)
    db_session.add(ClubWar(
        week_start=week_start_for(), club_a_id=a, club_b_id=b, status="active",
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(hours=47),
    ))
    await db_session.commit()

    ring = (await client.get(f"{API}/club-ring", headers=headers_a)).json()
    assert ring["active"] and ring["opponent_club"] == "Ринг Б" and ring["win_points"] == 30
    assert [o["user_id"] for o in ring["opponents"]] == [user_b]

    created = (await client.post(f"{API}/matches/challenge", headers=headers_a, json={"receiver_id": user_b})).json()
    match = (await client.post(f"{API}/matches/{created['id']}/accept", headers=headers_b)).json()
    await _rewrite_state(db_session, match["id"], _ko_ready)
    await _pick(client, headers_a, match, "jab")
    end = (await _pick(client, headers_b, match, "block")).json()
    assert end["result"] == "loss"  # B lost, A won

    ring = (await client.get(f"{API}/club-ring", headers=headers_a)).json()
    assert ring["my_points"] == 30 and ring["my_club_points"] == 30 and ring["opponent_club_points"] == 0
    war = (await client.get("/api/v1/clubs/me/war", headers=headers_a)).json()
    me = next(m for m in war["me"]["members"] if m["user_id"] == user_a)
    assert me["ring_points"] == 30 and me["games"] == 1 and me["points"] >= 30
    assert war["me"]["score"] > war["opponent"]["score"]


async def test_club_ring_is_off_without_a_war(client, db_session, bot_token):
    headers, _, _ = await _player(client, db_session, bot_token, 990050)
    ring = (await client.get(f"{API}/club-ring", headers=headers)).json()
    assert ring["active"] is False and ring["opponents"] == []
