from app.core.exceptions import ConflictError
from app.models.enums import Position
from app.services.lineup_service import FormationSlot

DEFAULT_FORMATION = "4-3-3"

# Verbatim from the design spec §4. FormationSlot is imported (not redefined)
# from lineup_service — same dataclass shape, but this dict is a completely
# separate registry from lineup_service.FORMATION_SLOTS: club matches must
# never be affected by a future change to the personal engine's single
# formation, and vice versa (see this plan's Global Constraints).
CLUB_FORMATIONS: dict[str, list[FormationSlot]] = {
    "4-3-3": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.CDM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CAM),
        FormationSlot("FWD1", "FWD", Position.LW), FormationSlot("FWD2", "FWD", Position.ST),
        FormationSlot("FWD3", "FWD", Position.RW),
    ],
    "4-4-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.LM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CM), FormationSlot("MID4", "MID", Position.RM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
    "3-5-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.CB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB),
        FormationSlot("MID1", "MID", Position.LM), FormationSlot("MID2", "MID", Position.CDM),
        FormationSlot("MID3", "MID", Position.CM), FormationSlot("MID4", "MID", Position.CAM),
        FormationSlot("MID5", "MID", Position.RM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
    "5-3-2": [
        FormationSlot("GK", "GK", Position.GK),
        FormationSlot("DEF1", "DEF", Position.LB), FormationSlot("DEF2", "DEF", Position.CB),
        FormationSlot("DEF3", "DEF", Position.CB), FormationSlot("DEF4", "DEF", Position.CB),
        FormationSlot("DEF5", "DEF", Position.RB),
        FormationSlot("MID1", "MID", Position.CDM), FormationSlot("MID2", "MID", Position.CM),
        FormationSlot("MID3", "MID", Position.CAM),
        FormationSlot("FWD1", "FWD", Position.ST), FormationSlot("FWD2", "FWD", Position.ST),
    ],
}


def get_formation_slots(formation: str) -> list[FormationSlot]:
    if formation not in CLUB_FORMATIONS:
        raise ConflictError(f"Unknown formation: {formation}")
    return CLUB_FORMATIONS[formation]


def get_slots_by_code(formation: str) -> dict[str, FormationSlot]:
    return {s.code: s for s in get_formation_slots(formation)}
