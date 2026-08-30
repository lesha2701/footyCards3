import pytest

from app.core.exceptions import ConflictError
from app.models.enums import Position
from app.services import club_formation_service as svc


def test_default_formation_is_4_3_3():
    assert svc.DEFAULT_FORMATION == "4-3-3"


def test_every_formation_has_eleven_slots_and_one_gk():
    for formation, slots in svc.CLUB_FORMATIONS.items():
        assert len(slots) == 11, formation
        gk_slots = [s for s in slots if s.category == "GK"]
        assert len(gk_slots) == 1, formation
        assert gk_slots[0].ideal_position == Position.GK


def test_get_formation_slots_returns_registered_list():
    slots = svc.get_formation_slots("4-4-2")
    assert [s.code for s in slots] == ["GK", "DEF1", "DEF2", "DEF3", "DEF4", "MID1", "MID2", "MID3", "MID4", "FWD1", "FWD2"]
    assert [s.ideal_position for s in slots if s.category == "MID"] == [Position.LM, Position.CM, Position.CM, Position.RM]


def test_get_formation_slots_rejects_unknown_formation():
    with pytest.raises(ConflictError):
        svc.get_formation_slots("4-2-4")


def test_get_slots_by_code_keys_match_codes():
    by_code = svc.get_slots_by_code("3-5-2")
    assert set(by_code.keys()) == {"GK", "DEF1", "DEF2", "DEF3", "MID1", "MID2", "MID3", "MID4", "MID5", "FWD1", "FWD2"}
    assert by_code["MID2"].ideal_position == Position.CDM


def test_5_3_2_has_five_defenders_and_two_wide_backs():
    slots = svc.get_formation_slots("5-3-2")
    def_positions = [s.ideal_position for s in slots if s.category == "DEF"]
    assert def_positions.count(Position.CB) == 3
    assert Position.LB in def_positions and Position.RB in def_positions
