"""Regenerates frontend/src/test/chemistryCases.json — the shared fixture
that pins backend chemistry_service.compute_chemistry and frontend
lib/chemistry.ts to the same numbers (tests/test_chemistry.py and
src/test/chemistry.test.ts both assert it). Run after an INTENTIONAL rules
change, review the diff, commit both. Usage (from backend/):

    python -m scripts.gen_chemistry_cases ../frontend/src/test/chemistryCases.json
"""
import json
import sys

from types import SimpleNamespace as NS
from app.services.chemistry_service import FORMATION_LINKS, ChemistryRules, compute_chemistry

SLOTS = {
 "4-3-3": [("GK","GK"),("DEF1","LB"),("DEF2","CB"),("DEF3","CB"),("DEF4","RB"),("MID1","CDM"),("MID2","CM"),("MID3","CAM"),("FWD1","LW"),("FWD2","ST"),("FWD3","RW")],
 "4-4-2": [("GK","GK"),("DEF1","LB"),("DEF2","CB"),("DEF3","CB"),("DEF4","RB"),("MID1","LM"),("MID2","CM"),("MID3","CM"),("MID4","RM"),("FWD1","ST"),("FWD2","ST")],
}
def case(name, formation, rules, players):
    slots = dict(SLOTS[formation])
    pairs=[(NS(player=NS(club=p["club"],country=p["country"],position=p["position"])), NS(code=p["slot"], ideal_position=slots[p["slot"]])) for p in players]
    r = compute_chemistry(pairs, formation, rules, slot_count=len(slots))
    return {"name": name, "formation": formation, "rules": rules.as_dict(), "slot_count": len(slots), "adjacency": [list(e) for e in FORMATION_LINKS[formation]], "players": players,
            "expected": {"team": r.team, "team_max": r.team_max,
                         "links": [{"a":l.a,"b":l.b,"level":l.level,"points":l.points} for l in r.links],
                         "players": {k: {"points":v.points,"link_sum":v.link_sum,"on_position":v.on_position,"rating_bonus":v.rating_bonus} for k,v in r.players.items()}}}

def P(slot, club, country, position): return {"slot":slot,"club":club,"country":country,"position":position}
default = ChemistryRules()
floor1 = ChemistryRules(player_floor=1, off_position_penalty=2, rating_per_point=2)
cases = []
# full 4-3-3: Real Madrid/Spain core, mixed edges
cases.append(case("4-3-3 mixed full squad", "4-3-3", default, [
 P("GK","Real","Spain","GK"), P("DEF1","Barca","Spain","LB"), P("DEF2","Real","Spain","CB"), P("DEF3","Real","France","CB"),
 P("DEF4","Bayern","Germany","RB"), P("MID1","Barca","Spain","CDM"), P("MID2","Real","Spain","CM"), P("MID3","Bayern","Germany","CAM"),
 P("FWD1","Barca","Brazil","LW"), P("FWD2","Real","France","ST"), P("FWD3","Bayern ","Germany","RW")]))
# floor + off-position penalty + empty slots
cases.append(case("4-3-3 partial, floor and off-position", "4-3-3", floor1, [
 P("GK","A","X","GK"), P("DEF2","B","Y","CB"), P("DEF3","C","Z","LB"), P("MID2","C","Z","CM"), P("FWD2","D","W","LW")]))
# all strong
cases.append(case("4-4-2 all one club and country", "4-4-2", default, [
 P(s, "Milan", "Italy", pos) for s, pos in SLOTS["4-4-2"]]))
# no links, empty club strings never link
cases.append(case("4-4-2 nothing in common, blank clubs", "4-4-2", ChemistryRules(thresholds=(2,3,5), player_floor=2, player_max=2), [
 P(s, "", f"C{i}", pos) for i, (s, pos) in enumerate(SLOTS["4-4-2"])]))
json.dump(cases, open(sys.argv[1], "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(json.dumps([c["expected"]["team"] for c in cases]))
