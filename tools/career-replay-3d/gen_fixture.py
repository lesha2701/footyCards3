"""Builds a 2D career replay (backend career_replay_service) for a hand-made
event log with every kind of goal: frontend fixture for the 3D goal replay."""
import json, sys
from app.services import career_replay_service as r
from app.services.club_formation_service import CLUB_FORMATIONS

def xi(side, formation, off):
    return {"formation": formation, "mentality": "BALANCED", "tactic": {},
            "xi": [[off + i, f"{side.upper()}{fs.code}", fs.code] for i, fs in enumerate(CLUB_FORMATIONS[formation])]}

lineups = {"a": xi("a", "4-3-3", 1), "b": xi("b", "4-4-2", 101)}
A = lambda c: f"A{c}"
B = lambda c: f"B{c}"
events = [
  {"minute": 7, "event_type": "goal", "team": "a", "payload": {"shot_type": "in_box", "action": "pass", "shooter": A("FWD2"), "shooter_id": None, "assist": A("MID2"), "zone": "wing_attack", "aerial_duel": {"won": True}}},
  {"minute": 15, "event_type": "save", "team": "b", "payload": {"shot_type": "in_box", "action": "shoot", "shooter": B("FWD1")}},
  {"minute": 21, "event_type": "goal", "team": "b", "payload": {"shot_type": "long_range", "action": "shoot", "shooter": B("MID2")}},
  {"minute": 33, "event_type": "goal", "team": "a", "payload": {"action": "header", "set_piece": "corner", "taker": A("MID1"), "shooter": A("DEF2")}},
  {"minute": 40, "event_type": "goal", "team": "a", "payload": {"action": "free_kick", "set_piece": "free_kick", "shooter": A("MID3")}},
  {"minute": 52, "event_type": "goal", "team": "b", "payload": {"action": "penalty", "is_penalty": True, "set_piece": "penalty", "shooter": B("FWD2")}},
  {"minute": 70, "event_type": "goal", "team": "a", "payload": {"shot_type": "in_box", "action": "shoot", "shooter": A("FWD1"), "origin": "counter"}},
  {"minute": 70, "event_type": "goal", "team": "b", "payload": {"shot_type": "in_box", "action": "shoot", "shooter": B("FWD1")}},
  {"minute": 80, "event_type": "goal", "team": "b", "payload": {"shot_type": "in_box", "action": "pass", "shooter": B("FWD2"), "assist": B("MID1"), "zone": "wing_attack"}},
  {"minute": 89, "event_type": "goal", "team": "a", "payload": {"shot_type": "empty_net", "shooter": A("FWD3")}},
]
for e in events:
    e["description"] = f"{e['minute']}' гол {e['payload']['shooter']}" if e["event_type"] == "goal" else "сейв"
rep = r.build_replay(20261028, events, lineups)
json.dump({"events": events, "replay": rep}, sys.stdout, ensure_ascii=False)
