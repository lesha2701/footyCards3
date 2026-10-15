import random
from dataclasses import dataclass, field

# Distinct from match_service.py's personal-engine _EVENT_DESCRIPTIONS (phrased "your team" vs.
# "{them}") — a tournament replay is watched from a neutral standpoint by any club's members, so
# every description names the real club instead. Never names an individual player, matching the
# personal engine's own team-level-only phrasing. Exactly 7 event types — confirmed exhaustive:
# simulate_match only ever resolves one of these 7 shot/tackle outcomes per Chance.
_EVENT_DESCRIPTIONS: dict[str, list[str]] = {
    "goal": [
        "⚽ Гол! {club} открывает счёт!",
        "⚽ ГОЛ! {club} забивает!",
        "⚽ {club} находит путь в ворота!",
    ],
    "shot": [
        "🎯 {club} бьёт — мимо ворот",
        "🎯 Удар {club} уходит выше перекладины",
    ],
    "save": [
        "🧤 Вратарь {club} спасает свою команду!",
        "🧤 Отличный сейв на счету {club}!",
    ],
    "blocked": [
        "🛡️ Защитник {club} блокирует удар!",
        "🛡️ {club} накрывает удар в последний момент!",
    ],
    "pass_failed": [
        "❌ Пас {club} не находит адресата — атака сорвана",
        "❌ {club} теряет мяч в решающей передаче",
    ],
    "tackle_won": [
        "🛡️ Защитник {club} чисто отбирает мяч в подкате!",
        "🛡️ {club} прерывает атаку точным подкатом",
    ],
    "foul_stopped": [
        "🟨 Фол защитника {club} останавливает атаку",
        "🟨 {club} фолит, чтобы сорвать атаку",
    ],
}

# Tactic-flavored variants for a standout ("HIGH"/"VERY_HIGH" quality) goal —
# mixed into the generic pool below rather than replacing it, so a
# tactic-flavored description appears "occasionally", never every time (spec
# §11). Only "goal" gets flavor text — spec's own 3 examples are all
# scoring-moment phrasing, and extending this to every event type would be
# scope beyond what's asked.
_PLAYSTYLE_GOAL_FLAVOR: dict[str, list[str]] = {
    "COUNTER_ATTACK": [
        "⚡ Быстрая контратака {club} застаёт соперника врасплох!",
        "⚡ {club} убегает в разрушительную контратаку!",
    ],
    "HIGH_PRESS": [
        "🔥 Высокий прессинг {club} перехватывает мяч — и сразу гол!",
        "🔥 {club} выигрывает мяч прессингом в опасной зоне!",
    ],
    "CENTRAL_PLAY": ["🎯 {club} находит момент через центр поля!"],
    "WING_PLAY": ["🎯 {club} врывается с фланга и не оставляет шансов!"],
    "POSSESSION": ["🎯 {club} терпеливо выводит мяч на убойную позицию!"],
}


OPENER_PHRASE = "открывает счёт"


def score_phrase(own: int, opp: int) -> str:
    """What a goal did to the score, from the scorer's side, `own`/`opp`
    counted after it: the opener, an equaliser, going ahead, extending a
    lead or pulling one back."""
    if own + opp == 1:
        return OPENER_PHRASE
    if own == opp:
        return "сравнивает счёт"
    if own == opp + 1:
        return "выходит вперёд"
    if own > opp:
        return "увеличивает преимущество"
    return "сокращает отставание"


def fix_goal_descriptions(events: list[dict]) -> None:
    """Goal texts are drawn before the score is known: "открывает счёт" may
    land on any goal. Rewrites it to fit the running score — a separate pass
    over the finished log, so it draws no random numbers and never changes
    a result."""
    goals = {"a": 0, "b": 0}
    for event in events:
        team = event.get("team")
        if event.get("event_type") != "goal" or team not in goals:
            continue
        goals[team] += 1
        text = event.get("description") or ""
        if OPENER_PHRASE in text:
            other = "b" if team == "a" else "a"
            event["description"] = text.replace(OPENER_PHRASE, score_phrase(goals[team], goals[other]))


def _describe_event(
    event_type: str, team: str, club_a_name: str, club_b_name: str,
    playstyle: str | None = None, quality: str | None = None,
) -> str:
    club = club_a_name if team == "a" else club_b_name
    pool = _EVENT_DESCRIPTIONS[event_type]
    if event_type == "goal" and quality in ("HIGH", "VERY_HIGH") and playstyle in _PLAYSTYLE_GOAL_FLAVOR:
        pool = pool + _PLAYSTYLE_GOAL_FLAVOR[playstyle]
    template = random.choice(pool)
    return template.format(club=club)


from app.services import club_tactical_matchup_service
from app.services.card_skill_effects import aerial_alpha, aerial_shot_roll, effect_of, skill_roll
from app.services.path_talent_effects import dynamic_bonus, dynamic_note, with_bonus

# Maps a Chance's quality tier (club_tactical_matchup_service.Chance.quality)
# onto the same units situation.bias used to nudge effective rating in the
# old engine (spec §6.7).
QUALITY_BIAS: dict[str, float] = {"LOW": -6, "NORMAL": 0, "HIGH": 5, "VERY_HIGH": 10}


# --- Resolution -------------------------------------------------------------
# The functions below decide the OUTCOME of each chance produced by the
# tactical Chance pipeline (club_tactical_matchup_service.simulate_match_phases),
# reusing the exact same probability curves as the personal Card Arena engine
# (backend/app/services/match_service.py) — _lerp_chance, _lerp_chance_positive,
# _clamp_rating and _resolve_shot_continuation are copied verbatim from there
# (same math, same config field names) rather than re-derived, so admin-tuned
# match_* config values behave identically in both engines.


def _lerp_chance(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return high - (r - 58) / (99 - 58) * (high - low)


def _lerp_chance_positive(rating: int, low: float, high: float) -> float:
    r = max(58, min(99, rating))
    return low + (r - 58) / (99 - 58) * (high - low)


def _clamp_rating(rating: float) -> int:
    return max(58, min(99, round(rating)))


def _resolve_shot_continuation(
    missed: bool, shot_type: str, config, blocker_rating, keeper_rating,
    keeper: dict | None = None, notes: list | None = None, one_on_one: bool = False,
) -> tuple[str, dict]:
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max))
    if not missed and not blocked:
        saved, save_notes = skill_roll(
            _lerp_chance_positive(keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)),
            # A keeper has one skill, so at most one of these is ever active.
            [_skill(keeper, "reflexes", 1)] + ([_skill(keeper, "one_on_one", 1)] if one_on_one else []),
        )
        if notes is not None:
            notes.extend(save_notes)
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


@dataclass
class MatchResult:
    score_a: int
    score_b: int
    event_log: list[dict] = field(default_factory=list)
    injuries: list[tuple[int, int]] = field(default_factory=list)      # (club_card_id, rounds_remaining)
    red_cards: list[tuple[int, int]] = field(default_factory=list)     # (club_card_id, rounds_remaining=1)


def _skill(actor: dict | None, code: str, sign: int) -> tuple[dict | None, int, str | None]:
    """(effect, sign, player) adjustment for card_skill_effects.skill_roll —
    effect is None unless this exact actor carries this exact skill (only
    player-tournament actors ever carry one; club cards never do)."""
    if not actor:
        return None, sign, None
    return effect_of(actor.get("skill"), code), sign, actor.get("name")


def _keeper_of(lineup: list[dict] | None) -> dict | None:
    """The side's goalkeeper card (category GK) — whose "reflexes" skill
    applies to that side's save rolls. The save's BASE strength still comes
    from the duel defender's rating, exactly as before skills existed."""
    return next((c for c in lineup or [] if c.get("category") == "GK"), None)


def _aerial_pick(lineup: list[dict] | None, position: str) -> dict | None:
    """Deterministic (no RNG) pick of a side's aerial duelist by position —
    the one carrying aerial_master if any, else the first in the lineup."""
    candidates = [c for c in lineup or [] if c.get("position") == position]
    skilled = [c for c in candidates if effect_of(c.get("skill"), "aerial_master")]
    return (skilled or candidates or [None])[0]


def _shot_miss_roll(
    miss: float, scorer: dict, moment: dict, aerial: dict | None,
) -> tuple[bool, list[dict], dict | None]:
    """The scorer's miss roll (sniper), or — on a cross whose header duel
    involves an aerial_master — the same probability split into header duel
    + header (card_skill_effects.aerial_shot_roll). Without an aerial effect
    this is exactly the old single roll."""
    if aerial and moment.get("is_cross"):
        target = scorer if scorer.get("position") in ("ST", "CB") else (aerial.get("attack_target") or scorer)
        defender = aerial.get("defender")
        att_eff = effect_of(target.get("skill"), "aerial_master")
        def_eff = effect_of(defender.get("skill"), "aerial_master") if defender else None
        if att_eff or def_eff:
            alpha = aerial_alpha(target["rating"], defender["rating"] if defender else target["rating"])
            missed, lost, notes = aerial_shot_roll(
                miss, alpha,
                [(def_eff, 1, defender.get("name") if defender else None), (att_eff, -1, target.get("name"))],
                [_skill(scorer, "sniper", -1)],
            )
            info = {"target": target.get("name"), "defender": defender.get("name") if defender else None,
                    "won_by": "defender" if lost else "attacker"}
            return missed, notes, info
    missed, notes = skill_roll(miss, [_skill(scorer, "sniper", -1)])
    return missed, notes, None


def _with_skill_notes(payload: dict, notes: list) -> dict:
    if notes:
        payload["skills"] = notes
    return payload


def _with_talent_notes(payload: dict, notes: list) -> dict:
    if notes:
        payload["talents"] = payload.get("talents", []) + notes
    return payload


def _talented(actor: dict | None, minute: int, own: int, opp: int, role: str, *, one_on_one: bool = False):
    """(actor for this roll, note) — the actor's rating with its «Начало
    пути» dynamic talent when the condition holds now (player tournaments
    only: club/career actors never carry a talent). Its static talents are
    already inside the rating."""
    snap = actor.get("talent") if actor else None
    if not snap:
        return actor, None
    bonus = dynamic_bonus(snap, minute=minute, own=own, opp=opp, role=role, one_on_one=one_on_one)
    if not bonus:
        return actor, None
    return {**actor, "rating": with_bonus(actor["rating"], bonus)}, dynamic_note(snap, bonus)


def _resolve_shot_action(
    attacking_side: str, moment: dict, config, quality_bias: float = 0,
    keeper: dict | None = None, notes: list | None = None, aerial: dict | None = None, keeper_bonus: int = 0,
) -> tuple[dict, str]:
    """Shoots when quality_bias is non-negative (a clear chance), passes
    otherwise — same shoot/pass split the old situation.bias-driven policy
    used, now driven by the tactical pipeline's resolved chance quality
    instead of a scripted ATTACK_SITUATIONS template (spec §6.7)."""
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    defender = moment["actors"]["defender"]
    shot_type = moment["shot_type"]

    notes = list(notes or [])
    action = "shoot" if quality_bias >= 0 else "pass"
    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + quality_bias)
        missed, roll_notes, aerial_info = _shot_miss_roll(
            _lerp_chance(eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max)),
            shooter, moment, aerial,
        )
        notes.extend(roll_notes)
        scorer = shooter
    else:
        eff_passer_rating = _clamp_rating(shooter["rating"] - quality_bias)
        # One roll, two opposing skills: the passer's "playmaker" lowers the
        # fail chance, the duel defender's "interceptor" raises it.
        pass_failed, roll_notes = skill_roll(
            _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max)),
            [_skill(shooter, "playmaker", -1), _skill(defender, "interceptor", 1)],
        )
        notes.extend(roll_notes)
        if pass_failed:
            event = {
                "minute": moment["minute"], "event_type": "pass_failed", "team": attacking_side,
                "payload": _with_skill_notes({"shot_type": shot_type, "action": "pass", "passer": shooter["name"]}, notes),
            }
            return event, "none"
        missed, roll_notes, aerial_info = _shot_miss_roll(
            _lerp_chance(pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max)),
            pass_target, moment, aerial,
        )
        notes.extend(roll_notes)
        scorer = pass_target

    outcome, extra = _resolve_shot_continuation(
        missed, shot_type, config, blocker_rating=defender["rating"], keeper_rating=with_bonus(defender["rating"], keeper_bonus),
        keeper=keeper, notes=notes, one_on_one=bool(moment.get("is_one_on_one")),
    )
    # shooter_id / assist (+_id): who scored / set it up — read by «Карьера
    # игрока» for personal stats (names alone can repeat across teams).
    credit = {"shooter_id": scorer.get("club_card_id")}
    if action == "pass":
        credit.update({"assist": shooter["name"], "assist_id": shooter.get("club_card_id")})
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": _with_skill_notes(
            {"shot_type": shot_type, "action": action, "shooter": scorer["name"], **credit, **extra}, notes,
        ),
    }
    if aerial_info:
        event["payload"]["aerial_duel"] = aerial_info
    return event, (attacking_side if outcome == "goal" else "none")


def _resolve_defense_tackle(
    defending_side: str, moment: dict, config, keeper: dict | None = None,
    foul_mult: float = 1.0, penalty_hook=None, talent_ctx: dict | None = None,
) -> tuple[dict, str, tuple[int, str] | None]:
    """Default policy: defending side always attempts a tackle (same
    rating-driven foul/card rolls as a human picking 'tackle' today).
    Returns (event, scoring_side_or_none, (club_card_id, 'red'|'yellow')_or_none)."""
    defender = moment["actors"]["defender"]
    is_box = moment["is_box"]
    shot_type = moment["shot_type"]

    foul_chance = _lerp_chance(defender["rating"], float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max))
    if foul_mult != 1.0:  # career tackling style (career_tactics_service)
        foul_chance = min(0.95, foul_chance * foul_mult)
    foul = random.random() < foul_chance
    if not foul:
        event = {
            "minute": moment["minute"], "event_type": "tackle_won", "team": defending_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"]},
        }
        return event, "none", None

    is_red = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max))
    card_kind = "red" if is_red else "yellow"

    if is_box and penalty_hook is not None:
        # Career: the penalty is taken by the attacking side's taker vs its keeper.
        attacking_side = "a" if defending_side == "b" else "b"
        event, scored = penalty_hook(attacking_side, moment["minute"], card_kind)
        return event, (attacking_side if scored else "none"), (defender["club_card_id"], card_kind)

    if is_box:
        # «Начало пути»: the keeper's talent on a penalty (Хладнокровие etc.).
        penalty_talents: list = []
        keeper_bonus = 0
        if talent_ctx is not None and keeper and keeper.get("talent"):
            keeper_bonus = dynamic_bonus(
                keeper["talent"], minute=moment["minute"], own=talent_ctx["own"], opp=talent_ctx["opp"],
                role="keeper", penalty=True,
            )
            if keeper_bonus:
                penalty_talents.append(dynamic_note(keeper["talent"], keeper_bonus))
        eff_gk = _clamp_rating(defender["rating"] + keeper_bonus - config.match_penalty_gk_rating_penalty)
        saved, save_notes = skill_roll(
            _lerp_chance_positive(eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max)),
            [_skill(keeper, "reflexes", 1)],
        )
        outcome = "save" if saved else "goal"
        attacking_side = "a" if defending_side == "b" else "b"
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
            "payload": _with_talent_notes(_with_skill_notes(
                {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": True},
                save_notes,
            ), penalty_talents),
        }
        return event, (attacking_side if outcome == "goal" else "none"), (defender["club_card_id"], card_kind)

    event = {
        "minute": moment["minute"], "event_type": "foul_stopped", "team": defending_side,
        "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": False},
    }
    return event, "none", (defender["club_card_id"], card_kind)


def _resolve_breakaway(attacking_side: str, moment: dict, lineup: list[dict], config, notes: list | None = None) -> tuple[dict, str]:
    fwd_candidates = [c for c in lineup if c["category"] == "FWD"]
    fwd_rating = fwd_candidates[0]["rating"] if fwd_candidates else 70
    notes = list(notes or [])
    missed, roll_notes = skill_roll(
        _lerp_chance(fwd_rating, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max)),
        [_skill(fwd_candidates[0] if fwd_candidates else None, "sniper", -1)],
    )
    notes.extend(roll_notes)
    outcome = "shot" if missed else "goal"
    finisher = fwd_candidates[0] if fwd_candidates else None
    credit = {"shooter": finisher["name"], "shooter_id": finisher.get("club_card_id")} if finisher else {}
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": _with_skill_notes({"shot_type": "empty_net", "missed": missed, **credit}, notes),
    }
    return event, (attacking_side if outcome == "goal" else "none")


def simulate_match(
    side_a: "club_tactical_matchup_service.ClubTacticalSide", side_b: "club_tactical_matchup_service.ClubTacticalSide",
    lineup_a: list[dict], lineup_b: list[dict], config,
    club_a_name: str = "Клуб A", club_b_name: str = "Клуб B",
) -> "MatchResult":
    """Replaces the old strength-driven random moment queue: chances now come
    from club_tactical_matchup_service's possession-phase pipeline (spec §6),
    already carrying a resolved quality tier and real picked duelists.
    lineup_a/lineup_b (the plain category-tagged actor dicts
    tournament_simulation_service.resolve_match_lineup already produces) are
    still needed for _resolve_breakaway's unchanged fwd_candidates lookup on
    a clean-breakaway chance."""
    chances = club_tactical_matchup_service.simulate_match_phases(side_a, side_b, config)

    result = MatchResult(score_a=0, score_b=0)
    for chance in chances:
        _resolve_chance(result, chance, side_a, side_b, lineup_a, lineup_b, config, club_a_name, club_b_name)
    fix_goal_descriptions(result.event_log)
    return result


def _resolve_chance(
    result: MatchResult, chance, side_a, side_b, lineup_a: list[dict], lineup_b: list[dict], config,
    club_a_name: str, club_b_name: str, tag_origin: bool = False, controller=None,
) -> None:
    """Resolves one tactical Chance into event(s) and score on `result`.
    `tag_origin` (career matches) also records the chance's origin/zone in
    the event payload — read by the career tactical match analysis."""
    attacking_side = chance.attacking_side
    defending_side = "b" if attacking_side == "a" else "a"
    attacking_playstyle = side_a.playstyle if attacking_side == "a" else side_b.playstyle

    def tag(event: dict) -> None:
        if tag_origin:
            event.setdefault("payload", {})["origin"] = getattr(chance, "origin", "build_up")
            if getattr(chance, "zone", None):
                event["payload"]["zone"] = chance.zone

    if chance.shot_type == "empty_net":
        lineup = lineup_a if attacking_side == "a" else lineup_b
        moment = {"minute": chance.minute}
        event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config, notes=chance.skill_notes)
        tag(event)
        result.event_log.append(event)
        event["description"] = _describe_event(
            event["event_type"], event["team"], club_a_name, club_b_name,
            playstyle=attacking_playstyle, quality=chance.quality,
        )
        if scorer != "none":
            setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
        return

    moment = {
        "minute": chance.minute, "shot_type": chance.shot_type, "is_box": chance.is_box,
        "actors": {"shooter": chance.shooter, "pass_target": chance.pass_target, "defender": chance.defender},
        # A flank attack finished inside the box = a cross (aerial duel).
        "is_cross": getattr(chance, "zone", None) == "wing_attack" and chance.shot_type == "in_box",
        # The top chance tier is the engine's "clean through on goal"
        # (keeper's one_on_one skill applies to that save).
        "is_one_on_one": chance.quality == "VERY_HIGH",
    }
    quality_bias = QUALITY_BIAS[chance.quality]
    defending_keeper = _keeper_of(lineup_b if attacking_side == "a" else lineup_a)
    # «Начало пути» dynamic talents (no RNG draws: a match without talents
    # resolves exactly as before).
    own_att, own_def = getattr(result, f"score_{attacking_side}"), getattr(result, f"score_{defending_side}")
    keeper_bonus = 0
    talent_notes: dict[str, dict] = {}
    if any(a and a.get("talent") for a in (chance.shooter, chance.pass_target, chance.defender, defending_keeper)):
        one_on_one = moment["is_one_on_one"]
        role = "shooter" if quality_bias >= 0 else "passer"
        shooter, n1 = _talented(chance.shooter, chance.minute, own_att, own_def, role, one_on_one=one_on_one and role == "shooter")
        target, n2 = _talented(chance.pass_target, chance.minute, own_att, own_def, "shooter", one_on_one=one_on_one)
        defender, n3 = _talented(chance.defender, chance.minute, own_def, own_att, "defender")
        moment["actors"] = {"shooter": shooter, "pass_target": target, "defender": defender}
        talent_notes = {k: n for k, n in (("shooter", n1), ("pass_target", n2), ("defender", n3)) if n}
        keeper_snap = defending_keeper.get("talent") if defending_keeper else None
        keeper_bonus = dynamic_bonus(
            keeper_snap, minute=chance.minute, own=own_def, opp=own_att, role="keeper", one_on_one=one_on_one,
        )
        if keeper_bonus:
            talent_notes["keeper"] = dynamic_note(keeper_snap, keeper_bonus)
    aerial = None
    if moment["is_cross"]:
        aerial = {
            "attack_target": _aerial_pick(lineup_a if attacking_side == "a" else lineup_b, "ST"),
            "defender": _aerial_pick(lineup_b if attacking_side == "a" else lineup_a, "CB"),
        }
    event, scorer = _resolve_shot_action(
        attacking_side, moment, config, quality_bias, keeper=defending_keeper, notes=chance.skill_notes,
        **({"aerial": aerial} if aerial else {}), **({"keeper_bonus": keeper_bonus} if keeper_bonus else {}),
    )
    if talent_notes:
        # A note only for an actor whose roll actually happened: the passer's
        # receiver after a completed pass, the defender once the shot was on
        # target (block / keeper base), the keeper when there was a save roll.
        reached = event["event_type"] in ("blocked", "save", "goal")
        used = ["shooter"]
        if event["payload"].get("action") == "pass" and event["event_type"] != "pass_failed":
            used.append("pass_target")
        if reached:
            used.append("defender")
        if event["event_type"] in ("save", "goal"):
            used.append("keeper")
        _with_talent_notes(event["payload"], [talent_notes[k] for k in used if k in talent_notes])
    tag(event)
    result.event_log.append(event)
    event["description"] = _describe_event(
        event["event_type"], event["team"], club_a_name, club_b_name,
        playstyle=attacking_playstyle, quality=chance.quality,
    )
    if scorer != "none":
        setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)

    # Defense is attempted only when a blocked/saved shot has a further
    # (config.club_tactical_tackle_attempt_chance) chance the defender
    # committed a foul in the process — mirrors match_service's "tackle
    # can stop an attack before it becomes a shot" flow for the box/foul
    # path; everywhere else, shoot/pass resolves directly against the
    # defender's rating via _resolve_shot_continuation's blocker/keeper
    # roll, same as the personal engine.
    tackle_chance = float(config.club_tactical_tackle_attempt_chance)
    if controller is not None:
        tackle_chance = min(0.95, tackle_chance * controller.tackle_attempt_mult(defending_side))
    if event["event_type"] in ("blocked", "save") and random.random() < tackle_chance:
        if controller is not None:
            defense_event, defense_scorer, card = _resolve_defense_tackle(
                defending_side, moment, config, keeper=defending_keeper,
                foul_mult=controller.foul_mult(defending_side), penalty_hook=controller.penalty,
            )
        else:
            defense_event, defense_scorer, card = _resolve_defense_tackle(
                defending_side, moment, config, keeper=defending_keeper,
                talent_ctx={"own": own_def, "opp": own_att} if defending_keeper and defending_keeper.get("talent") else None,
            )
        result.event_log.append(defense_event)
        if "description" not in defense_event:
            defense_event["description"] = _describe_event(defense_event["event_type"], defense_event["team"], club_a_name, club_b_name)
        if defense_scorer != "none":
            setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
        if card is not None:
            club_card_id, card_kind = card
            if card_kind == "red":
                result.red_cards.append((club_card_id, 1))
                if random.random() < float(config.club_tactical_injury_chance):
                    result.injuries.append((club_card_id, random.randint(1, 3)))


class MatchController:
    """Hook for simulate_match_controlled: called before every phase with
    the minute and the live score; returns the sides/lineups to play that
    phase with plus any events to log first (tactic changes, substitutions).
    See career_tactics_service.CareerMatchController."""

    def before_phase(self, minute: int, score_a: int, score_b: int) -> tuple:  # pragma: no cover - interface
        raise NotImplementedError


def simulate_match_controlled(
    controller: MatchController, config, club_a_name: str = "Клуб A", club_b_name: str = "Клуб B",
    tracker: dict | None = None,
) -> MatchResult:
    """Phase-by-phase variant of simulate_match for «Карьера тренера»: each
    chance is resolved as soon as it happens, so the controller sees the real
    score and minute before the next phase (conditional instructions,
    substitutions, in-match fatigue). Same phase count, minute draw and chance
    ceiling as simulate_match_phases; `tracker` collects the per-side phase
    statistics the post-match analysis reports."""
    num_phases = random.randint(config.club_tactical_phases_per_match_min, config.club_tactical_phases_per_match_max)
    minutes = sorted(random.sample(range(1, 90), min(num_phases, 89)))
    max_chances = config.club_tactical_promoted_chance_target_max

    result = MatchResult(score_a=0, score_b=0)
    chances = 0
    for minute in minutes:
        side_a, side_b, lineup_a, lineup_b, events = controller.before_phase(minute, result.score_a, result.score_b)
        result.event_log.extend(events)
        if chances >= max_chances:
            continue
        chance = club_tactical_matchup_service.simulate_phase(minute, side_a, side_b, config, tracker)
        if chance is None:
            continue
        chances += 1
        before = len(result.event_log)
        _resolve_chance(
            result, chance, side_a, side_b, lineup_a, lineup_b, config, club_a_name, club_b_name, tag_origin=True,
            controller=controller if hasattr(controller, "penalty") else None,
        )
        if hasattr(controller, "set_pieces"):
            for event, scorer in controller.set_pieces(result.event_log[before:], minute):
                result.event_log.append(event)
                if scorer:
                    setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
    if hasattr(controller, "finish"):
        controller.finish()
    fix_goal_descriptions(result.event_log)
    return result
