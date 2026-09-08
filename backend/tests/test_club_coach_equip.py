import pytest
import pytest_asyncio
from sqlalchemy import select

from app.core.exceptions import ConflictError
from app.models.club_coach_card import ClubCoachCard
from app.models.club_lineup import ClubLineup
from app.models.coach import Coach, CoachBoost
from app.models.enums import ClubCoachCardSource, CoachBoostType, Position, Rarity
from app.schemas.club_squad import ClubCoachSetRequest
from app.services.club_squad_service import set_club_coach
from tests.factories import create_player, get_user_by_telegram_id
from tests.utils import telegram_headers

# Mirrors test_club_squad.py's own fixture/helper pattern exactly (autouse
# position-pool seeding + local _register_only/_create_club helpers) since
# that file's autouse fixture is file-scoped in this codebase's test setup
# and must be repeated here.


@pytest_asyncio.fixture(autouse=True)
async def _seed_position_pool(db_session):
    for position in (Position.GK, Position.GK, Position.GK):
        await create_player(db_session, position=position)
    for position in (Position.LB, Position.LB, Position.CB, Position.CB, Position.RB, Position.RB):
        await create_player(db_session, position=position)
    for position in (Position.CDM, Position.CM, Position.CAM, Position.LM, Position.RM):
        await create_player(db_session, position=position)
    for position in (Position.LW, Position.LW, Position.ST, Position.ST, Position.RW):
        await create_player(db_session, position=position)


async def _register_only(client, bot_token, telegram_id):
    resp = await client.post("/api/v1/auth/session", headers=telegram_headers(telegram_id, bot_token))
    assert resp.status_code == 200


async def _create_club(client, bot_token, telegram_id, name):
    await _register_only(client, bot_token, telegram_id)
    headers = telegram_headers(telegram_id, bot_token)
    resp = await client.post(
        "/api/v1/clubs", headers=headers,
        json={"name": name, "club_type": "open", "logo_shape": "shield", "logo_color": "#FF0000"},
    )
    assert resp.status_code == 200
    return resp.json(), headers


async def _seed_club_with_captain_and_lineup(client, db_session, bot_token, telegram_id, name):
    club, headers = await _create_club(client, bot_token, telegram_id, name)
    captain = await get_user_by_telegram_id(db_session, telegram_id)
    lineup = (await db_session.execute(select(ClubLineup).where(ClubLineup.club_id == club["id"]))).scalar_one()
    return club, captain, lineup


async def test_captain_can_equip_and_clear_club_coach(client, db_session, bot_token):
    club, captain, lineup = await _seed_club_with_captain_and_lineup(
        client, db_session, bot_token, 840100, "Клуб с тренером"
    )

    coach = Coach(display_name="Equip Test Coach", rarity=Rarity.epic)
    coach.boosts = [
        CoachBoost(boost_type=CoachBoostType.ATTACK_CENTRAL, magnitude=4.0),
        CoachBoost(boost_type=CoachBoostType.DEFENCE_CENTRAL, magnitude=4.0),
    ]
    db_session.add(coach)
    await db_session.flush()
    card = ClubCoachCard(club_id=club["id"], coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(card)
    await db_session.commit()

    result = await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=card.id))
    assert result.coach is not None
    assert result.coach.display_name == "Equip Test Coach"
    assert len(result.coach.boosts) == 2

    cleared = await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=None))
    assert cleared.coach is None


async def test_cannot_equip_another_clubs_coach_card(client, db_session, bot_token):
    club, captain, lineup = await _seed_club_with_captain_and_lineup(
        client, db_session, bot_token, 840101, "Клуб без чужого тренера"
    )
    other_club, _other_headers = await _create_club(client, bot_token, 840102, "Другой клуб")

    coach = Coach(display_name="Foreign Coach", rarity=Rarity.common)
    coach.boosts = [CoachBoost(boost_type=CoachBoostType.GOALKEEPING, magnitude=2.0)]
    db_session.add(coach)
    await db_session.flush()
    foreign_card = ClubCoachCard(club_id=other_club["id"], coach_id=coach.id, serial_number=1, source=ClubCoachCardSource.club_pack)
    db_session.add(foreign_card)
    await db_session.commit()

    with pytest.raises(ConflictError):
        await set_club_coach(db_session, captain, ClubCoachSetRequest(club_coach_card_id=foreign_card.id))
