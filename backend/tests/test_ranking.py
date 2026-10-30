from app.models.enums import CardSource
from app.schemas.ranking import RankingMetric
from app.services import ranking_service
from app.services.card_creation import create_user_card
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers


async def test_ranking_cards_count_orders_users_by_card_total(client, db_session, bot_token):
    headers_a = telegram_headers(760001, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_a)
    user_a = await get_user_by_telegram_id(db_session, 760001)

    headers_b = telegram_headers(760002, bot_token)
    await client.post("/api/v1/auth/session", headers=headers_b)
    user_b = await get_user_by_telegram_id(db_session, 760002)

    player = await create_player(db_session)
    for _ in range(3):
        await create_user_card(db_session, user_b.id, player.id, CardSource.seed)
    await db_session.commit()

    resp = await client.get("/api/v1/leaderboard/ranking", headers=headers_a, params={"metric": "cards_count"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["metric"] == "cards_count"
    assert body["top"][0]["user_id"] == user_b.id
    assert body["top"][0]["value"] == 3
    # The caller (user_a, 0 cards) still gets their own rank even though it's below the leader.
    assert body["me"]["user_id"] == user_a.id
    assert body["me"]["value"] == 0
    assert body["me"]["rank"] == 2


async def test_ranking_reports_rank_when_outside_top_list(client, db_session, bot_token):
    for telegram_id in (760010, 760011, 760012):
        await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))

    # Distinct values for every user avoid relying on any particular
    # tie-break order for equal referral counts.
    leader = await get_user_by_telegram_id(db_session, 760010)
    leader.referral_count = 5
    middle = await get_user_by_telegram_id(db_session, 760011)
    middle.referral_count = 2
    db_session.add_all([leader, middle])
    await db_session.commit()

    last_place = await get_user_by_telegram_id(db_session, 760012)

    result = await ranking_service.get_ranking(db_session, RankingMetric.referral_count, last_place, limit=1)
    assert len(result.top) == 1
    assert result.top[0].user_id == leader.id
    # Not among the top-1 shown, but their own position is still reported.
    assert result.me is not None
    assert result.me.user_id == last_place.id
    assert result.me.rank == 3


async def test_ranking_excludes_admins(client, db_session, bot_token):
    admin_headers = telegram_headers(999000001, bot_token)  # matches ADMIN_TELEGRAM_IDS in conftest
    await client.post("/api/v1/auth/session", headers=admin_headers)
    admin = await get_user_by_telegram_id(db_session, 999000001)
    admin.referral_count = 999
    db_session.add(admin)
    await db_session.commit()

    headers = telegram_headers(760020, bot_token)
    await client.post("/api/v1/auth/session", headers=headers)
    user = await get_user_by_telegram_id(db_session, 760020)
    user.referral_count = 1
    db_session.add(user)
    await db_session.commit()

    resp = await client.get("/api/v1/leaderboard/ranking", headers=headers, params={"metric": "referral_count"})
    assert resp.status_code == 200
    body = resp.json()
    assert all(entry["user_id"] != admin.id for entry in body["top"])
    assert body["top"][0]["user_id"] == user.id


async def test_rank_of_matches_the_full_ranking_for_every_metric_shape(client, db_session, bot_token):
    """The database's row_number() places each user exactly where he stands
    in the full ordered ranking — ties broken by the earlier account — for a
    plain column, a sum and an aggregate (cards)."""
    ids = (760020, 760021, 760022, 760023, 760024)
    for telegram_id in ids:
        await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    users = [await get_user_by_telegram_id(db_session, t) for t in ids]
    for user, rating in zip(users, (1200, 1500, 1200, 900, 1500)):
        user.tactics_rating = rating
        db_session.add(user)
    player = await create_player(db_session)
    for user, n in zip(users, (2, 0, 4, 2, 1)):
        for _ in range(n):
            await create_user_card(db_session, user.id, player.id, CardSource.seed)
    await db_session.commit()

    for metric in (RankingMetric.tactics_rating, RankingMetric.league_rating, RankingMetric.cards_count):
        full = (await db_session.execute(ranking_service.ranking_statement(metric))).all()
        expected = {user.id: (i + 1, value) for i, (user, value) in enumerate(full)}
        for user in users:
            rank, value = await ranking_service.rank_of(db_session, metric, user.id)
            assert (rank, int(value)) == (expected[user.id][0], int(expected[user.id][1])), metric
