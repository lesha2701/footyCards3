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


def _describe_event(event_type: str, team: str, club_a_name: str, club_b_name: str) -> str:
    club = club_a_name if team == "a" else club_b_name
    template = random.choice(_EVENT_DESCRIPTIONS[event_type])
    return template.format(club=club)


from app.services import club_tactical_matchup_service

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


def _resolve_shot_continuation(missed: bool, shot_type: str, config, blocker_rating, keeper_rating) -> tuple[str, dict]:
    blocked = False
    saved = False
    if not missed and shot_type == "long_range" and blocker_rating is not None:
        blocked = random.random() < _lerp_chance(blocker_rating, float(config.match_defender_block_chance_min), float(config.match_defender_block_chance_max))
    if not missed and not blocked:
        saved = random.random() < _lerp_chance_positive(keeper_rating, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
    outcome = "shot" if missed else "blocked" if blocked else "save" if saved else "goal"
    return outcome, {"missed": missed, "blocked": blocked}


@dataclass
class MatchResult:
    score_a: int
    score_b: int
    event_log: list[dict] = field(default_factory=list)
    injuries: list[tuple[int, int]] = field(default_factory=list)      # (club_card_id, rounds_remaining)
    red_cards: list[tuple[int, int]] = field(default_factory=list)     # (club_card_id, rounds_remaining=1)


def _resolve_shot_action(attacking_side: str, moment: dict, config, quality_bias: float = 0) -> tuple[dict, str]:
    """Shoots when quality_bias is non-negative (a clear chance), passes
    otherwise — same shoot/pass split the old situation.bias-driven policy
    used, now driven by the tactical pipeline's resolved chance quality
    instead of a scripted ATTACK_SITUATIONS template (spec §6.7)."""
    shooter = moment["actors"]["shooter"]
    pass_target = moment["actors"]["pass_target"]
    defender = moment["actors"]["defender"]
    shot_type = moment["shot_type"]

    action = "shoot" if quality_bias >= 0 else "pass"
    if action == "shoot":
        eff_rating = _clamp_rating(shooter["rating"] + quality_bias)
        missed = random.random() < _lerp_chance(eff_rating, float(config.match_attack_shoot_miss_chance_min), float(config.match_attack_shoot_miss_chance_max))
        scorer = shooter
    else:
        eff_passer_rating = _clamp_rating(shooter["rating"] - quality_bias)
        pass_failed = random.random() < _lerp_chance(eff_passer_rating, float(config.match_pass_fail_chance_min), float(config.match_pass_fail_chance_max))
        if pass_failed:
            event = {
                "minute": moment["minute"], "event_type": "pass_failed", "team": attacking_side,
                "payload": {"shot_type": shot_type, "action": "pass", "passer": shooter["name"]},
            }
            return event, "none"
        missed = random.random() < _lerp_chance(pass_target["rating"], float(config.match_receiver_shot_miss_chance_min), float(config.match_receiver_shot_miss_chance_max))
        scorer = pass_target

    outcome, extra = _resolve_shot_continuation(missed, shot_type, config, blocker_rating=defender["rating"], keeper_rating=defender["rating"])
    event = {
        "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
        "payload": {"shot_type": shot_type, "action": action, "shooter": scorer["name"], **extra},
    }
    return event, (attacking_side if outcome == "goal" else "none")


def _resolve_defense_tackle(defending_side: str, moment: dict, config) -> tuple[dict, str, tuple[int, str] | None]:
    """Default policy: defending side always attempts a tackle (same
    rating-driven foul/card rolls as a human picking 'tackle' today).
    Returns (event, scoring_side_or_none, (club_card_id, 'red'|'yellow')_or_none)."""
    defender = moment["actors"]["defender"]
    is_box = moment["is_box"]
    shot_type = moment["shot_type"]

    foul = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_foul_chance_min), float(config.match_tackle_foul_chance_max))
    if not foul:
        event = {
            "minute": moment["minute"], "event_type": "tackle_won", "team": defending_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"]},
        }
        return event, "none", None

    is_red = random.random() < _lerp_chance(defender["rating"], float(config.match_tackle_red_chance_min), float(config.match_tackle_red_chance_max))
    card_kind = "red" if is_red else "yellow"

    if is_box:
        eff_gk = _clamp_rating(defender["rating"] - config.match_penalty_gk_rating_penalty)
        saved = random.random() < _lerp_chance_positive(eff_gk, float(config.match_keeper_save_chance_min), float(config.match_keeper_save_chance_max))
        outcome = "save" if saved else "goal"
        attacking_side = "a" if defending_side == "b" else "b"
        event = {
            "minute": moment["minute"], "event_type": outcome, "team": attacking_side,
            "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": True},
        }
        return event, (attacking_side if outcome == "goal" else "none"), (defender["club_card_id"], card_kind)

    event = {
        "minute": moment["minute"], "event_type": "foul_stopped", "team": defending_side,
        "payload": {"shot_type": shot_type, "action": "tackle", "defender": defender["name"], "card": card_kind, "is_penalty": False},
    }
    return event, "none", (defender["club_card_id"], card_kind)


def _resolve_breakaway(attacking_side: str, moment: dict, lineup: list[dict], config) -> tuple[dict, str]:
    fwd_candidates = [c for c in lineup if c["category"] == "FWD"]
    fwd_rating = fwd_candidates[0]["rating"] if fwd_candidates else 70
    missed = random.random() < _lerp_chance(fwd_rating, float(config.match_shot_miss_chance_min), float(config.match_shot_miss_chance_max))
    outcome = "shot" if missed else "goal"
    event = {"minute": moment["minute"], "event_type": outcome, "team": attacking_side, "payload": {"shot_type": "empty_net", "missed": missed}}
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
        attacking_side = chance.attacking_side
        defending_side = "b" if attacking_side == "a" else "a"

        if chance.shot_type == "empty_net":
            lineup = lineup_a if attacking_side == "a" else lineup_b
            moment = {"minute": chance.minute}
            event, scorer = _resolve_breakaway(attacking_side, moment, lineup, config)
            result.event_log.append(event)
            event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
            if scorer != "none":
                setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)
            continue

        moment = {
            "minute": chance.minute, "shot_type": chance.shot_type, "is_box": chance.is_box,
            "actors": {"shooter": chance.shooter, "pass_target": chance.pass_target, "defender": chance.defender},
        }
        quality_bias = QUALITY_BIAS[chance.quality]
        event, scorer = _resolve_shot_action(attacking_side, moment, config, quality_bias)
        result.event_log.append(event)
        event["description"] = _describe_event(event["event_type"], event["team"], club_a_name, club_b_name)
        if scorer != "none":
            setattr(result, f"score_{scorer}", getattr(result, f"score_{scorer}") + 1)

        # Defense is attempted only when a blocked/saved shot has a further
        # (15%) chance the defender committed a foul in the process — mirrors
        # match_service's "tackle can stop an attack before it becomes a shot"
        # flow for the box/foul path; everywhere else, shoot/pass resolves
        # directly against the defender's rating via _resolve_shot_continuation's
        # blocker/keeper roll, same as the personal engine.
        if event["event_type"] in ("blocked", "save") and random.random() < 0.15:
            defense_event, defense_scorer, card = _resolve_defense_tackle(defending_side, moment, config)
            result.event_log.append(defense_event)
            defense_event["description"] = _describe_event(defense_event["event_type"], defense_event["team"], club_a_name, club_b_name)
            if defense_scorer != "none":
                setattr(result, f"score_{defense_scorer}", getattr(result, f"score_{defense_scorer}") + 1)
            if card is not None:
                club_card_id, card_kind = card
                if card_kind == "red":
                    result.red_cards.append((club_card_id, 1))
                    if random.random() < 0.3:
                        result.injuries.append((club_card_id, random.randint(1, 3)))

    return result
