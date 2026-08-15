from app.models.enums import CardSource, TransactionType, WheelPrizeType, WheelSpinSource
from app.models.wheel import WheelPrize, WheelSpin
from tests.factories import create_wheel_prize


async def test_wheel_prize_model_roundtrip(db_session):
    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, weight=10, coins_amount=50)
    assert prize.id is not None
    assert prize.weight == 10
    assert prize.coins_amount == 50
    assert prize.is_active is True


async def test_wheel_spin_model_roundtrip(db_session):
    from tests.factories import create_player, create_pack, get_user_by_telegram_id
    from tests.utils import telegram_headers

    prize = await create_wheel_prize(db_session, prize_type=WheelPrizeType.coins, coins_amount=25)
    spin = WheelSpin(user_id=1, prize_id=prize.id, source=WheelSpinSource.free, coins_amount=25)
    db_session.add(spin)
    await db_session.commit()
    await db_session.refresh(spin)
    assert spin.id is not None
    assert spin.source == WheelSpinSource.free


def test_new_enum_members_exist():
    assert CardSource.wheel == "wheel"
    assert TransactionType.wheel_spin_cost == "wheel_spin_cost"
    assert TransactionType.wheel_spin_reward == "wheel_spin_reward"
    assert WheelPrizeType.card_rarity == "card_rarity"
