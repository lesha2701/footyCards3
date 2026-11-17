# «Мяч и Магия»: армия из карт существ, капитаны, гвардия

Agreed design (2026-11-11). Built step by step; each step is shown on the preview first.

## Pieces

| What | Role | Losses |
|---|---|---|
| Creature cards («Магический пак») | the fighters of a stack | quick run: half of the fallen die for good (essence), half come back wounded after a day (12 h after a won run); hardcore: all the fallen die, essence ×2 |
| Captain (a footballer, one per stack) | rating → atk/def, position → trait, rarity → the stack's tier cap | never dies; levels up from battles; a duplicate of the captain = +XP |
| Guard (one stack of footballer duplicates) | a levelled stack beside the army | quick run: 50 % of the fallen are lost; hardcore: all; refilled with duplicates at a rate |
| Hero leadership | how many / which tiers the army can take | — |
| Essence | currency of the essence shop | — |

## Numbers (defaults; all in GameConfig / engine constants)

- Card → fighters: I 10, II 8, III 5, IV 3, V 1.
- Pack: 5 cards of any race (Рассвет, Пепел, the wild); tier odds 55 / 28 / 12 / 4.5 / 0.5 %.
  The hero's faction gives spells only — the army mixes whatever the player collected.
- Starter set (once): 4 × I, 2 × II, 1 × III base creatures of each faction.
- Leadership: 10 + hero level; stack cost I 1, II 2, III 3, IV 5, V 8; knight +3, mage −2.
  A stack over the limit fights at half strength («не слушается»).
- Captain tier cap by rarity: common II, rare III, epic IV, legendary / diamond V.
- Captain levels 1–5 (trait choice at 3 and 5); duplicate of the same footballer = +XP.
- Guard: levels 1–10 (+atk/+def/+hp by turns, traits at 3 / 6 / 9), size cap 15 → 40;
  refill: same footballer 1→1, same rarity 2→1, lower 3→1, higher 3→2, same club one step better.
  Changing the guard's footballer burns 50 % of its XP.

## Steps

1. Creature cards, «Магический пак» (coins / Stars), starter set, collection on the game page.
2. The army from creature cards + leadership + captains on the army screen.
3. Losses, wounded, essence (done):
   - the engine counts the collection's own fallen per stack (`state["fallen"]`): hired fighters fall
     first, a tribune refill brings own fallen back first, a forfeit inside a battle = the field fell,
     a second chance in the final restores the fallen as they were before it;
   - `engine.casualties` splits them by `DEAD_PCT` (quick 50, hardcore 100), essence per fallen fighter
     `ESSENCE` I 1 · II 2 · III 5 · IV 15 · V 100 (hardcore ×2);
   - `_finish` → `_apply_casualties`: the dead leave `users.magic_creatures.have`, the wounded go to
     `wounded` with `until` (GameConfig `magic_wounded_hours`, halved after a won run), essence to `essence`;
   - healed by time on any read (`_ensure_starter` → `_settle_creatures`), now for essence
     (`POST /magic/heal`, `magic_heal_essence_pct` of their essence value) or Stars (`magic_heal:1`,
     `magic_heal_stars`); an empty collection gets the free starter set of one faction once a day;
   - the risk is shown before every start, on the army screen, above every battle and in the forfeit dialog.
4. Essence shop (done): `GET /magic/shop`, `POST /magic/shop/buy {code}` — a pack
   (`magic_essence_pack`), +1 leadership / +1 mana (base price × (owned + 1), caps
   `magic_essence_leadership_max` / `magic_essence_mana_max`, kept in `magic_creatures.bonus`),
   hero / castle skins (Stars price × `magic_essence_per_star` or coins × `magic_essence_per_100_coins` / 100).
5. Captains (done): XP for levels 1–5 `CAPTAIN_XP` 0 / 2 500 / 8 000 / 20 000 / 45 000, +5 % atk/def per
   level, a trait (`TRAITS`: striker +15 % atk / wall +15 % def / stamina +20 % hp / pace +1 spd) at
   levels 3 and 5 — all in % so a level weighs the same on any tier. XP from a run `run_xp` = 20 + 10 per
   won battle + 40 for a won run (0 for a forfeit), × `magic_progress_xp_pct`; a spare copy of the same
   footballer = `magic_captain_dup_xp` (150), at most `magic_captain_dup_daily` (1) a day per captain
   (`POST /magic/captains/{id}/feed`). Spares are plain copies (`can_burn`, no path / skill / stars /
   diamond / artifact / equipment), never a personal-squad copy, and one copy always stays.
   Kept in `magic_creatures.captains` (`fed_day` / `fed` for the daily cap).
6. Guard (done): one unit per rarity of its footballer (`GUARD_UNITS`): common tier II «сомкнутые щиты»,
   rare III «натиск», epic IV «двойной ответ», legendary / diamond V «удар чемпиона». Every rarity has
   the same power budget: `guard_size(level, unit)` = the rare guard's 15 → 40 × its unit value / this
   unit's (common 28 → 74, rare 15 → 40, epic 6 → 15, legendary 3 → 7), a fighter costs
   `guard_fighter_points` (3 / 6 / 15 / 35) refill points; a copy gives 6 (same footballer), 4 (higher
   rarity), 3 (same), 2 (lower). The rating gives no bonus. Levels 1–10 `GUARD_XP` 0 … 54 000, +5 %
   atk/def and +4 % hp per level, traits at 3 / 6 / 9; costs no leadership, stack `g1`. A change of
   footballer halves the XP and converts the fighters by weight. It loses `DEAD_PCT` of its fallen.
   `PUT /magic/guard`, `POST /magic/guard/refill`, `POST /magic/guard/trait`.

Pace (GameConfig): 5 free runs a day (`magic_daily_limit`), then 1 for coins and 4 for Stars
(`magic_extra_runs_daily_limit`), played in a row — magic has no shared hourly cap; the day resets
them. With ~90 XP a run: a Stars player (10 runs a day) maxes the guard in ~2 months, a free player
(5 a day) in ~4; captains ~1.5 / ~2.5 months; hero level 10 (`HERO_LEVELS` up to 95 000, hero XP = the
run score) ~1 / ~2 months. The essence shop's +leadership / +mana cost 450 / 360 × (owned + 1).
Rivals grow with the progress only by `magic_progress_scaling_pct` (60): camps and the final are scaled
from `start_power` = the army's power minus 40 % of what levels, traits and the guard add.
The weekly challenge caps captains and the guard at `magic_challenge_level_cap` (3) with their
traits, and ignores the mana bonus — skill decides there, not the time played.

Free revival (done): after the first run with dead, once per account (`magic_creatures.revive_used`),
`POST /magic/revive` returns the dead of that run and takes back the essence paid for them.
