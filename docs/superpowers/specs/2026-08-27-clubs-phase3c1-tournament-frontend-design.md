# Clubs Phase 3c-1: Player-Facing Tournament UI — Design Spec

## Goal

Give players a way to actually experience the tournament pipeline that's been running since Phase 3a: apply, watch the standings, replay matches, see round-14 results, and check a club leaderboard — using the already-shipped backend read API, which currently has zero frontend consumers. First of two Phase 3c sub-phases; admin (`AdminClubsPage`, missing `GameConfig` fields) is 3c-2, separate.

## Corrections to the original spec (found via direct code survey before this design)

- **The tournament engine produces no event descriptions.** The original spec's claim that tournament `event_log` is "the exact same shape" as the personal engine's events is wrong in one load-bearing way: `tournament_match_engine.py`'s events carry `minute`/`event_type`/`team`/`payload` but never a `description` string, while the personal engine's reveal UI renders `event.description` directly. This phase adds description generation to the tournament engine itself (backend-side, per the approved decision below), not the frontend.
- **There is no existing shared "brief info" popup to reuse.** The original spec claimed the browse-list preview already uses one; the browse list (`ClubBrowseList` in `ClubsPage.tsx`) has no click handler on club rows at all today. This phase builds the popup from scratch.
- **`Club.cups_count`/`.stars_count` (added in Phase 3a) are not exposed anywhere frontend-facing** — not in `ClubSummaryOut`/`ClubDetailOut` (backend Pydantic schemas), not in the frontend `Club`/`ClubSummary` TS types. This phase adds them to both.
- **`MatchSimulation` (the personal Card Arena reveal component) is not a shared, reusable component.** It's a private 169-line closure inside `ArenaPage.tsx`, and its coupling to personal-match specifics goes well beyond the `pending_moment`/`onAct` interactive machinery the original spec anticipated: it reads `match.opponent_name`, `match.result`, `match.reward_coins`, `match.status` directly, and hardcodes a `"user"`/`"opponent"` team model with fixed green/gray styling for "you." Retrofitting this into a two-named-clubs, no-personal-reward replay would mean substantially rewriting an already-shipped, live component. This phase instead builds a small, separate `TournamentMatchReplay.tsx` that reuses the same reveal-over-a-timer *mechanic* as fresh code — genuinely simpler than the original, since it carries none of the interactive/personal-reward machinery. `ArenaPage.tsx` is not touched.

## Backend additions

Three small, targeted additions to already-shipped Phase 3a/3b code — same category of cross-phase touch-up Phase 3b's notification hooks already established as normal for this multi-phase feature.

### 1. Event descriptions in `tournament_match_engine.py`

A new `_EVENT_DESCRIPTIONS`-style dict, distinct from the personal engine's (whose phrasing is "your team" vs. "{them}" — meaningless for a replay every viewer watches from a neutral standpoint, regardless of club membership). Templates take real club names directly:

```python
_EVENT_DESCRIPTIONS: dict[str, list[str]] = {
    "goal": ["⚽ Гол! {scorer} забивает за {club}!", "⚽ ГОЛ! {club} открывает счёт усилиями {scorer}!", ...],
    "shot": ["🎯 {club} бьёт мимо ворот", ...],
    "save": ["🧤 Вратарь {club} спасает!", ...],
    "blocked": ["🛡️ Защитник {club} блокирует удар!", ...],
    "pass_failed": ["❌ Пас {club} не находит адресата — атака сорвана", ...],
    "tackle_won": ["🛡️ Защитник {club} чисто отбирает мяч в подкате!", ...],
    "foul_stopped": ["🟨 Фол защитника {club} останавливает атаку", ...],
}
```

(7 event types — confirmed exhaustive: `generate_moment_queue` never persists flavor events to `event_log`, only real shot/tackle outcomes, so this is the complete set, not a partial list to extend later.) `simulate_match` gains `club_a_name`/`club_b_name` parameters; `simulate_next_round` (which already loads both `Club` rows to compute strength/form) passes `.name` through. Descriptions are generated inline at event-creation time, same as the personal engine — not a separate post-processing pass.

### 2. `cups_count`/`stars_count` on `ClubSummaryOut`/`ClubDetailOut`

Two-field addition to `backend/app/schemas/club.py`'s existing Pydantic schemas, populated from the already-existing `Club` model columns — `club_service.py`'s `_club_to_detail`/`list_clubs` construction sites need the two extra fields threaded through, nothing else changes.

### 3. `club_ranking_service.py` (new) + `GET /clubs/leaderboard`

Mirrors `ranking_service.get_ranking`'s exact shape (one unfiltered query, Python top-N slice, linear scan for "my club's position") — Phase 3a's own survey already established the *query* shape transfers cleanly but entry serialization doesn't (personal entries carry avatar/badge; club entries need name/logo). New `ClubRankingEntry`/`ClubRankingResult` schemas, one new endpoint taking `metric: "cups" | "stars"`.

### 4. `TournamentClubResult` data exposed on `TournamentStandingOut`

Checked directly: `TournamentStandingOut`/`TournamentDetailOut` (`backend/app/schemas/tournament.py`) expose only live-standings fields (`points`/`goals_for`/`goals_against`/`final_rank`) — `TournamentClubResult`'s reward fields (`budget_awarded`, `stars_delta`, `cup_awarded`), written once at round 14, are never exposed anywhere. The results screen needs "this club's rank/stars/cup/budget delta," so `TournamentStandingOut` gains three optional fields (`budget_awarded`, `stars_delta`, `cup_awarded`, all `None` until the tournament concludes), populated by `get_tournament_detail` (`clubs.py`) via a lookup against `TournamentClubResult` when `tournament.status == "completed"` — a small addition to a function Task 16 already built, not a new endpoint.

## Frontend: replay viewer

`frontend/src/components/matches/TournamentMatchReplay.tsx` (new, standalone): given `event_log` (now description-complete), a `club_a_name`/`club_b_name`, and `score_a`/`score_b`, reveal-animates through events on the same `revealedCount`/`setTimeout(EVENT_STEP_MS)` mechanic `MatchSimulation` already proved out, with a "Пропустить" skip-to-end button (no auto-play-pending-action loop needed, since there's nothing pending to play — every event is already resolved). No `ActionPrompt`, no breakaway-acknowledgment pause, no win/loss/reward banner (tournament rewards are conclusion-level, not per-match). Live score climbs with revealed goals exactly like the personal version, for the same "don't spoil the ending early" reason.

## Frontend: routes & pages

- **Apply entry point**: a manager-gated "Подать заявку на турнир" button added to `ClubHome` (`ClubsPage.tsx`, alongside the existing squad/packs buttons) — calls `POST /clubs/tournament/apply`, shows queue position or a "tournament formed!" confirmation inline. No new route.
- **`/clubs/tournament/:id`**: standings table (rank/points/GD, already correctly ranked by the backend) + this round's fixture list. A round-robin has no elimination-tree shape despite the feature's working name "bracket" — this is a table + schedule page. Clicking a club row opens the new club-preview popup; clicking a played fixture opens its replay.
- **`/clubs/tournament/:id/matches/:matchId`**: `TournamentMatchReplay`, fed by the existing `GET .../matches/:matchId`.
- **Results screen + gate**: a `localStorage` flag keyed by tournament id, set once the round-14 replay is dismissed — a purely frontend sequencing trick (matching the original spec's own framing), gating a simple results screen showing final standings plus this club's rank/stars/cup/budget delta (all already computed and stored server-side at round 14 regardless of who's watching).
- **`/clubs/leaderboard`**: mirrors `RankingPage.tsx`'s tabs + top-N + "my position" pattern exactly, against the new club-ranking endpoint. New `ClubRankingEntry` TS type, kept separate from personal `RankingEntry` (different fields).
- **Club-preview popup** (new component): founded date, cups, stars — used from both the browse list (which gains a click handler on each row, absent today) and the standings page's club rows.

## Bot-side: restore the `club_match` deep-link

Phase 3b deliberately removed `_MATCH_PATH_PREFIXES["club_match"]` (falling back to the generic "open the app" button) specifically because `/clubs/tournament/:id` didn't exist yet. Now that this phase builds it, restore that one line in `bot/services/notifier.py` — `"club_match": "/clubs/tournament"` — so match-result notifications deep-link straight to the standings/replay page again.

## Testing plan

- Backend: event-description generation produces non-empty text for every one of the 7 event types, using real club names (not the personal engine's "твоя команда" framing); `cups_count`/`stars_count` round-trip through `ClubSummaryOut`/`ClubDetailOut`; `club_ranking_service` matches `ranking_service`'s tie-break/ordering behavior for the two metrics.
- Frontend: `TournamentMatchReplay` reveals events in order and reaches a stable end state without ever attempting an interactive call; the results-gate `localStorage` flag correctly blocks/unblocks the results screen across a simulated dismiss; the apply button reflects all three `/clubs/tournament/current` states (not_queued/queued/active) correctly.
- Manual: full walkthrough — apply as 8 real clubs (dev-mode multi-session), watch a simulated round's replay, confirm the deep-link notification (Phase 3b) now lands on a real page instead of the home-page fallback Phase 3b deliberately left in place.
