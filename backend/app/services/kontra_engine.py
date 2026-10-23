"""«Контратака» — pure, seeded battle engine (no DB), like mordoboi_engine.

Two squads of up to 5 units (sides "me" and "foe"; a boss fight has a
single "foe" unit). A turn meter decides who acts: every tick each living
unit gains its speed, the first to reach TURN_METER acts and spends it.

Units carry a basic strike, up to two active abilities with cooldowns and
an optional passive; effects (stun, yellow card, slow, shield, taunt,
blind, injury, haste) tick at the start of their owner's turn.

The state is a JSON-able dict (kontra_battles.server_state). Every random
roll comes from `rng(state)`, seeded per battle and per action, so a
retried request or a replayed log reproduces the same numbers.

Flow: `advance(state)` moves time to the next actor and applies its
start-of-turn effects; if that actor is the player's and the battle is
manual, the server waits for `act(...)`; otherwise `ai_choose` picks.
`run_until_input` loops that and returns the new events for the client.
"""
import random
from typing import Optional

SIDES = ("me", "foe")
TURN_METER = 1000
MAX_TICKS = 100_000

ROLES = ("attacker", "midfielder", "defender", "goalkeeper")
ROLE_BY_POSITION = {
    "ST": "attacker", "CF": "attacker", "LW": "attacker", "RW": "attacker",
    "CAM": "midfielder", "CM": "midfielder", "CDM": "midfielder", "LM": "midfielder", "RM": "midfielder",
    "CB": "defender", "LB": "defender", "RB": "defender", "LWB": "defender", "RWB": "defender",
    "GK": "goalkeeper",
}
ROLE_LABELS = {"attacker": "Нападающий", "midfielder": "Полузащитник", "defender": "Защитник", "goalkeeper": "Вратарь"}
FAST_POSITIONS = {"LW": 14, "RW": 14, "LM": 10, "RM": 10, "LWB": 10, "RWB": 10, "CAM": 6, "ST": 4, "CF": 6}

# code -> (name, cooldown, target kind, description). Target kinds: enemy,
# enemy_all, enemy_random, ally, ally_all, self.
ABILITIES: dict[str, tuple[str, int, str, str]] = {
    "strike": ("Удар", 0, "enemy", "100% атаки по одному сопернику"),
    # attacker
    "hat_trick": ("Хет-трик", 3, "enemy_random", "Три удара по 45% атаки по случайным соперникам"),
    "penalty": ("Пенальти", 3, "enemy_weakest", "160% атаки по самому слабому, +50% если у него меньше 30% HP"),
    "bicycle": ("Удар через себя", 4, "enemy", "130% атаки и 40% шанс оглушить на ход"),
    # midfielder
    "through_ball": ("Пас в разрез", 3, "ally", "80% атаки по сопернику и +50% шкалы хода союзнику"),
    "pressing": ("Прессинг", 3, "enemy", "90% атаки, снимает щит и даёт «жёлтую» (−30% защиты, 2 хода)"),
    "conductor": ("Дирижёр", 4, "ally_all", "+30% шкалы хода всему отряду"),
    # defender
    "tackle": ("Подкат", 3, "enemy", "110% атаки и замедление (−30% скорости, 2 хода)"),
    "wall": ("Стенка", 4, "self", "Провокация на 2 хода и щит 20% HP"),
    "offside": ("Офсайдная ловушка", 5, "enemy_all", "Следующий удар каждого соперника — промах"),
    # goalkeeper
    "save": ("Сейв", 3, "ally_weakest", "Щит 25% HP самому раненому союзнику на 2 хода"),
    "medics": ("Медбригада", 4, "ally_all", "Лечит отряд на 15% HP"),
    "long_kick": ("Длинный выбив", 3, "enemy", "100% атаки и +25% шкалы хода всем нападающим"),
    # bosses
    "boss_slam": ("Разнос", 2, "enemy_all", "70% атаки по всему отряду"),
    "boss_card": ("Красная карточка", 3, "enemy", "200% атаки и оглушение"),
    "boss_chant": ("Кричалка", 3, "enemy_all", "«Травма» на 2 хода всему отряду"),
}
ROLE_ABILITIES = {
    "attacker": ("penalty", "hat_trick", "bicycle"),
    "midfielder": ("pressing", "through_ball", "conductor"),
    "defender": ("tackle", "wall", "offside"),
    "goalkeeper": ("save", "medics", "long_kick"),
}

# Passives: tier (diamond / path / my_player) or the legendary role passive.
PASSIVES: dict[str, tuple[str, str]] = {
    "star_hour": ("Звёздный час", "Раз за бой, когда HP ниже 30%, сразу получает ещё один ход"),
    "grows": ("Растёт по ходу матча", "+4% атаки за каждый свой ход, до +20%"),
    "captain": ("Капитан", "+8% скорости всему отряду, пока жив"),
    "cold_blood": ("Хладнокровие", "+15% шанса крита"),
    "armor": ("Броня", "Получает на 15% меньше урона"),
    "vision": ("Видение поля", "После своей способности +10% шкалы хода союзникам"),
    "inspire": ("Вдохновение", "Его «Сейв» и «Медбригада» ещё и лечат всех на 5%"),
}
ROLE_PASSIVE = {"attacker": "cold_blood", "defender": "armor", "midfielder": "vision", "goalkeeper": "inspire"}

EFFECT_LABELS = {
    "stun": "Оглушение", "yellow": "Жёлтая карточка", "slow": "Замедление", "shield": "Щит",
    "taunt": "Провокация", "blind": "Офсайд", "injury": "Травма", "haste": "Ускорение",
}


class EngineError(Exception):
    pass


def other(side: str) -> str:
    return "foe" if side == "me" else "me"


def rng(state: dict, salt: str = "") -> random.Random:
    return random.Random(f"kontra:{state['seed']}:{state['actions']}:{salt}")


# ---------------------------------------------------------------------------
# Building units
# ---------------------------------------------------------------------------

def abilities_for(role: str, tier: str) -> list[str]:
    """common: strike; rare: +1 active; epic: +2 actives; legendary-level
    cards (legendary, diamond, «Академия», «Мой игрок») the role's two
    signature actives — plus a passive (passive_for)."""
    first, second, third = ROLE_ABILITIES[role]
    extra = {"common": [], "rare": [first], "epic": [first, second]}.get(tier, [second, third])
    return ["strike", *extra]


def passive_for(role: str, tier: str) -> Optional[str]:
    """Legendary-level cards get a passive: diamond, «Академия» and «Мой игрок»
    their own, a legendary its role's."""
    return {"diamond": "star_hour", "path": "grows", "my_player": "captain", "legendary": ROLE_PASSIVE[role]}.get(tier)


def unit_stats(rating: int, attack: int, defense: int, position: str) -> dict:
    return {
        "max_hp": 800 + defense * 12 + rating * 6,
        "atk": attack * 3 + rating,
        "def": defense * 2,
        "spd": 90 + FAST_POSITIONS.get(position, 0) + max(0, rating - 70) // 2,
        "crit": 10,
        "crit_dmg": 150,
    }


def make_unit(uid: str, side: str, *, name: str, card: Optional[dict], position: str, tier: str,
              rating: int, attack: int, defense: int, crit_bonus: int = 0, gear: Optional[dict] = None) -> dict:
    role = ROLE_BY_POSITION.get(position, "midfielder")
    stats = unit_stats(rating, attack, defense, position)
    stats["crit"] += crit_bonus
    gear = gear or {}
    for stat, pct in (gear.get("pct") or {}).items():
        if stat in ("crit", "crit_dmg"):
            stats[stat] += pct
        elif stat in stats:
            stats[stat] = round(stats[stat] * (100 + pct) / 100)
    passive = passive_for(role, tier)
    if passive == "cold_blood":
        stats["crit"] += 15
    return {
        "id": uid, "side": side, "name": name, "card": card, "position": position, "role": role, "tier": tier,
        **stats, "hp": stats["max_hp"], "meter": 0, "alive": True,
        "abilities": [{"code": c, "cd": 0} for c in abilities_for(role, tier)],
        "passive": passive, "effects": [], "turns": 0, "star_used": False,
        "sets": list(gear.get("sets4") or []),
    }


def make_boss(uid: str, *, name: str, max_hp: int, atk: int, defense: int, spd: int, abilities: list[str]) -> dict:
    return {
        "id": uid, "side": "foe", "name": name, "card": None, "position": "BOSS", "role": "boss", "tier": "boss",
        "max_hp": max_hp, "hp": max_hp, "atk": atk, "def": defense, "spd": spd, "crit": 5, "crit_dmg": 150,
        "meter": 0, "alive": True, "abilities": [{"code": c, "cd": 0} for c in ["strike", *abilities]],
        "passive": None, "effects": [], "turns": 0, "star_used": False, "sets": [],
    }


def apply_team_bonuses(units: list[dict], leader_id: Optional[int], chemistry_pct: int) -> None:
    """Leader aura (by the leader's role) and the squad «химия» bonus."""
    side_units = list(units)
    leader = next((u for u in side_units if u["id"] == leader_id), None)
    aura = {"attacker": ("atk", 8), "midfielder": ("spd", 8), "defender": ("def", 10), "goalkeeper": ("max_hp", 10)}
    for u in side_units:
        if leader is not None:
            stat, pct = aura.get(leader["role"], ("atk", 0))
            u[stat] = round(u[stat] * (100 + pct) / 100)
        if chemistry_pct:
            u["atk"] = round(u["atk"] * (100 + chemistry_pct) / 100)
        u["hp"] = u["max_hp"]
    if leader is not None:
        leader["leader"] = True


def new_battle(seed: str, me: list[dict], foe: list[dict], *, mode: str, max_rounds: int, manual: bool) -> dict:
    return {
        "seed": seed, "actions": 0, "mode": mode, "manual": manual, "auto": not manual,
        "units": [*me, *foe], "turn_of": None, "round": 0, "max_rounds": max_rounds,
        "events": [], "finished": False, "winner": None, "damage_to_foe": 0,
    }


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def unit(state: dict, uid: str) -> dict:
    for u in state["units"]:
        if u["id"] == uid:
            return u
    raise EngineError("Нет такого бойца")


def living(state: dict, side: str) -> list[dict]:
    return [u for u in state["units"] if u["side"] == side and u["alive"]]


def has(u: dict, code: str) -> bool:
    return any(e["code"] == code for e in u["effects"])


def effect(u: dict, code: str) -> Optional[dict]:
    return next((e for e in u["effects"] if e["code"] == code), None)


def add_effect(u: dict, code: str, turns: int, value: int = 0) -> None:
    current = effect(u, code)
    if current:
        current["turns"] = max(current["turns"], turns)
        current["value"] = max(current.get("value", 0), value)
    else:
        u["effects"].append({"code": code, "turns": turns, "value": value})


def speed(state: dict, u: dict) -> int:
    s = u["spd"]
    if has(u, "slow"):
        s = s * 70 // 100
    if has(u, "haste"):
        s = s * 130 // 100
    if any(a["passive"] == "captain" for a in living(state, u["side"])):
        s = s * 108 // 100
    return max(1, s)


def defence(u: dict) -> int:
    d = u["def"]
    if has(u, "yellow"):
        d = d * 70 // 100
    return d


def _attack_power(u: dict) -> int:
    a = u["atk"]
    if u["passive"] == "grows":
        a = a * (100 + min(20, 4 * u["turns"])) // 100
    return a


def _event(state: dict, kind: str, **data) -> dict:
    e = {"kind": kind, "n": len(state["events"]) + 1, **data}
    state["events"].append(e)
    return e


# ---------------------------------------------------------------------------
# Combat
# ---------------------------------------------------------------------------

def _hit(state: dict, attacker: dict, target: dict, mult: int, r: random.Random, ability: str) -> int:
    """mult in %; returns damage dealt (after shield). Misses on «офсайд»."""
    blind = effect(attacker, "blind")
    if blind:
        attacker["effects"].remove(blind)
        _event(state, "miss", actor=attacker["id"], target=target["id"], ability=ability)
        return 0
    dmg = _attack_power(attacker) * mult / 100
    dmg *= 600 / (600 + defence(target))
    crit = r.randint(1, 100) <= attacker["crit"]
    if crit:
        dmg *= attacker["crit_dmg"] / 100
    if target["passive"] == "armor":
        dmg *= 0.85
    dmg = max(1, round(dmg * r.uniform(0.95, 1.05)))
    shield = effect(target, "shield")
    absorbed = 0
    if shield:
        absorbed = min(shield["value"], dmg)
        shield["value"] -= absorbed
        if shield["value"] <= 0:
            target["effects"].remove(shield)
    taken = dmg - absorbed
    target["hp"] = max(0, target["hp"] - taken)
    if attacker["side"] == "me" and target["side"] == "foe":
        state["damage_to_foe"] += taken
    _event(state, "hit", actor=attacker["id"], target=target["id"], ability=ability, damage=taken,
           absorbed=absorbed, crit=crit, hp=target["hp"])
    if target["hp"] <= 0:
        target["alive"] = False
        target["effects"] = []
        _event(state, "down", target=target["id"])
    elif target["passive"] == "star_hour" and not target["star_used"] and target["hp"] * 100 < target["max_hp"] * 30:
        target["star_used"] = True
        target["meter"] = TURN_METER
        _event(state, "passive", target=target["id"], passive="star_hour")
    return taken


def _heal(state: dict, healer: dict, target: dict, pct: int) -> None:
    if not target["alive"]:
        return
    amount = target["max_hp"] * pct // 100
    target["hp"] = min(target["max_hp"], target["hp"] + amount)
    _event(state, "heal", actor=healer["id"], target=target["id"], amount=amount, hp=target["hp"])


def _pick_enemy(state: dict, actor: dict, wanted: Optional[str]) -> dict:
    foes = living(state, other(actor["side"]))
    taunting = [u for u in foes if has(u, "taunt")]
    if taunting:
        return taunting[0]
    if wanted:
        chosen = next((u for u in foes if u["id"] == wanted), None)
        if chosen is not None:
            return chosen
    return min(foes, key=lambda u: (u["hp"], u["id"]))


def _weakest(units: list[dict]) -> dict:
    return min(units, key=lambda u: (u["hp"] / u["max_hp"], u["id"]))


def available(u: dict) -> list[str]:
    return [a["code"] for a in u["abilities"] if a["cd"] == 0]


def act(state: dict, actor_id: str, ability: str, target_id: Optional[str] = None) -> list[dict]:
    """The current actor uses `ability`. Returns the events it produced and
    moves on (does not advance to the next actor)."""
    if state["finished"]:
        raise EngineError("Бой окончен")
    if state["turn_of"] != actor_id:
        raise EngineError("Сейчас ходит другой боец")
    actor = unit(state, actor_id)
    slot = next((a for a in actor["abilities"] if a["code"] == ability), None)
    if slot is None:
        raise EngineError("У бойца нет такой способности")
    if slot["cd"] > 0:
        raise EngineError("Способность ещё перезаряжается")
    start = len(state["events"])
    r = rng(state, f"act:{actor_id}")
    name, cooldown, _kind, _ = ABILITIES[ability]
    _event(state, "ability", actor=actor_id, ability=ability, name=name)
    allies = living(state, actor["side"])
    foes = living(state, other(actor["side"]))

    if ability == "strike":
        _hit(state, actor, _pick_enemy(state, actor, target_id), 100, r, ability)
    elif ability == "hat_trick":
        for _ in range(3):
            pool = living(state, other(actor["side"]))
            if not pool:
                break
            _hit(state, actor, r.choice(pool), 45, r, ability)
    elif ability == "penalty":
        target = _pick_enemy(state, actor, target_id) if any(has(u, "taunt") for u in foes) else _weakest(foes)
        mult = 160 + (50 if target["hp"] * 100 < target["max_hp"] * 30 else 0)
        _hit(state, actor, target, mult, r, ability)
    elif ability == "bicycle":
        target = _pick_enemy(state, actor, target_id)
        if _hit(state, actor, target, 130, r, ability) and target["alive"] and r.random() < 0.4:
            add_effect(target, "stun", 1)
            _event(state, "effect", target=target["id"], effect="stun")
    elif ability == "through_ball":
        _hit(state, actor, _pick_enemy(state, actor, None), 80, r, ability)
        mate = next((u for u in allies if u["id"] == target_id and u["id"] != actor_id), None) \
            or min((u for u in allies if u["id"] != actor_id), key=lambda u: u["meter"], default=None)
        if mate:
            mate["meter"] += TURN_METER // 2
            _event(state, "meter", target=mate["id"], pct=50)
    elif ability == "pressing":
        target = _pick_enemy(state, actor, target_id)
        _hit(state, actor, target, 90, r, ability)
        if target["alive"]:
            target["effects"] = [e for e in target["effects"] if e["code"] != "shield"]
            add_effect(target, "yellow", 2)
            _event(state, "effect", target=target["id"], effect="yellow")
    elif ability == "conductor":
        for mate in allies:
            if mate["id"] != actor_id:
                mate["meter"] += TURN_METER * 30 // 100
        _event(state, "meter", target="team", pct=30)
    elif ability == "tackle":
        target = _pick_enemy(state, actor, target_id)
        _hit(state, actor, target, 110, r, ability)
        if target["alive"]:
            add_effect(target, "slow", 2)
            _event(state, "effect", target=target["id"], effect="slow")
    elif ability == "wall":
        add_effect(actor, "taunt", 2)
        add_effect(actor, "shield", 2, actor["max_hp"] * 20 // 100)
        _event(state, "effect", target=actor_id, effect="taunt")
    elif ability == "offside":
        for f in foes:
            add_effect(f, "blind", 2)
        _event(state, "effect", target="foes", effect="blind")
    elif ability == "save":
        target = next((u for u in allies if u["id"] == target_id), None) or _weakest(allies)
        add_effect(target, "shield", 2, target["max_hp"] * 25 // 100)
        _event(state, "effect", target=target["id"], effect="shield")
    elif ability == "medics":
        for mate in allies:
            _heal(state, actor, mate, 15)
    elif ability == "long_kick":
        _hit(state, actor, _pick_enemy(state, actor, target_id), 100, r, ability)
        for mate in allies:
            if mate["role"] == "attacker":
                mate["meter"] += TURN_METER // 4
    elif ability == "boss_slam":
        for f in foes:
            _hit(state, actor, f, 70, r, ability)
    elif ability == "boss_card":
        target = _pick_enemy(state, actor, None)
        _hit(state, actor, target, 200, r, ability)
        if target["alive"]:
            add_effect(target, "stun", 1)
            _event(state, "effect", target=target["id"], effect="stun")
    elif ability == "boss_chant":
        for f in foes:
            add_effect(f, "injury", 2, max(1, f["max_hp"] * 4 // 100))
        _event(state, "effect", target="foes", effect="injury")

    if actor["passive"] == "inspire" and ability in ("save", "medics"):
        for mate in living(state, actor["side"]):
            _heal(state, actor, mate, 5)
    if actor["passive"] == "vision" and ability != "strike":
        for mate in living(state, actor["side"]):
            if mate["id"] != actor_id:
                mate["meter"] += TURN_METER // 10
    slot["cd"] = cooldown
    state["actions"] += 1
    state["turn_of"] = None
    _check_end(state)
    return state["events"][start:]


def _check_end(state: dict) -> None:
    if state["finished"]:
        return
    if not living(state, "foe"):
        _finish(state, "me")
    elif not living(state, "me"):
        _finish(state, "foe")


def _finish(state: dict, winner: str) -> None:
    state["finished"] = True
    state["winner"] = winner
    state["turn_of"] = None
    _event(state, "end", winner=winner)


def advance(state: dict) -> Optional[dict]:
    """Moves time until someone can act; applies start-of-turn effects.
    Returns the actor (or None if the battle ended on the way)."""
    if state["finished"]:
        return None
    for _ in range(MAX_TICKS):
        ready = [u for u in state["units"] if u["alive"] and u["meter"] >= TURN_METER]
        if ready:
            break
        for u in state["units"]:
            if u["alive"]:
                u["meter"] += speed(state, u)
    else:
        raise EngineError("Бой завис")
    actor = max(ready, key=lambda u: (u["meter"], speed(state, u), u["side"] == "me", u["id"]))
    actor["meter"] -= TURN_METER
    actor["turns"] += 1
    if actor["side"] == "foe":
        state["round"] += 1  # a "round" is one turn of the other side
    for slot in actor["abilities"]:
        slot["cd"] = max(0, slot["cd"] - 1)
    for e in list(actor["effects"]):
        if e["code"] == "injury":
            actor["hp"] = max(0, actor["hp"] - e["value"])
            _event(state, "tick", target=actor["id"], effect="injury", damage=e["value"], hp=actor["hp"])
            if actor["hp"] <= 0:
                actor["alive"] = False
                actor["effects"] = []
                _event(state, "down", target=actor["id"])
                _check_end(state)
                return advance(state) if not state["finished"] else None
    if "medic" in actor["sets"] and actor["hp"] < actor["max_hp"]:
        _heal(state, actor, actor, 5)
    stunned = has(actor, "stun")
    for e in list(actor["effects"]):
        e["turns"] -= 1
        if e["turns"] <= 0:
            actor["effects"].remove(e)
    if state["max_rounds"] and state["round"] > state["max_rounds"]:
        _finish(state, "foe" if state["mode"] != "boss" else "time")
        return None
    if stunned:
        _event(state, "stunned", target=actor["id"])
        state["actions"] += 1
        return advance(state)
    state["turn_of"] = actor["id"]
    _event(state, "turn", actor=actor["id"])
    return actor


def ai_choose(state: dict, actor: dict) -> tuple[str, Optional[str]]:
    """A sensible, deterministic pick: heal/shield when hurt, otherwise the
    strongest ready ability; strike the weakest enemy."""
    ready = available(actor)
    allies = living(state, actor["side"])
    hurt = [u for u in allies if u["hp"] * 100 < u["max_hp"] * 50]
    order = {
        "medics": 0 if len(hurt) >= 2 else 9, "save": 0 if hurt else 9, "wall": 1 if len(allies) > 1 else 9,
        "boss_card": 1, "boss_slam": 1, "boss_chant": 2, "penalty": 2, "hat_trick": 2, "bicycle": 2,
        "pressing": 3, "tackle": 3, "offside": 3, "conductor": 3, "through_ball": 3, "long_kick": 4, "strike": 8,
    }
    ability = min(ready, key=lambda c: (order.get(c, 5), c))
    foes = living(state, other(actor["side"]))
    target = min(foes, key=lambda u: (u["hp"], u["id"]))["id"] if foes else None
    if ability in ("save",):
        target = _weakest(allies)["id"]
    return ability, target


def run_until_input(state: dict) -> list[dict]:
    """Plays every turn that doesn't need the player; stops at the player's
    unit in a manual battle, or at the end. Returns the new events."""
    start = len(state["events"])
    while not state["finished"]:
        actor = unit(state, state["turn_of"]) if state["turn_of"] else advance(state)
        if actor is None:
            break
        if actor["side"] == "me" and not state["auto"]:
            break
        ability, target = ai_choose(state, actor)
        act(state, actor["id"], ability, target)
    return state["events"][start:]
