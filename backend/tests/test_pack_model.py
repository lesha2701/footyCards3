import pytest
from sqlalchemy.exc import IntegrityError

from app.models.pack import Pack, PackOpening, PackOpeningCard


async def test_pack_coach_drop_chance_defaults_to_zero(db_session):
    pack = Pack(slug="test-pack-default-arena", name="Test Pack", price=100, card_count=3)
    db_session.add(pack)
    await db_session.commit()
    await db_session.refresh(pack)
    assert pack.coach_drop_chance == 0.0


async def test_pack_opening_card_rejects_neither_fk_set(db_session):
    from datetime import datetime, timezone

    from app.models.user import User

    user = User(telegram_id=999_200_200, username="pack_slot_test_user")
    db_session.add(user)
    pack = Pack(slug="test-pack-slot-arena", name="Test Pack", price=100, card_count=1)
    db_session.add(pack)
    await db_session.flush()
    opening = PackOpening(user_id=user.id, pack_id=pack.id, price_paid=100, created_at=datetime.now(timezone.utc))
    db_session.add(opening)
    await db_session.flush()

    db_session.add(PackOpeningCard(opening_id=opening.id, user_card_id=None, user_coach_card_id=None, is_new=True))
    with pytest.raises(IntegrityError):
        await db_session.commit()
    await db_session.rollback()
