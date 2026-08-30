# Club Tactical Match Engine — Design

> **For agentic workers:** this spec is the authority for the implementation
> plan(s) that follow. Where the plan and this spec disagree, this spec wins.

## 1. Overview and goals

Today a club tournament match is decided almost entirely by one number per
side: `team_strength` (`lineup_service.calculate_base_strength`), which sets
`P(attacks) = strength_A / (strength_A + strength_B)`; everything after that
— who shoots, who defends, miss/save/block — is resolved by individual card
ratings and RNG, uninfluenced by any tactical choice. There is exactly one
fixed formation (4-3-3), no mentality/style setting for clubs, and no way to
scout an upcoming opponent.

**Goal:** rebuild the club match engine so that formation, mentality,
playstyle, and the opponent's actual strengths/weaknesses meaningfully shape
the result — without turning tactics into flat bonuses that make weak cards
strong, and without letting a correctly-guessed counter-tactic let a much
weaker squad beat a much stronger one consistently. Card ratings stay the
primary long-run driver; tactics become a real, learnable skill layered on
top.

**Explicitly out of scope:** the personal (non-club) Card Arena system
(`match_service.py`, `lineup_service.py`'s existing single-formation
personal lineup, `Lineup.tactic`'s attacking/balanced/defensive) is
untouched. It is a fully independent code path today (its shot/pass/save
helpers are a verbatim, non-shared copy of `tournament_match_engine.py`'s —
see §2) and stays that way after this work.

**Phases** (see §15 for the full breakdown): this spec covers all three,
but only Phase 1 is planned/implemented first.

- **Phase 1 — core engine.** Formations, mentality/playstyle, the new
  possession-phase pipeline, data model, migration, unit tests. Every
  tournament match (new and already-in-progress, per the explicit decision
  in §13) is decided by the new engine as soon as this phase ships.
- **Phase 2 — scouting & UX.** Next-opponent endpoint, Attack/Midfield/
  Defence scouting numbers, Tactical Fit surfaced in the squad UI, pre-match
  briefing block.
- **Phase 3 — balance.** Statistical simulation script, tuning pass on the
  Phase 1 default coefficients against the scenarios in §14.

---

## 2. Module boundaries

`lineup_service.py` currently defines `FormationSlot`, `FORMATION_SLOTS`,
`SLOTS_BY_CODE`, `CATEGORY_POSITIONS`, and `calculate_base_strength` **once**,
and both the personal Card Arena path (`match_service.py`, via
`get_active_lineup`/`set_lineup`/`TACTIC_MULTIPLIERS`/`split_strength`) and
every club path (`club_squad_service.py`, `tournament_simulation_service.py`,
`tournament_queue_service.py`, `app/seed.py`) import directly from it. Editing
these symbols in place to support multiple formations would silently change
personal-match behavior too. Confirmed independently: `tournament_match_engine.py`'s
shot/pass/save helpers (`_lerp_chance`, `_resolve_shot_continuation`, etc.)
are **already** a verbatim, independently-maintained copy of
`match_service.py`'s own versions (see the file's own top-of-file comment) —
so restructuring `tournament_match_engine.py` freely, including deleting its
now-superseded `generate_moment_queue`/`simulate_match` entry points, carries
zero risk to `match_service.py`.

**Rule:** nothing in this feature edits `FormationSlot`, `FORMATION_SLOTS`,
`SLOTS_BY_CODE`, `TACTIC_MULTIPLIERS`, `split_strength`, or `match_service.py`.
`CATEGORY_POSITIONS` and `calculate_base_strength` (both formation-agnostic —
the former is just a category→position-set map, the latter takes an
already-resolved list of `(card, slot)` pairs) are imported and reused as-is
for computing the UI-facing `team_strength` number (§5).

New club-only modules (all under `backend/app/services/`):

| Module | Owns |
|---|---|
| `club_formation_service.py` | Formation registry (§4), slot lookups, `CATEGORY_POSITIONS`-compatible per-formation category sets |
| `club_tactical_profile_service.py` | `TeamTacticalProfile` computation (§5), position→zone weight table, Tactical Fit (§9) |
| `club_tactical_matchup_service.py` | Initiative, progression, duel chain, chance quality (§6–8) — everything between "who has the ball" and "who's taking the shot" |
| `club_scouting_service.py` | Next-opponent lookup + Attack/Midfield/Defence rollup (§10) — Phase 2 |

`tournament_match_engine.py` is kept and refactored (§6.7): its shot/pass/
save/tackle/foul/card resolution stays the final stage of every chance, just
invoked with externally-chosen actors and a quality-derived bias instead of
its own moment-queue. `generate_moment_queue` and the old `simulate_match`
are deleted once `club_tactical_matchup_service.py` replaces their caller —
there is no dual-engine flag (per §13, this ships for everyone at once, so a
legacy path would be dead code from day one).

---

## 3. Data model

`ClubLineup` (`app/models/club_lineup.py`) gains three columns, following the
exact precedent of personal `Lineup.tactic` (`app/models/lineup.py:17`) —
plain `String`, validated against a Python-side set/enum in the service
layer, no native Postgres enum, no `ALTER TYPE` migration dance:

```python
formation: Mapped[str] = mapped_column(String(16), default="4-3-3", nullable=False, server_default="4-3-3")
mentality: Mapped[str] = mapped_column(String(16), default="BALANCED", nullable=False, server_default="BALANCED")
playstyle: Mapped[str] = mapped_column(String(16), default="CENTRAL_PLAY", nullable=False, server_default="CENTRAL_PLAY")
```

`server_default` makes the migration a plain `ADD COLUMN` — every existing
`club_lineups` row (all ~40+ production clubs, all currently an unlabeled
4-3-3) gets these defaults automatically, no backfill UPDATE needed. This is
also why the defaults are exactly what they are: 4-3-3 is the formation
every current lineup already, structurally, is; BALANCED/CENTRAL_PLAY are
the two most-neutral options on each axis, so no club is silently opted into
an extreme tactic they never chose.

New endpoint `PUT /clubs/me/tactics` (mirrors `PUT /clubs/me/lineup`'s
captain/assistant-only gating): body `{formation, mentality, playstyle}`,
validated against §4/§7/§8's registries, `ConflictError` on an unknown value
— same pattern as `lineup_service.set_tactic`.

**Formation changes and existing slots:** changing formation while slots are
already filled needs a reconciliation rule. Simplest, safest: changing
`ClubLineup.formation` clears every `ClubLineupCard` whose `slot_code` isn't
valid in the new formation's slot list (e.g. going from 4-3-3 to 4-4-2 drops
the `FWD3`/`MID3` assignment since those codes don't exist in 4-4-2's slot
set — see §4) and leaves the freed cards on the bench; slots that share a
code across both formations (e.g. `GK`, `DEF1`) keep their card. The squad
screen must then show the lineup as incomplete until the captain fills the
newly-empty slots — same "must be 11/11 to apply to a tournament" gate
already enforced by `tournament_queue_service.py`.

---

## 4. Formation registry

`club_formation_service.py`:

```python
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
```

`FormationSlot` itself is the exact dataclass already defined in
`lineup_service.py` (imported, not redefined — its shape, not its formation
list, is what's reusable). `CLUB_SLOTS_BY_CODE[formation]` and
`CLUB_CATEGORY_POSITIONS` (formation-independent, so a single shared dict
suffices) are derived the same way `lineup_service.py` derives its own.

**Extensibility:** adding a 5th formation later is a new dict entry, nothing
else — no code path branches on formation name, everything downstream (zone
weights, duel eligibility) reads the slot list generically.

**How formation affects zones — no per-formation bonus table.** A
formation's tactical effect is 100% emergent from which positions it puts on
the pitch, run through the position→zone weight table in §5. 3-5-2's five
midfield slots naturally produce a higher `midfield_control` (more
contributors averaged in) and a deeper pool of eligible duelists in central
possession phases (more players who can be picked as the Stage-1/Stage-2
actor, so a bad individual matchup is less likely to be forced) than 4-3-3's
three midfield slots — without a single `"3-5-2": +10` constant anywhere.
5-3-2 gets the same effect in reverse for defensive presence and against
wing attack (only one out-and-out wide slot's worth of contribution per
flank, LB/RB, versus 4-3-3/4-4-2's fuller wide coverage).

---

## 5. TeamTacticalProfile

```python
@dataclass
class TeamTacticalProfile:
    central_attack: float
    wing_attack: float
    midfield_control: float
    central_defence: float
    wing_defence: float
    goalkeeping: float
    team_strength: int  # = calculate_base_strength(cards_with_slots); UI/back-compat only, unused below §6
```

Each zone is a **weighted average**, not a sum, over the 11 starters —
average keeps every zone on the same 58–99-ish scale as an individual card
rating, which matters both for the zone-ratio math in §6 and for the
Attack/Midfield/Defence numbers shown to a scouting opponent in §10 (they
need to read like a rating, not grow with squad size):

```
zone(team) = Σ(rating_i × weight[position_i][zone]) / Σ(weight[position_i][zone])
             over the 11 starters where weight[position_i][zone] > 0
```

Position→zone weight table (defaults; tuned in Phase 3, §15):

| Position | central_attack | wing_attack | midfield_control | central_defence | wing_defence | goalkeeping |
|---|---|---|---|---|---|---|
| GK | — | — | — | 0.15 | 0.15 | 1.00 |
| CB | — | — | 0.10 | 1.00 | 0.25 | — |
| LB / RB | — | 0.55 | 0.10 | 0.20 | 1.00 | — |
| CDM | 0.05 | — | 0.85 | 0.45 | 0.15 | — |
| CM | 0.20 | 0.05 | 1.00 | 0.10 | — | — |
| CAM | 0.60 | 0.10 | 0.55 | — | — | — |
| LM / RM | 0.10 | 0.85 | 0.35 | — | 0.20 | — |
| LW / RW | 0.65 | 1.00 | — | — | 0.05 | — |
| ST | 1.00 | 0.10 | — | — | — | — |

Chemistry (same-club/-country) and rarity bonuses (already in
`calculate_base_strength`) affect `team_strength` only — they're whole-squad
properties with no natural per-zone home, and keeping them out of the zone
formula keeps "weighted average of real position contributions" honest.

**Substitution / suspension:** `resolve_match_lineup`'s existing
bench-substitution logic (§ current `tournament_simulation_service.py`) is
kept as-is and runs *before* profile computation — a suspended starter is
already swapped for a bench card (or the slot goes empty) by the time zones
are computed, so a forced substitution naturally lowers whichever zone(s)
that slot fed, proportional to the real rating gap between starter and
sub — no separate "substitution penalty" multiplier is needed once zones
exist (this replaces the old flat `SUBSTITUTION_PENALTY = 0.5` on
`team_strength`, which no longer drives anything gameplay-relevant post-§6).
Form (`form_multiplier`, last N results) is likewise recomputed to apply to
`team_strength` for UI only; it does not multiply the zones (form as a
zone-level effect is left for Phase 3 to consider — see §15's non-goals — a
whole-team confidence swing has no single natural zone home either).

---

## 6. The match pipeline

Replaces the whole "18–26 independent moments" model with a sequence of
**possession phases**. A phase is the new unit of simulation; each one
either ends quietly (stall, or a low-event turnover) or produces a real
chance that reaches the existing shot/save engine (§6.7). Roughly 40–70
phases run per match internally; only the ones that reach a real chance (or
a card/foul) are written to `event_log` — expected to land in the same
15–25-events-per-match range players see today, per the explicit "internal
noise reduction, unchanged log size" requirement.

### 6.1 Initiative — who has this phase

Not `team_strength`. Each phase opens with a midfield battle:

```
midfield_score(team) = midfield_control(team) × initiative_mult(team.mentality)
P(A wins this phase's initiative) = midfield_score_A / (midfield_score_A + midfield_score_B)
```

`initiative_mult` (§7 table): ATTACKING/POSSESSION actively contest and hold
the ball (mult > 1); PARK_THE_BUS/DEFENSIVE deliberately cede it in exchange
for defensive solidity (mult < 1) — conceding initiative is the bus's whole
point, not a side-effect. `midfield_control` itself already reflects
formation (§4's emergent effect) and the real cards in midfield slots — no
separate formation multiplier is layered on top here.

### 6.2 Progression — playstyle picks the zone and the risk profile

The team that won initiative attempts to progress into a scoring
opportunity. Playstyle (§8) decides which zone the attempt targets:
`wing_attack` (WING_PLAY), `central_attack` (CENTRAL_PLAY), a
possession-gated mix of both (POSSESSION — see §8), or a reduced-volume mix
with lower commitment (COUNTER_ATTACK, which mostly waits for §6.5 instead
of building its own positional attacks). HIGH_PRESS is primarily a
defensive-phase modifier (§8) and behaves like BALANCED when in possession.

### 6.3 Duel chain (Stage 1 → Stage 2)

**§5's zone values are for team-level decisions only** (§6.1's initiative,
§6.2's progression targeting, §9's Tactical Fit, §10's scouting rollup).
Stage 1/Stage 2 duels themselves are resolved from the **individually
picked duelists' own ratings** — this is what makes "LW 94 vs RB 72" a real,
named confrontation instead of a whole-team average deciding it, matching
the brainstorm's explicit worked examples.

**Picking a duelist:** weighted-random among the slot-holders eligible for
that zone (§5's weight table doubles as the selection probability — a
zone's `weight > 0` positions are the eligible pool, higher weight = picked
more often; this is the same "weighted-pick, not uniform-random" idea used
today by `tournament_match_engine._pick_actor`).

**Resolving the duel:** once picked, each duelist contributes their **raw
card rating**, adjusted by a position-fit multiplier for that specific zone
(1.0 for that zone's primary position, e.g. ST for `central_attack`; 0.9 for
a natural secondary contributor, e.g. LW for `central_attack`; 0.85 for a
present-but-weakly-relevant pick) — the same 1.0/0.9/0.75-shaped fit concept
`calculate_base_strength` already uses, reapplied per-zone instead of
per-formation-slot:

```
effective_rating(player, zone) = player.rating × position_fit(player.position, zone)
zone_ratio = effective_rating(attacker_duelist, zone) / (effective_rating(attacker_duelist, zone) + effective_rating(defender_duelist, zone))
```

**Stage 1 — progression duel.** The attacking zone's primary duelist versus
the defending zone's primary duelist, `zone_ratio` per the formula above.
Outcome is a three-way roll banded by `zone_ratio` (defaults; Phase 3-tuned):

| `zone_ratio` | breakdown → §6.5 | stalls (phase ends) | advances → Stage 2 |
|---|---|---|---|
| > 0.75 | 10% | 25% | 65% |
| 0.60–0.75 | 18% | 35% | 47% |
| 0.40–0.60 | 30% | 45% | 25% |
| < 0.40 | 45% | 35% | 20% |

**Stage 2 — creation duel** (only if Stage 1 advanced). A secondary
combatant (e.g. an overlapping fullback or a central creator, per playstyle)
versus a covering secondary defender; same `zone_ratio` mechanic, combined
with Stage 1's margin to pick a **chance quality** tier:

| combined advantage | LOW | NORMAL | HIGH | VERY_HIGH |
|---|---|---|---|---|
| strong (>0.75) | 5% | 20% | 50% | 25% |
| moderate (0.60–0.75) | 15% | 35% | 38% | 12% |
| even (0.40–0.60) | 25% | 50% | 22% | 3% |
| weak (<0.40) | 55% | 35% | 9% | 1% |

This is the direct fix for "quality shouldn't be an independent roll on top
of a real advantage" — the distribution itself shifts with the margin, RNG
only decides where inside that shifted distribution the match lands.

### 6.4 Effective defensive pool — how mentality changes structure, not ratings

Before the counter-attack chain (§6.5) can pick a defensive duelist, it
needs a pool to pick from. This is the mechanism that satisfies "mentality
must not multiply a defender's rating" directly: a *transition* moment
doesn't draw its defensive duelist from the team's full back line — it
draws from a **mentality-sized random subset** of that line's real
contributors:

```
sample_fraction(mentality) = {PARK_THE_BUS: 1.00, DEFENSIVE: 0.90, BALANCED: 0.75, ATTACKING: 0.55}
# HIGH_PRESS multiplies whatever the mentality gives by an additional ×0.85
# (pressing high commits players forward independently of overall mentality)
pool_size = max(1, round(sample_fraction(mentality) × count(defensive-zone contributors)))
```

The pool is re-rolled fresh each transition moment, drawn from the team's
*actual* rated defenders — a CB rated 65 is exactly 65 whenever they're
picked, never adjusted. PARK_THE_BUS keeps the full (however strong or
weak) back line eligible every single time; ATTACKING/HIGH_PRESS shrink the
pool, so there's a real chance the specific defender who ends up in the §6.5
duel is a makeshift/thin cover rather than the team's best cover — which is
what produces "more space, more dangerous counters conceded" structurally,
with zero rating inflation or deflation anywhere in this formula.

### 6.5 Counter-attack chain (triggered on a Stage-1 breakdown)

The team that *won* the Stage-1 duel (the defender, call them Y) gets an
immediate transition check, resolved with **the same picked-duelist
mechanism as §6.3** — a named individual confrontation, not an aggregate:

```
Y picks a counter duelist (weighted from central_attack/wing_attack — ST/LW/RW-heavy)
X picks a defensive duelist from §6.4's shrunk pool (not the full back line)

effective_rating(Y's duelist) = duelist.rating × position_fit(...)
    × transition_bonus(Y.playstyle)   # COUNTER_ATTACK/HIGH_PRESS(just won it) higher; POSSESSION lower
    × first_pass_quality_factor(Y)    # Y's CDM/CM rating on the outlet pass — a weak first pass caps this

effective_rating(X's duelist) = duelist.rating × position_fit(...)   # unmodified — pool size already
                                                                       # carried mentality's whole effect

zone_ratio = effective_rating(Y's duelist) / (effective_rating(Y's duelist) + effective_rating(X's duelist))
```

`zone_ratio` feeds the *same* advance/breakdown/quality bands as §6.3 —
this is literally a Stage-1 duel, just with Y and X's roles and eligible
pools swapped by the turnover.

**Worked check against the spec's explicit example:** club X (CB 64/67, LB
65, RB 66) on PARK_THE_BUS against club Y (ST 95, LW 93, RW 94) on
ATTACKING. X's low `initiative_mult` (§6.1, §7) means Y wins the vast
majority of phases. In each of those phases, whichever of Y's 93–95-rated
forwards gets picked as the Stage-1 duelist faces whichever of X's real
64–67-rated defenders gets picked — X's PARK_THE_BUS keeps the *full* back
line eligible (§6.4's `sample_fraction = 1.00`), but every member of that
line is still genuinely 64–67, never boosted. `zone_ratio` is overwhelmingly
in Y's favor almost every time, so the bulk of Y's many phases land in the
"strong advantage" quality band (mostly HIGH/VERY_HIGH) regardless of which
specific weak defender got picked. X's weak defenders keep facing, and keep
losing to, Y's elite attackers — bus reduces how much *worse* X could make
it (by not also dragging defenders forward and shrinking their own pool
further) and, via §6.4, denies Y's *own* counter-threat the thin-pool
advantage X would hand it under ATTACKING — but bus never turns a 65-rated
CB into a functional stopper.

### 6.6 Player selection (Stage 1 / Stage 2)

"Weighted-pick" (used throughout §6.3–6.5) means: among the slot-holders
eligible for a zone (§5's `weight > 0` positions for that zone, or §6.4's
shrunk pool for a transition defender), pick one at random with probability
proportional to their position's weight for that zone — the same idea
`tournament_match_engine._pick_actor` already uses for shot moments today,
just zone-scoped instead of category-scoped. A WING_PLAY duel preferentially
puts LW/RW/LM/RM/LB/RB forward as the attacking duelist; a CENTRAL_PLAY duel
preferentially puts ST/CAM/CM. This is what makes each duel a concrete,
named individual matchup rather than a whole-team average deciding it.

### 6.7 Handoff to the existing engine

Everything above produces exactly what `tournament_match_engine.py`'s
resolution functions already need — a shooter, a pass target, a defender,
and a `shot_type` — plus one new input: a `quality_bias` derived from the
chance-quality tier (e.g. `{LOW: -6, NORMAL: 0, HIGH: +5, VERY_HIGH: +10}`,
in the same units `situation.bias` already nudges effective rating by).
`_resolve_shot_action`/`_resolve_defense_tackle`/`_resolve_breakaway`/
`_resolve_shot_continuation` are refactored to accept this bias as a
parameter (defaulting to 0, so their unit tests keep working unmodified)
instead of only reading `situation.bias` from a pre-built moment dict.
Everything past this point — miss/pass-fail/block/save curves, fouls,
cards, injuries, event descriptions — is **unchanged**.

---

## 7. Mentality effects (all structural — see §6.1, §6.4)

| Mentality | `initiative_mult` (§6.1) | `sample_fraction` (§6.4) |
|---|---|---|
| PARK_THE_BUS | 0.55 | 1.00 |
| DEFENSIVE | 0.80 | 0.90 |
| BALANCED | 1.00 | 0.75 |
| ATTACKING | 1.25 | 0.55 |

No table entry multiplies a card's rating. `initiative_mult` changes how
often a team gets the ball at all (§6.1); `sample_fraction` changes how much
of its real back line is actually eligible to contest a transition moment
(§6.4) — together these are the *entire* structural effect of mentality.
There is no separate "exposure" multiplier layered on top of a mentality
choice — §6.5's counter-attack duel already inherits mentality's full effect
through whichever (real, unmodified) defender §6.4's shrunk pool hands it;
adding a second multiplier for the same cause would double-count it.

---

## 8. Playstyle effects

| Playstyle | Progression zone target (§6.2) | Transition bonus (§6.5) | Notes |
|---|---|---|---|
| WING_PLAY | wing_attack ~65%, central ~25%, rest low-event | 1.0 | Stage-2 secondary duelist is the overlapping LB/RB |
| CENTRAL_PLAY | central_attack ~65%, wing ~25% | 1.0 | Stage-2 secondary duelist is CAM/CM |
| POSSESSION | buildup gate on `midfield_control` first (weak midfield → higher breakdown chance *before* even reaching §6.3), then ~40/40 central/wing | 0.7 | Punishes a weak midfield hard; rewards a strong one by extending phases (more Stage-2 attempts per won initiative) |
| HIGH_PRESS | ~BALANCED zone mix when in possession | 1.3 (when *this* team just won the ball) | Its real effect is on `sample_fraction` (§6.4, ×0.85 stacking) and on how often it forces an opponent Stage-1 breakdown, not on its own attacking shape |
| COUNTER_ATTACK | ~60% of won-initiative phases attempt progression at all (rest recycle safely, low-event); mostly relies on §6.5 | 1.5 | Low positional-attack volume by design; its real power is the transition chain |

**Soft counters (not a hard matrix):** effectiveness differences between
styles are entirely explained by §6.4/§6.5's real mechanisms responding to
the opponent's *actual current* mentality/playstyle choice — COUNTER_ATTACK
is only more dangerous against ATTACKING/HIGH_PRESS because those mentalities
concretely shrink §6.4's defensive pool, which lowers the effective rating
§6.5's `zone_ratio` compares against. There is no separate
`style_vs_style[COUNTER_ATTACK][ATTACKING] = 1.3` lookup table layered on
top — the interaction is the same formula, just evaluated against whatever
the opponent picked. This satisfies "results always weighted by real
ratings" (§13 of the brainstorm) by construction: a COUNTER_ATTACK team with
weak ST/LW/RW still picks a weak counter duelist, no matter how thin the
opponent's pool is.

---

## 9. Tactical Fit

Informational only (0–100%), never multiplies anything in §6:

```
tactical_fit = 0.4 × formation_fit        # avg of the existing 1.0/0.9/0.75 position-fit values, per §5-style slot list
             + 0.4 × playstyle_alignment  # is the zone(s) this playstyle uses actually this squad's STRONGEST zone(s)?
             + 0.2 × mentality_fit        # e.g. PARK_THE_BUS scored against (defence zones' strength − attack zones' strength)
```

`playstyle_alignment`: rank all 6 zones for this squad; WING_PLAY scores
well only if `wing_attack`/`wing_defence` are genuinely near the top of that
ranking, not just "good in isolation" — a strong squad playing a style that
doesn't use its best zone gets a mediocre fit score even though every
individual card is excellent. Surfaced in the squad UI as a single
percentage plus one hint line ("Слабое место: центральная защита" /
"Хорошо подходит для игры по флангам") — the underlying formula is never
exposed to the player (Phase 2 UI, §11).

---

## 10. Opponent scouting (Phase 2)

`GET /clubs/tournament/next-opponent` — `TournamentApplyResult`-style
response gated on the caller's club being in an active tournament with a
round left to play:

```python
class NextOpponentOut(BaseModel):
    round_number: int
    opponent_club_id: int
    opponent_club_name: str
    attack: int
    midfield: int
    defence: int
    goalkeeping: int
```

Resolved via `generate_fixtures(club_ids)` (already deterministic and
already used this way in `tournament_simulation_service.py`/
`tournament_notification_service.py`) filtered to
`round_number == tournament.rounds_simulated + 1`, picking whichever pairing
contains the caller's club. The opponent's **current** lineup+formation is
run through §5's profile calculator, then rolled up:

```
Attack      = weighted(central_attack, wing_attack)       # even weight by default
Midfield    = midfield_control
Defence     = weighted(central_defence, wing_defence)
Goalkeeping = goalkeeping
```

**Never exposed:** the opponent's formation, mentality, or playstyle — only
these four rolled-up numbers, so the scouting club can plan around known
*strengths/weaknesses* without being able to hard-counter a specific,
about-to-be-locked-in tactical choice. Both clubs can still freely change
their own formation/mentality/playstyle right up until their round is
simulated; the fixture and the opponent's roll-up numbers can shift between
views if the opponent changes their squad before kickoff (a live snapshot,
not a locked prediction).

---

## 11. UX (Phase 2)

- **`ClubSquadPage.tsx`**: formation selector (dropdown/segmented control),
  mentality selector, playstyle selector, and the Tactical Fit percentage +
  hint line, replacing the current hardcoded "Состав 4-3-3" header.
- **`ClubsPage.tsx` / `TournamentPage.tsx`**: a "Следующий соперник" block
  (round number, opponent name, Attack/Midfield/Defence/Goalkeeping) placed
  right after the existing tournament-status card (per the current file's
  layout — see the countdown block already there), with
  "Изменить состав" / "Изменить тактику" shortcuts into the squad screen.
- Match event descriptions (`_describe_event`, §6.7) gain a handful of new
  templates keyed to how the chance was built (e.g. "Быстрая контратака по
  левому флангу", "Высокий прессинг перехватывает мяч", "Атака через центр
  находит момент") so the log visibly reflects the chosen playstyle without
  becoming noisier — same event count, just occasionally tactic-flavored
  phrasing.

---

## 12. Configuration strategy

Per the explicit "don't create hundreds of poorly-maintained fields"
constraint: the *structural* tables in this spec (§5's position→zone
weights, §6.3's breakdown/stall/advance and chance-quality bands, §7's
mentality table, §8's playstyle table) are **Python module-level constants**
in the new services, following the exact precedent already set by
`lineup_service.TACTIC_MULTIPLIERS` and `tournament_match_engine._FLAVOR_WEIGHTS`
— matrix-shaped tuning data that doesn't fit `GameConfig`'s flat-scalar
convention, and isn't something an admin needs to live-tune from a phone.

`GameConfig` gains a small number of genuinely independent scalar knobs
(Phase 1, admin-editable, mirroring the existing `club_game_*`/`match_*`
grouping convention in `AdminGamesPage.tsx`):

- `club_tactical_phases_per_match_min` / `_max` (default 40 / 70)
- `club_tactical_promoted_chance_target_min` / `_max` (default 15 / 25 —
  used to sanity-check/clip how many phases get promoted to logged events,
  keeping match length in the range players see today)
- `club_tactical_fit_formation_weight` / `_playstyle_weight` /
  `_mentality_weight` (default 0.4 / 0.4 / 0.2, §9 — admin can rebalance
  which axis matters most for the displayed percentage without a deploy)

---

## 13. Migration of existing clubs and in-progress tournaments

Per explicit decision: this ships for **everyone at once**, including
tournaments already mid-season. There is no dual-engine flag, no
per-tournament opt-in.

- Every `club_lineups` row gets the three new columns via `server_default`
  (§3) — structurally identical to today's single 4-3-3, just now labeled
  and changeable.
- An in-progress tournament's *remaining* rounds are simulated by the new
  engine the next time `simulate_next_round` runs after deploy; already-
  simulated rounds/results/standings are untouched (nothing about past
  `TournamentMatch` rows changes retroactively).
- `resolve_match_lineup`'s substitution logic, `_decay_availability`,
  `_apply_engine_result` (injuries/cards), `apply_match_result` (standings),
  `conclude_tournament` (rewards) — all unchanged, per §14's "don't break
  existing mechanics" list below.

---

## 14. Tests and balance simulation

**Unit tests** (Phase 1), one file per new service plus updated
`test_tournament_match_engine.py`/`test_tournament_simulation_service.py`
for the refactored call sites:

1. Two strong ST in a squad produce a higher `central_attack` (and thus
   better-used) under 4-4-2/3-5-2 than the same two ST with one forced onto
   a mismatched flank slot in 4-3-3.
2. A squad with strong LW/RW/LB/RB gets a measurably higher share of
   HIGH/VERY_HIGH chances under WING_PLAY than the same squad under
   CENTRAL_PLAY, run over many simulated phases.
3. A squad with weak flanks does **not** get an inflated advantage from
   WING_PLAY — `tactical_fit`'s `playstyle_alignment` term is low, and raw
   simulated outcomes don't improve versus CENTRAL_PLAY.
4. PARK_THE_BUS with weak defenders does not out-defend the same squad on
   BALANCED against a strong attacker (§6.5's worked example, reproduced as
   an automated statistical assertion over N simulated matches).
5. COUNTER_ATTACK's `conversion_score` is measurably higher when simulated
   against an ATTACKING/HIGH_PRESS opponent than against a PARK_THE_BUS/
   DEFENSIVE one, all else equal.
6. HIGH_PRESS raises the pressing team's transition win rate against a
   POSSESSION opponent with mediocre `midfield_control`, and that same
   HIGH_PRESS team concedes above-baseline counter chances against a
   COUNTER_ATTACK opponent.
7. A 70-rated squad does not statistically beat a 95-rated squad even with
   an optimal tactical matchup (large gap holds up over N simulated
   matches) — tactics narrow the gap, never invert it at this magnitude.
8. Two identical squads on identical settings simulate to ~50/50 over many
   matches.
9. Existing, unrelated tournament mechanics keep passing unmodified:
   8-club formation, 14-round round-robin scheduling, standings/points,
   tie-break ranking, rewards distribution, form multiplier (UI-only per
   §5), injuries/suspensions/bench substitution, match history, and every
   currently-passing test in `test_tournament_simulation_service.py`,
   `test_tournament_standing_service.py`, `test_tournament_fixture_service.py`,
   `test_tournament_reward_service.py`.

**Balance simulation script** (Phase 3, not pytest —
`backend/scripts/simulate_tactical_balance.py` or similar): runs 1000+
matches per scenario and prints a summary table for each of the 8 scenarios
listed in the original brainstorm (§31: identical squads →~50/50; identical
squads + one counter-tactic → clear edge; slightly-weaker-but-well-tacticed
vs slightly-stronger-but-mis-tacticed → close/edge to the weaker side;
huge gap → strong side still clear favorite; strong flanks + WING_PLAY beats
same squad + CENTRAL_PLAY; strong midfield + POSSESSION realizes that style
well; COUNTER_ATTACK vs ATTACKING beats COUNTER_ATTACK vs PARK_THE_BUS;
PARK_THE_BUS + weak defenders is not a universally strong meta). Coefficients
in §5/§6.3/§7/§8's tables are hand-tuned against this output until every
scenario's result direction (not necessarily exact magnitude) matches intent.

---

## 15. Phases

- **Phase 1 (this plan).** §2–8, §12 (Phase-1 config only), §13, and §14's
  unit tests. Every tournament match, from the next simulated round on,
  runs through the new pipeline. No scouting endpoint, no new UI beyond the
  minimum formation/mentality/playstyle picker needed to actually exercise
  the feature (bare-bones acceptable — polish is Phase 2).
- **Phase 2.** §9 (Tactical Fit surfaced in UI), §10 (scouting endpoint),
  §11 (full UX pass, event-log flavor text).
- **Phase 3.** §14's balance script and the resulting coefficient tuning
  pass.

**Explicit non-goals for all three phases:** formation/mentality/playstyle
for the *personal* Card Arena system (§1); a form-multiplier that varies
per-zone rather than only `team_strength`; more than the four listed
formations (registry is extensible, but no fifth formation ships now);
showing the opponent's own formation/mentality/playstyle anywhere (§10).
