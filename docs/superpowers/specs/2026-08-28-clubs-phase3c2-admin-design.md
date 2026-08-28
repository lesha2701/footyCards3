# Clubs Phase 3c-2: Admin Visibility — Design Spec

## Goal

Give the admin panel two things it's had zero visibility into since Clubs launched: a read-only view of clubs/tournaments, and the 11 club/tournament `GameConfig` fields that are already admin-tunable by CLAUDE.md's "Economy config" rule but aren't surfaced anywhere in the admin UI. This is the second and final sub-phase of Phase 3c; after it ships, the Clubs feature is complete relative to the original brainstorm's scope, aside from the separately-deferred mini-game club-contribution mode.

## Scope decisions (confirmed with the user)

- **Read-only.** No moderation actions (force-disband, kick, budget adjustment) in this phase — pure visibility. A moderation action can be added later as its own bounded change if a real support need surfaces.
- **Tournament data lives nested under club detail, not as a separate top-level list.** A club's detail view gets a "Турниры" tab showing that club's own tournament history; there is no standalone all-tournaments admin page in this phase.
- **Disbanded clubs are included** in the admin list (unlike the player-facing browse list, which filters them out) — admin needs to see them for debugging soft-disband cases from Phase 3a's cascade-delete fix.
- **No computed live rank.** The tournament tab shows the club's own stored `TournamentClubStanding` fields (points/goals_for/goals_against) directly, not a cross-club-computed rank — `final_rank` is already stored on `TournamentClubResult` once a tournament completes, so no extra computation is needed there either.

## Current state (confirmed by direct survey before this design)

- Zero existing admin route or admin frontend page reads `Club`/`Tournament*` models — this is fully greenfield, not an extension of an existing flow. `admin_club_packs.py`/`AdminClubPacksPage.tsx` only manage the admin-authored `ClubPack` catalog, unrelated to player-created clubs or live tournaments.
- The `GameConfig` gap is three layers deep, not just the admin page: `backend/app/schemas/admin.py`'s `GameConfigOut`/`GameConfigUpdate` Pydantic schemas omit 11 of the 13 club/tournament fields on the `GameConfig` model (only `club_creation_cost_coins`/`club_daily_reward_coins` are exposed anywhere) — so `GET/PUT /admin/games/config` cannot return or accept these fields today regardless of the frontend. `frontend/src/admin/types.ts`'s `GameConfig` TS interface mirrors the same gap. `AdminGamesPage.tsx` only renders the two already-exposed fields, in its "Общие лимиты" section.
- Two unrelated fields (`maintenance_banner_until`, `last_update_broadcast_at`) are also missing from the same schemas — explicitly out of scope for this phase, since they're managed via dedicated `/admin/maintenance` and `/admin/broadcasts` endpoints already, not the generic config editor.

## Backend: `admin_clubs.py`

New router, `prefix="/admin/clubs"`, `dependencies=[Depends(get_current_admin)]` at the router level — the exact same two-part auth pattern every existing admin router uses (router-level dependency for all reads; this phase has no mutations, so no per-endpoint `admin: User` param or `log_action` call is needed, unlike a write-capable admin router).

- `GET /admin/clubs?search=&page=&page_size=` → `Page[AdminClubSummaryOut]`, mirroring `admin_users.py`'s exact list-endpoint shape: a `select(Club)` plus a parallel count query, an `ilike` name-search filter applied to both, paginated via the existing `PageParams`/`Page.build(...)` primitives (`backend/app/core/pagination.py`). Includes disbanded clubs. Summary fields: `id, name, club_type, logo_shape, logo_color, captain_id, member_count, budget, cups_count, stars_count, founded_at, is_disbanded`.
- `GET /admin/clubs/{club_id}` → `AdminClubDetailOut` — the summary fields plus `description, invite_code, last_tournament_applied_at`. 404 if the club doesn't exist.
- `GET /admin/clubs/{club_id}/members` → a plain (non-paginated — capped at 11 by the game's own `MAX_MEMBERS`) list of `{user_id, username, first_name, role, joined_at}`.
- `GET /admin/clubs/{club_id}/budget-transactions?page=&page_size=` → `Page[...]` over `ClubBudgetTransaction`, since this can genuinely grow large over a club's lifetime (daily claims, tournament rewards, pack purchases) — paginated like `admin_users.py`'s transactions tab.
- `GET /admin/clubs/{club_id}/tournaments` → a plain list (a club realistically plays a small number of tournaments) of `{tournament_id, status, rounds_simulated, points, goals_for, goals_against, final_rank, budget_awarded, stars_delta, cup_awarded}`, joining `TournamentClub` → `Tournament` → `TournamentClubStanding` → an optional `TournamentClubResult` lookup (the last four fields `null` until that specific tournament completes).

## Frontend: `AdminClubsPage.tsx`

Mirrors `AdminUsersPage.tsx`'s established structure exactly (search + paginated table + click-to-open modal with lazily-loaded tabs):

- **List**: search box (by name) above a table with columns Name (+ logo swatch), Type, Captain, Members (`n/11`), Budget, Cups/Stars, Founded, a disbanded-status badge, and an "Открыть" button. Prev/Next pagination reading the `Page` envelope's `page`/`pages`.
- **Detail modal**, opened per-row, with four tabs, each gated `enabled: tab === "..."` so a tab's data only fetches once opened:
  - **Обзор** — description, invite code, captain, founded date, budget, cups/stars, last-tournament-applied timestamp.
  - **Участники** — member table (name, role, joined date).
  - **Бюджет** — paginated `ClubBudgetTransaction` list (type, amount, balance before/after, description, date).
  - **Турниры** — the tournaments list: tournament id, status badge, round progress (`X/14`), points/GF/GA, and once completed, final rank + a cup icon if `cup_awarded` + stars delta + budget awarded.
- **Nav entry**: `AdminLayout.tsx`'s `SECTIONS` array gets `{ to: "/admin/clubs", label: "Клубы", icon: "👥" }` (distinct from `🏟️`, already used by "Клубные паки"), plus the corresponding route registration in `App.tsx`'s `/admin/*` block.

## Backend: expose the 11 missing `GameConfig` fields

Add `club_tournament_cooldown_hours, club_form_window_matches, club_form_bonus_per_result, club_tournament_budget_place_1` through `club_tournament_budget_place_8` to `GameConfigOut` and `GameConfigUpdate` (`backend/app/schemas/admin.py`) — these already exist on the `GameConfig` model itself (Phase 3a), this is purely a schema-exposure gap. Add the same 11 fields to the `GameConfig` TS interface (`frontend/src/admin/types.ts`), keeping it a faithful mirror of the Pydantic schema as it already is for every other field.

## Frontend: extend `AdminGamesPage.tsx`

Add the 11 fields to the page's existing "Общие лимиты" section (already home to `club_creation_cost_coins`/`club_daily_reward_coins`), using the page's existing `field(key, label)` helper closure verbatim — no new UI pattern, no new section. All fields are numeric `<input type="number">` and save through the page's single existing "Сохранить настройки" PUT alongside every other field already there.

## Testing plan

- Backend: `test_admin_clubs.py` — list endpoint (search filtering, disbanded clubs included, pagination correctness), detail endpoint (404 on a missing club), the three sub-resource endpoints (members list shape, budget-transactions pagination, tournaments showing `null` reward fields pre-completion and real values post-completion — reusing the existing 14-round-simulation pattern already established in `test_tournament_api.py`), and auth (403 without a valid admin token). Extend the existing `test_admin_games.py` to round-trip the 11 new fields through `GET`/`PUT /admin/games/config`, the same way every existing field is already tested there.
- Frontend: typecheck only — matches this codebase's existing convention that admin CRUD/list pages (`AdminUsersPage`, `AdminLeaguesPage`, etc.) have no Vitest coverage; verified manually via the browser instead.
- Manual walkthrough: open `/admin/clubs`, search, open a club that has completed a tournament and confirm all four tabs render real data, confirm a disbanded club shows its badge, confirm the 11 new `GameConfig` fields round-trip on `/admin/games`.
