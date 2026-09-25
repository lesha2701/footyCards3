import pytest
from sqlalchemy import select

from app.core.exceptions import ConflictError, ForbiddenError
from app.models.enums import Position
from app.models.personal_squad import PersonalSquad
from app.schemas.personal_squad import (
    PersonalSquadSetRequest, PersonalSquadSlotIn, PersonalSquadTacticsRequest,
)
from app.services import personal_squad_service as svc
from tests.factories import create_player
from tests.player_tournament_helpers import give_cards_for_formation, make_ready_user, make_user


def _payload(pairs):
    return PersonalSquadSetRequest(slots=[PersonalSquadSlotIn(slot_code=s.code, user_card_id=c.id) for s, c in pairs])


async def test_templates_are_seeded_once_with_first_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841001)
    templates = await svc.list_templates(db_session, user)
    assert [t.template_index for t in templates] == [1, 2, 3, 4, 5]
    assert [t.is_active for t in templates] == [True, False, False, False, False]
    again = await svc.list_templates(db_session, user)
    assert len(again) == 5
    rows = (await db_session.execute(select(PersonalSquad).where(PersonalSquad.user_id == user.id))).scalars().all()
    assert len(rows) == 5


async def test_full_squad_is_complete(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 841002)
    assert await svc.is_squad_complete(db_session, user.id) is True
    squad = await svc.get_squad(db_session, user)
    assert squad.is_complete is True
    assert len(squad.slots) == 11


async def test_wrong_position_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841003)
    pairs = await give_cards_for_formation(db_session, user)
    striker = await create_player(db_session, position=Position.ST)
    from app.models.card import UserCard
    from app.models.enums import CardSource
    card = UserCard(owner_id=user.id, player_id=striker.id, source=CardSource.seed)
    db_session.add(card)
    await db_session.commit()
    await db_session.refresh(card)
    gk_slot = pairs[0][0]
    with pytest.raises(ConflictError):
        await svc.set_squad_cards(db_session, user, PersonalSquadSetRequest(
            slots=[PersonalSquadSlotIn(slot_code=gk_slot.code, user_card_id=card.id)]))


async def test_foreign_card_rejected(client, db_session, bot_token):
    owner = await make_user(client, db_session, bot_token, 841004)
    thief = await make_user(client, db_session, bot_token, 841005)
    pairs = await give_cards_for_formation(db_session, owner)
    slot, card = pairs[0]
    with pytest.raises(ForbiddenError):
        await svc.set_squad_cards(db_session, thief, PersonalSquadSetRequest(
            slots=[PersonalSquadSlotIn(slot_code=slot.code, user_card_id=card.id)]))


async def test_duplicate_slot_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841006)
    pairs = await give_cards_for_formation(db_session, user)
    slot, card = pairs[1]
    other = pairs[2][1]
    with pytest.raises(ConflictError):
        await svc.set_squad_cards(db_session, user, PersonalSquadSetRequest(slots=[
            PersonalSquadSlotIn(slot_code=slot.code, user_card_id=card.id),
            PersonalSquadSlotIn(slot_code=slot.code, user_card_id=other.id),
        ]))


async def test_formation_change_clears_slots_missing_in_new_formation(client, db_session, bot_token):
    user = await make_ready_user(client, db_session, bot_token, 841007)
    squad = await svc.set_tactics(db_session, user, PersonalSquadTacticsRequest(
        formation="4-4-2", mentality="ATTACKING", playstyle="WING_PLAY"))
    assert squad.formation == "4-4-2"
    assert (squad.mentality, squad.playstyle) == ("ATTACKING", "WING_PLAY")
    assert squad.is_complete is False  # FWD3 gone, MID4/... empty
    codes_with_cards = {s.slot_code for s in squad.slots if s.user_card_id}
    assert "FWD3" not in codes_with_cards


async def test_unknown_tactics_rejected(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841008)
    with pytest.raises(ConflictError):
        await svc.set_tactics(db_session, user, PersonalSquadTacticsRequest(
            formation="9-9-9", mentality="BALANCED", playstyle="WING_PLAY"))


async def test_activate_template_switches_active(client, db_session, bot_token):
    user = await make_user(client, db_session, bot_token, 841009)
    await svc.list_templates(db_session, user)
    await svc.activate_template(db_session, user, 3)
    templates = await svc.list_templates(db_session, user)
    assert [t.template_index for t in templates if t.is_active] == [3]


async def test_card_no_longer_owned_is_excluded_from_resolve(client, db_session, bot_token):
    seller = await make_ready_user(client, db_session, bot_token, 841010)
    buyer = await make_user(client, db_session, bot_token, 841011)
    _squad, cards = await svc.resolve_active_squad(db_session, seller.id)
    assert len(cards) == 11
    moved = cards[0][0]
    moved.owner_id = buyer.id  # simulates a trade
    db_session.add(moved)
    await db_session.commit()
    _squad, cards = await svc.resolve_active_squad(db_session, seller.id)
    assert len(cards) == 10
    assert await svc.is_squad_complete(db_session, seller.id) is False


async def test_formation_change_drops_cards_that_no_longer_fit_slot_category(client, db_session, bot_token):
    # In every current CLUB_FORMATIONS entry a slot code encodes its category
    # (DEF*/MID*/FWD*), so no surviving code changes category between real
    # formations. Simulate a misfit row (as a future formation table or a
    # legacy row could produce) by inserting it directly, bypassing validation.
    from app.models.card import UserCard
    from app.models.enums import CardSource
    from app.models.personal_squad import PersonalSquadCard

    user = await make_ready_user(client, db_session, bot_token, 841012)
    striker = await create_player(db_session, position=Position.ST)
    misfit = UserCard(owner_id=user.id, player_id=striker.id, source=CardSource.seed)
    db_session.add(misfit)
    await db_session.commit()
    await db_session.refresh(misfit)
    misfit_id = misfit.id

    squad = await svc.get_squad(db_session, user)
    def_slot = next(s for s in squad.slots if s.slot_code == "DEF1")
    fitting_id = def_slot.user_card_id
    row = (await db_session.execute(
        select(PersonalSquadCard).where(PersonalSquadCard.user_card_id == fitting_id))).scalar_one()
    row.user_card_id = misfit_id  # striker now sits in DEF1
    db_session.add(row)
    await db_session.commit()

    out = await svc.set_tactics(db_session, user, PersonalSquadTacticsRequest(
        formation="4-4-2", mentality="BALANCED", playstyle="WING_PLAY"))
    by_code = {s.slot_code: s.user_card_id for s in out.slots}
    assert by_code["DEF1"] is None  # misfit removed
    assert by_code["DEF2"] is not None and by_code["GK"] is not None  # fitting cards stay


async def test_serialized_squad_hides_cards_no_longer_owned(client, db_session, bot_token):
    seller = await make_ready_user(client, db_session, bot_token, 841020)
    buyer = await make_user(client, db_session, bot_token, 841021)
    seller_id = seller.id
    _squad, cards = await svc.resolve_active_squad(db_session, seller_id)
    moved = cards[0][0]
    moved_id, slot_code = moved.id, cards[0][1].code
    moved.owner_id = buyer.id
    db_session.add(moved)
    await db_session.commit()
    seller = await db_session.get(type(seller), seller_id)
    squad = await svc.get_squad(db_session, seller)
    assert squad.is_complete is False
    slot = next(s for s in squad.slots if s.slot_code == slot_code)
    assert slot.user_card_id is None and slot.player is None
    assert all(s.user_card_id != moved_id for s in squad.slots)
    assert await svc.is_squad_complete(db_session, seller_id) is False
