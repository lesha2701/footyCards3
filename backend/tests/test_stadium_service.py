import pytest

from app.core.exceptions import ConflictError, NotFoundError
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


async def test_create_stadium_diamond_rarity_rejected_cleanly(db_session):
    # Regression: create_stadium used to pass rarity=diamond straight through
    # to the DB, where ck_stadiums_rarity_not_diamond would raise a raw
    # IntegrityError (unhandled 500) instead of a clean API error. Mirrors
    # Coach's equivalent diamond-rejection guard.
    with pytest.raises(ConflictError):
        await create_stadium(db_session, StadiumCreate(display_name="Diamond Arena", rarity="diamond", boost_pct=0.1))


async def test_update_stadium_rarity_to_diamond_rejected_cleanly(db_session):
    stadium = await create_stadium(db_session, StadiumCreate(display_name="Almost Diamond", rarity="legendary", boost_pct=0.1))
    await db_session.commit()
    with pytest.raises(ConflictError):
        await update_stadium(db_session, stadium.id, StadiumUpdate(rarity="diamond"))
