import pytest

from app.core.exceptions import NotFoundError
from app.schemas.stadium import StadiumCreate, StadiumUpdate
from app.services.stadium_service import create_stadium, get_stadium_or_404, update_stadium


async def test_create_and_get_stadium(db_session):
    stadium = await create_stadium(db_session, StadiumCreate(display_name="Уэмбли", rarity="rare", boost_pct=0.05))
    await db_session.commit()
    fetched = await get_stadium_or_404(db_session, stadium.id)
    assert fetched.display_name == "Уэмбли"
    assert float(fetched.boost_pct) == 0.05


async def test_update_stadium_partial(db_session):
    stadium = await create_stadium(db_session, StadiumCreate(display_name="Camp Nou", rarity="epic", boost_pct=0.08))
    await db_session.commit()
    updated = await update_stadium(db_session, stadium.id, StadiumUpdate(boost_pct=0.12))
    await db_session.commit()
    assert float(updated.boost_pct) == 0.12
    assert updated.display_name == "Camp Nou"  # untouched


async def test_get_missing_stadium_raises(db_session):
    with pytest.raises(NotFoundError):
        await get_stadium_or_404(db_session, 999999)


async def test_diamond_rarity_rejected_by_db(db_session):
    from sqlalchemy.exc import IntegrityError
    from app.models.stadium import Stadium
    db_session.add(Stadium(display_name="X", rarity="diamond", boost_pct=0.1))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
