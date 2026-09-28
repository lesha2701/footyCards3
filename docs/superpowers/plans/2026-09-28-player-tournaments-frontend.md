# Player Tournaments — Frontend Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Give players a Mini App UI for the 16-player, 30-round tournament backend already shipped on this branch: a hub (status/apply/queue), a 5-template squad editor, a tournament table + match replay, and a rating leaderboard.

**Architecture:** Five new pages that mirror the existing club-tournament and Card Arena screens field-for-field, reusing every shared component (`CardPickerModal`, `UserCoachCardPickerModal`, `TournamentMatchReplay`, `FORMATIONS`/`MENTALITIES`/`PLAYSTYLES`, `CATEGORY_POSITIONS`/`CATEGORY_LABELS`) unchanged. Only one existing file (`PlayPage.tsx`) gets a small, backward-compatible extension. No backend, club, or Card Arena code changes.

**Tech Stack:** React 18, TypeScript, Vite, TanStack Query, react-router-dom v6, Tailwind CSS, Vitest.

**Spec:** `docs/superpowers/specs/2026-09-25-league-tournaments-design.md` (backend-focused; the frontend screens below were designed and approved in chat on 2026-09-28 — this plan is that design's authoritative record) and `docs/superpowers/plans/2026-09-25-player-tournaments-backend.md` (the API this plan consumes, already implemented on this branch at commit `8ec6438`).

## Global Constraints

- The hub route is **exactly** `/player-tournament` (singular, no trailing segment) — the bot's notification deep-links (`bot/services/notifier.py`'s `_TYPE_PATHS`) already point here; renaming it breaks push notifications silently.
- Backend API base path: `/player-tournaments` (plural) under the app's existing `/api/v1` prefix, reached through the shared `api` axios instance from `@/lib/api` — never hardcode a different base.
- Reuse existing shared components as-is: `components/cards/CardPickerModal.tsx`, `components/cards/UserCoachCardPickerModal.tsx`, `components/clubs/TournamentMatchReplay.tsx`. Do not modify them.
- Reuse existing shared constants: `FORMATIONS`/`MENTALITIES`/`PLAYSTYLES` from `@/lib/clubTactics`, `CATEGORY_POSITIONS`/`CATEGORY_LABELS`/`FormationSlot` from `@/lib/formation`.
- Errors surface via `formatGameError(err, fallback)` from `@/lib/errors`, same as every other page in this codebase — never re-derive error text.
- Money/points values come only from the API response — never compute or guess rewards/rating client-side.
- TypeScript typecheck (`npm run typecheck`) and lint (`npm run lint`) must pass for every task; this project has no dedicated tests for page-level components (`TournamentPage`, `ClubSquadPage`, `ArenaPage` have none either) — do not add new test files for the new pages unless a task says otherwise.
- Keep Telegram UI mobile-first: use the existing design tokens (`bg-bg-surface`, `text-ink-chalk`, `text-ink-mist`, `accent-lime`, `accent-cyan`, `font-display`, `font-mono`) exactly as the mirrored pages use them — never introduce new colors or raw hex values.
- Do not touch admin panel files, club tournament files, or backend files in this plan.

## File Structure

**Create**
- `frontend/src/api/personalTournament.ts` — every `/player-tournaments/*` call.
- `frontend/src/pages/PlayerTournamentPage.tsx` — hub (`/player-tournament`).
- `frontend/src/pages/PlayerTournamentSquadPage.tsx` — squad editor (`/player-tournament/squad`).
- `frontend/src/pages/PlayerTournamentDetailPage.tsx` — table + matches (`/player-tournament/:id`).
- `frontend/src/pages/PlayerTournamentMatchPage.tsx` — replay (`/player-tournament/:id/matches/:matchId`).
- `frontend/src/pages/PlayerTournamentRatingPage.tsx` — leaderboard (`/player-tournament/rating`).

**Modify**
- `frontend/src/types/index.ts` — append the new response shapes.
- `frontend/src/App.tsx` — import the 5 pages, register the 5 routes.
- `frontend/src/pages/PlayPage.tsx` — one new `GameCard` entry, one small (additive) prop on the local `GameCard` helper.

---

### Task 1: Types and API client

**Files:**
- Modify: `frontend/src/types/index.ts`
- Create: `frontend/src/api/personalTournament.ts`

**Interfaces:**
- Produces (types, exact shape of the backend's Pydantic schemas — see `backend/app/schemas/personal_squad.py` and `backend/app/schemas/player_tournament.py`): `PersonalSquadSlot`, `PersonalSquad`, `PlayerTournamentStatus`, `PlayerTournamentApplyResult`, `PlayerTournamentCurrent`, `PlayerTournamentStanding`, `PlayerTournamentMatchSummary`, `PlayerTournamentDetail`, `PlayerTournamentMatchDetail`, `TournamentRatingRow`.
- Produces (functions, all consumed by Tasks 2–5): `fetchPersonalSquads`, `fetchPersonalSquadCoachCards`, `setPersonalSquadCards`, `setPersonalSquadTactics`, `setPersonalSquadCoach`, `renamePersonalSquad`, `activatePersonalSquad`, `applyToPlayerTournament`, `fetchPlayerTournamentCurrent`, `fetchPlayerTournamentRating`, `fetchPlayerTournamentDetail`, `fetchPlayerTournamentMatch`.

- [ ] **Step 1: Append types**

Open `frontend/src/types/index.ts` and add the following block after the existing `TournamentMatchDetail` interface (around line 1482, right before the `BingoGoalType` section) — keep it in this location so it sits next to the club tournament types it mirrors:

```typescript
export interface PersonalSquadSlot {
  slot_code: string;
  category: string;
  ideal_position: string;
  user_card_id: number | null;
  serial_number: number | null;
  player: Player | null;
}

export interface PersonalSquad {
  template_index: number;
  name: string;
  is_active: boolean;
  is_complete: boolean;
  formation: string;
  mentality: string;
  playstyle: string;
  slots: PersonalSquadSlot[];
  coach: EquippedCoach | null;
}

export type PlayerTournamentStatus = "not_queued" | "queued" | "active" | "completed";

export interface PlayerTournamentApplyResult {
  queued: boolean;
  tournament_id: number | null;
  queue_position: number | null;
  queue_size: number;
}

export interface PlayerTournamentCurrent {
  status: PlayerTournamentStatus;
  queue_position: number | null;
  queue_size: number;
  tournament_id: number | null;
  can_apply: boolean;
}

export interface PlayerTournamentStanding {
  user_id: number;
  display_name: string;
  points: number;
  goals_for: number;
  goals_against: number;
  final_rank: number | null;
  coins_awarded: number | null;
  rating_delta: number | null;
}

export interface PlayerTournamentMatchSummary {
  id: number;
  round_number: number;
  user_a_id: number;
  user_b_id: number;
  score_a: number;
  score_b: number;
}

export interface PlayerTournamentDetail {
  id: number;
  status: string;
  rounds_simulated: number;
  standings: PlayerTournamentStanding[];
  matches: PlayerTournamentMatchSummary[];
  next_round_seconds_remaining: number | null;
}

export interface PlayerTournamentMatchDetail {
  id: number;
  round_number: number;
  user_a_id: number;
  user_b_id: number;
  user_a_name: string;
  user_b_name: string;
  score_a: number;
  score_b: number;
  event_log: MatchEvent[];
}

export interface TournamentRatingRow {
  user_id: number;
  display_name: string;
  tournament_rating: number;
}
```

`EquippedCoach` (used above) is already defined earlier in this same file — do not redefine it. `Player` and `MatchEvent` are likewise already defined.

- [ ] **Step 2: Write the API client**

Create `frontend/src/api/personalTournament.ts`:

```typescript
import { api } from "@/lib/api";
import type {
  PersonalSquad,
  PlayerTournamentApplyResult,
  PlayerTournamentCurrent,
  PlayerTournamentDetail,
  PlayerTournamentMatchDetail,
  TournamentRatingRow,
  UserCoachCard,
} from "@/types";

export async function fetchPersonalSquads(): Promise<PersonalSquad[]> {
  const { data } = await api.get<PersonalSquad[]>("/player-tournaments/squads");
  return data;
}

export async function fetchPersonalSquadCoachCards(): Promise<UserCoachCard[]> {
  const { data } = await api.get<UserCoachCard[]>("/player-tournaments/squads/coach-cards");
  return data;
}

export async function setPersonalSquadCards(
  templateIndex: number, slots: { slot_code: string; user_card_id: number }[],
): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/cards`, { slots });
  return data;
}

export async function setPersonalSquadTactics(
  templateIndex: number, payload: { formation: string; mentality: string; playstyle: string },
): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/tactics`, payload);
  return data;
}

export async function setPersonalSquadCoach(templateIndex: number, userCoachCardId: number | null): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(
    `/player-tournaments/squads/${templateIndex}/coach`, { user_coach_card_id: userCoachCardId },
  );
  return data;
}

export async function renamePersonalSquad(templateIndex: number, name: string): Promise<PersonalSquad> {
  const { data } = await api.put<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/name`, { name });
  return data;
}

export async function activatePersonalSquad(templateIndex: number): Promise<PersonalSquad> {
  const { data } = await api.post<PersonalSquad>(`/player-tournaments/squads/${templateIndex}/activate`);
  return data;
}

export async function applyToPlayerTournament(): Promise<PlayerTournamentApplyResult> {
  const { data } = await api.post<PlayerTournamentApplyResult>("/player-tournaments/apply");
  return data;
}

export async function fetchPlayerTournamentCurrent(): Promise<PlayerTournamentCurrent> {
  const { data } = await api.get<PlayerTournamentCurrent>("/player-tournaments/current");
  return data;
}

export async function fetchPlayerTournamentRating(): Promise<TournamentRatingRow[]> {
  const { data } = await api.get<TournamentRatingRow[]>("/player-tournaments/rating");
  return data;
}

export async function fetchPlayerTournamentDetail(id: number): Promise<PlayerTournamentDetail> {
  const { data } = await api.get<PlayerTournamentDetail>(`/player-tournaments/${id}`);
  return data;
}

export async function fetchPlayerTournamentMatch(matchId: number): Promise<PlayerTournamentMatchDetail> {
  const { data } = await api.get<PlayerTournamentMatchDetail>(`/player-tournaments/matches/${matchId}`);
  return data;
}
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run typecheck`
Expected: no errors (these two files have no consumers yet, but must be internally well-typed).

---

### Task 2: Hub page + entry point in Play

**Files:**
- Create: `frontend/src/pages/PlayerTournamentPage.tsx`
- Modify: `frontend/src/pages/PlayPage.tsx`, `frontend/src/App.tsx` (route only — full route list finalized in Task 4's step, but register this one route now so the page is reachable for manual testing; Task 4 adds the rest)

**Interfaces:**
- Consumes: `fetchPlayerTournamentCurrent`, `applyToPlayerTournament` (Task 1).
- Produces: nothing new consumed elsewhere.

- [ ] **Step 1: Write the hub page**

Create `frontend/src/pages/PlayerTournamentPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import { applyToPlayerTournament, fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronRight, IconClock, IconFlagCheckered, IconTrophy, IconUsers } from "@/components/icons";
import { formatGameError } from "@/lib/errors";

export default function PlayerTournamentPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [applyError, setApplyError] = useState<string | null>(null);

  const { data: current, isLoading } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });

  const applyMutation = useMutation({
    mutationFn: applyToPlayerTournament,
    onSuccess: () => {
      setApplyError(null);
      queryClient.invalidateQueries({ queryKey: ["player-tournament", "current"] });
    },
    onError: (err) => setApplyError(formatGameError(err, "Не удалось подать заявку")),
  });

  if (isLoading) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
        <IconFlagCheckered size={20} className="text-accent-lime" />
        Личный турнир
      </h1>
      <p className="text-xs text-ink-mist">
        16 игроков, 30 туров (2 круга) — свой состав, своя тактика. Тур симулируется 3 раза в день.
      </p>

      <button
        onClick={() => navigate("/player-tournament/squad")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconUsers size={16} className="text-accent-lime" />
        Состав для турнира
        <IconChevronRight size={16} className="ml-auto text-ink-mist-dim" />
      </button>

      <button
        onClick={() => navigate("/player-tournament/rating")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconTrophy size={16} className="text-accent-lime" />
        Рейтинг турнира
        <IconChevronRight size={16} className="ml-auto text-ink-mist-dim" />
      </button>

      {(current?.status === "active" || current?.status === "completed") && current.tournament_id != null && (
        <button
          onClick={() => navigate(`/player-tournament/${current.tournament_id}`)}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconFlagCheckered size={16} className="text-accent-lime" />
          Мой турнир
          {current.status === "active" && (
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-accent-lime/10 px-2 py-1 text-[10px] font-bold text-accent-lime">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-lime" />
              Идёт
            </span>
          )}
        </button>
      )}

      {current?.status === "queued" && (
        <div className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">
          <IconClock size={16} className="text-accent-lime" />
          В очереди на турнир — место {current.queue_position} из {current.queue_size}
        </div>
      )}

      {current?.can_apply && (
        <button
          onClick={() => applyMutation.mutate()}
          disabled={applyMutation.isPending}
          className="relative flex items-center gap-4 overflow-hidden rounded-3xl bg-gradient-to-br from-accent-lime/25 via-accent-cyan/10 to-bg-surface p-5 text-left active:scale-[0.98] disabled:opacity-40"
        >
          <div className="pointer-events-none absolute -right-6 -top-8 h-28 w-28 rounded-full bg-accent-lime/25 blur-2xl" />
          <div className="relative flex h-12 w-12 shrink-0 items-center justify-center rounded-2xl bg-accent-lime/20 text-accent-lime">
            <IconTrophy size={22} />
          </div>
          <div className="relative min-w-0 flex-1">
            <p className="font-display text-base font-bold text-ink-chalk">Состав готов!</p>
            <p className="mt-0.5 text-xs leading-snug text-ink-mist">
              Подай заявку и жди, пока наберётся 16 игроков — турнир начнётся сам
            </p>
          </div>
          <IconChevronRight size={18} className="relative shrink-0 text-ink-mist-dim" />
        </button>
      )}

      {current && !current.can_apply && current.status === "not_queued" && (
        <button
          onClick={() => navigate("/player-tournament/squad")}
          className="flex items-center gap-2 rounded-2xl bg-white/5 p-3 text-left text-xs text-ink-mist-dim active:scale-[0.99]"
        >
          <IconUsers size={14} />
          Заполни все 11 позиций в составе, чтобы подать заявку на турнир
        </button>
      )}

      {applyError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{applyError}</p>}
    </div>
  );
}
```

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`:
1. Add `import PlayerTournamentPage from "@/pages/PlayerTournamentPage";` next to the other page imports (alongside `import ClubLeaderboardPage from "@/pages/ClubLeaderboardPage";` is a reasonable spot).
2. Inside the `<Route element={<AppLayout />}>` block, add `<Route path="/player-tournament" element={<PlayerTournamentPage />} />` next to `<Route path="/clubs/leaderboard" element={<ClubLeaderboardPage />} />`.

(Task 4 will add the remaining 4 routes in the same block, right after this one.)

- [ ] **Step 3: Add the entry point in PlayPage**

Open `frontend/src/pages/PlayPage.tsx`.

Add the import at the top, next to the other API imports:
```tsx
import { fetchPlayerTournamentCurrent } from "@/api/personalTournament";
```

Inside the `PlayPage` component, add a query next to the existing ones (after the `limits` query):
```tsx
  const { data: playerTournamentCurrent } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });
```

Add this helper function above `export default function PlayPage()`:
```tsx
function playerTournamentStatusLabel(status?: string, queuePosition?: number | null): string {
  switch (status) {
    case "queued":
      return `В очереди — место ${queuePosition ?? "?"}`;
    case "active":
      return "Турнир идёт";
    case "completed":
      return "Турнир завершён";
    default:
      return "Собери состав и подай заявку";
  }
}
```

Add a new `GameCard` call. Place it right after the `Тактико` `GameCard` block (i.e. right before the `FUT Draft` `GameCard` block) so the two squad-building competitive modes sit together:
```tsx
        <GameCard
          onClick={() => navigate("/player-tournament")}
          Icon={IconFlagCheckered}
          badgeClass="bg-accent-lime"
          title="Личный турнир"
          description="16 игроков, 30 туров — свой состав и тактика"
          stat={playerTournamentStatusLabel(playerTournamentCurrent?.status, playerTournamentCurrent?.queue_position)}
          rightLabel="16 игроков"
        />
```
This needs `IconFlagCheckered` added to the existing icon import list at the top of the file (it currently imports `IconBall, IconBrain, IconCard, IconFlagCheckered is NOT yet imported` — check the current import line and add `IconFlagCheckered` to it if it is missing; do not duplicate it if it is already there for some other reason).

Finally, extend the local `GameCard` helper function (defined at the bottom of this same file) with one new optional prop, `rightLabel`, so the new card's right-hand column doesn't need to fit the existing `remaining`/`limit`/`noLimit` semantics (which are about paid-entry/hourly-limit games and don't apply here). Replace the whole `GameCard` function with:

```tsx
function GameCard({
  onClick,
  Icon,
  badgeClass,
  title,
  description,
  stat,
  remaining,
  limit,
  noLimit,
  rightLabel,
}: {
  onClick: () => void;
  Icon: (props: IconProps) => JSX.Element;
  badgeClass: string;
  title: string;
  description: string;
  stat?: string;
  remaining?: number;
  limit?: number;
  noLimit?: boolean;
  rightLabel?: string;
}) {
  return (
    <button onClick={onClick} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]">
      <span className={`flex h-12 w-12 shrink-0 items-center justify-center rounded-xl ${badgeClass}`}>
        <Icon size={22} className="text-bg-base" />
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-display text-sm font-bold text-ink-chalk">{title}</p>
        <p className="mt-0.5 text-[11px] leading-tight text-ink-mist">{description}</p>
        {stat && <p className="mt-1 font-mono text-[10px] text-ink-mist">{stat}</p>}
      </div>
      <div className="shrink-0 text-right">
        {rightLabel !== undefined ? (
          <p className="text-[10px] text-ink-mist-dim">{rightLabel}</p>
        ) : remaining !== undefined && limit !== undefined ? (
          <>
            <p className={`font-mono text-sm font-bold ${remaining > 0 ? "text-ink-chalk" : "text-red-400"}`}>
              {remaining}/{limit}
            </p>
            <p className="text-[10px] text-ink-mist-dim">осталось в час</p>
          </>
        ) : noLimit ? (
          <p className="text-[10px] text-ink-mist-dim">Платный вход</p>
        ) : (
          <p className="text-[10px] text-ink-mist-dim">...</p>
        )}
      </div>
    </button>
  );
}
```

This is the ONLY change to `GameCard`'s existing behavior: every other call site (`Card Arena`, `Тактико`, `FUT Draft`, etc.) omits `rightLabel`, so `rightLabel !== undefined` is `false` for them and they fall through to the exact same `remaining`/`limit`/`noLimit`/`...` branches as before — verify this by reading the other `GameCard` call sites already in the file and confirming none of them pass a `rightLabel`.

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors. Manually confirm (reading the file back) that every pre-existing `GameCard` call site is untouched.

---

### Task 3: Squad editor

**Files:**
- Create: `frontend/src/pages/PlayerTournamentSquadPage.tsx`
- Modify: `frontend/src/App.tsx` (add this one route)

**Interfaces:**
- Consumes: `fetchPersonalSquads`, `fetchPersonalSquadCoachCards`, `setPersonalSquadCards`, `setPersonalSquadTactics`, `setPersonalSquadCoach`, `renamePersonalSquad`, `activatePersonalSquad` (Task 1); `fetchCollection` (existing, `@/api/collection`); `CardPickerModal`, `UserCoachCardPickerModal` (existing, unmodified); `FORMATIONS`, `MENTALITIES`, `PLAYSTYLES` (existing, `@/lib/clubTactics`); `CATEGORY_POSITIONS`, `CATEGORY_LABELS`, `FormationSlot` (existing, `@/lib/formation`); `BOOST_TYPE_LABELS` (existing, `@/lib/coaches`); `staticUrl` (existing, `@/lib/api`).

- [ ] **Step 1: Write the squad editor page**

Create `frontend/src/pages/PlayerTournamentSquadPage.tsx`:

```tsx
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { useState } from "react";

import CardPickerModal from "@/components/cards/CardPickerModal";
import UserCoachCardPickerModal from "@/components/cards/UserCoachCardPickerModal";
import { IconCheck, IconChevronLeft, IconPlus } from "@/components/icons";
import { ListSkeleton } from "@/components/common/Skeleton";
import { fetchCollection } from "@/api/collection";
import {
  activatePersonalSquad, fetchPersonalSquadCoachCards, fetchPersonalSquads,
  renamePersonalSquad, setPersonalSquadCards, setPersonalSquadCoach, setPersonalSquadTactics,
} from "@/api/personalTournament";
import { staticUrl } from "@/lib/api";
import { BOOST_TYPE_LABELS } from "@/lib/coaches";
import { FORMATIONS, MENTALITIES, PLAYSTYLES } from "@/lib/clubTactics";
import { CATEGORY_LABELS, CATEGORY_POSITIONS, type FormationSlot } from "@/lib/formation";
import { formatGameError } from "@/lib/errors";
import type { PersonalSquadSlot, UserCard } from "@/types";

export default function PlayerTournamentSquadPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const { data: templates, isLoading } = useQuery({ queryKey: ["player-tournament", "squads"], queryFn: fetchPersonalSquads });
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const activeIndex = templates?.find((t) => t.is_active)?.template_index ?? 1;
  const viewedIndex = selectedIndex ?? activeIndex;
  const squad = templates?.find((t) => t.template_index === viewedIndex);

  const [pickerSearch, setPickerSearch] = useState("");
  const { data: collectionPage } = useQuery({
    queryKey: ["collection-for-player-tournament", pickerSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: pickerSearch || undefined }),
  });
  const { data: coachCards } = useQuery({ queryKey: ["player-tournament", "coach-cards"], queryFn: fetchPersonalSquadCoachCards });

  const [pickerSlot, setPickerSlot] = useState<PersonalSquadSlot | null>(null);
  const [coachPickerOpen, setCoachPickerOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const setCardsMutation = useMutation({
    mutationFn: (slots: { slot_code: string; user_card_id: number }[]) => setPersonalSquadCards(viewedIndex, slots),
    onSuccess: () => { setError(null); queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); },
    onError: (err) => setError(formatGameError(err, "Не удалось обновить состав")),
  });

  const setTacticsMutation = useMutation({
    mutationFn: (payload: { formation: string; mentality: string; playstyle: string }) => setPersonalSquadTactics(viewedIndex, payload),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }),
    onError: (err) => setError(formatGameError(err, "Не удалось обновить тактику")),
  });

  const setCoachMutation = useMutation({
    mutationFn: (userCoachCardId: number | null) => setPersonalSquadCoach(viewedIndex, userCoachCardId),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); setCoachPickerOpen(false); },
    onError: (err) => setError(formatGameError(err, "Не удалось назначить тренера")),
  });

  const activateMutation = useMutation({
    mutationFn: () => activatePersonalSquad(viewedIndex),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }),
    onError: (err) => setError(formatGameError(err, "Не удалось переключить шаблон")),
  });

  const [renamingTemplate, setRenamingTemplate] = useState(false);
  const [renameValue, setRenameValue] = useState("");
  const renameMutation = useMutation({
    mutationFn: (name: string) => renamePersonalSquad(viewedIndex, name),
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["player-tournament", "squads"] }); setRenamingTemplate(false); },
  });

  const updateTactics = (patch: Partial<{ formation: string; mentality: string; playstyle: string }>) => {
    if (!squad) return;
    setTacticsMutation.mutate({ formation: squad.formation, mentality: squad.mentality, playstyle: squad.playstyle, ...patch });
  };

  if (isLoading) return <ListSkeleton />;

  const usedPlayerIds = (pickerSlot
    ? squad?.slots.filter((s) => s.player && s.slot_code !== pickerSlot.slot_code)
    : squad?.slots.filter((s) => s.player)
  )?.map((s) => s.player!.id) ?? [];

  const cardsForSlot = (slot: PersonalSquadSlot): UserCard[] => {
    const positions = CATEGORY_POSITIONS[slot.category as FormationSlot["category"]];
    return (collectionPage?.items ?? []).filter((c) => positions.includes(c.player.position));
  };

  const assignSlot = async (slot: PersonalSquadSlot, card: UserCard) => {
    const currentSlots = (squad?.slots ?? [])
      .filter((s) => s.user_card_id != null && s.slot_code !== slot.slot_code)
      .map((s) => ({ slot_code: s.slot_code, user_card_id: s.user_card_id! }));
    currentSlots.push({ slot_code: slot.slot_code, user_card_id: card.id });
    try {
      await setCardsMutation.mutateAsync(currentSlots);
      setPickerSlot(null);
      setPickerSearch("");
    } catch {
      // Error is surfaced via setCardsMutation's onError; keep the picker
      // open so the player can choose a different card instead of it
      // silently closing.
    }
  };

  return (
    <div className="flex flex-col gap-4 pb-24">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Состав для турнира</h1>
      </div>

      <section className="flex gap-1.5 overflow-x-auto pb-1">
        {(templates ?? []).map((t) => (
          <button
            key={t.template_index}
            onClick={() => { setSelectedIndex(t.template_index); setRenamingTemplate(false); }}
            className={`flex shrink-0 flex-col items-center gap-0.5 rounded-xl px-3 py-1.5 ${
              t.template_index === viewedIndex ? "bg-accent-lime text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            <span className="whitespace-nowrap text-[11px] font-bold">{t.name}</span>
            {t.is_active && (
              <span className={`text-[8px] ${t.template_index === viewedIndex ? "text-bg-base/70" : "text-accent-lime"}`}>
                Активный
              </span>
            )}
          </button>
        ))}
      </section>

      {renamingTemplate ? (
        <div className="flex gap-2">
          <input
            value={renameValue}
            onChange={(e) => setRenameValue(e.target.value)}
            maxLength={64}
            className="flex-1 rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
            autoFocus
          />
          <button
            onClick={() => renameMutation.mutate(renameValue)}
            disabled={!renameValue.trim() || renameMutation.isPending}
            className="rounded-xl bg-accent-lime px-4 py-2 text-xs font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
        </div>
      ) : (
        <button
          onClick={() => { setRenameValue(squad?.name ?? ""); setRenamingTemplate(true); }}
          className="self-start text-[11px] font-semibold text-ink-mist-dim underline underline-offset-2"
        >
          Переименовать «{squad?.name}»
        </button>
      )}

      {viewedIndex !== activeIndex && (
        <button
          onClick={() => activateMutation.mutate()}
          disabled={activateMutation.isPending}
          className="rounded-xl bg-accent-lime/10 px-3 py-2 text-center text-xs font-semibold text-accent-lime disabled:opacity-40"
        >
          {activateMutation.isPending ? "Переключаем..." : `Сделать «${squad?.name}» активным для турнира`}
        </button>
      )}

      {error && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="rounded-2xl bg-bg-surface p-4">
        <div className="mb-3 flex items-center justify-between">
          <p className="font-display text-base font-bold text-ink-chalk">Состав {squad?.formation}</p>
          {squad?.is_complete && (
            <span className="flex items-center gap-1 font-mono text-xs font-bold text-accent-cyan">
              <IconCheck size={14} />
              Заполнен
            </span>
          )}
        </div>

        <div className="mb-3 flex flex-col gap-1.5">
          <TacticSelect
            label="Схема"
            options={FORMATIONS}
            value={squad?.formation ?? "4-3-3"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ formation: value })}
          />
          <TacticSelect
            label="Настрой"
            options={MENTALITIES}
            value={squad?.mentality ?? "BALANCED"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ mentality: value })}
          />
          <TacticSelect
            label="Стиль игры"
            options={PLAYSTYLES}
            value={squad?.playstyle ?? "CENTRAL_PLAY"}
            disabled={!squad || setTacticsMutation.isPending}
            onChange={(value) => updateTactics({ playstyle: value })}
          />
        </div>

        <div className="relative flex flex-col gap-3 overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-950/60 to-emerald-900/30 p-3">
          {(["FWD", "MID", "DEF", "GK"] as const).map((category) => (
            <div key={category} className="relative flex justify-evenly gap-2">
              {category === "GK" && (
                <button
                  onClick={() => setCoachPickerOpen(true)}
                  disabled={setCoachMutation.isPending}
                  className={`absolute left-0 top-0 flex min-w-0 max-w-[72px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 ${
                    setCoachMutation.isPending ? "opacity-60" : ""
                  }`}
                >
                  {squad?.coach ? (
                    <>
                      <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                        <img
                          src={staticUrl(squad.coach.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                          alt="" className="h-full w-full object-cover" loading="lazy"
                        />
                      </div>
                      <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[8px] font-bold leading-none text-accent-cyan">Тренер</span>
                    </>
                  ) : (
                    <>
                      <IconPlus size={16} className="text-ink-mist-dim" />
                      <span className="text-[8px] text-ink-mist-dim">Тренер</span>
                    </>
                  )}
                </button>
              )}
              {squad?.slots
                .filter((slot) => slot.category === category)
                .map((slot) => (
                  <button
                    key={slot.slot_code}
                    onClick={() => setPickerSlot(slot)}
                    disabled={setCardsMutation.isPending}
                    className="flex min-w-0 max-w-[84px] flex-1 flex-col items-center gap-1 rounded-xl bg-black/30 p-1.5 backdrop-blur-sm active:scale-95 disabled:opacity-60"
                  >
                    {slot.player ? (
                      <>
                        <div className="aspect-square w-full overflow-hidden rounded-lg bg-black/40">
                          <img
                            src={staticUrl(slot.player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
                            alt="" className="h-full w-full object-cover" loading="lazy"
                          />
                        </div>
                        <span className="rounded-full bg-black/50 px-1.5 py-0.5 font-mono text-[9px] font-bold leading-none text-accent-cyan">
                          {slot.player.position}
                        </span>
                        <span className="font-mono text-[9px] font-bold leading-none text-accent-lime">{slot.player.rating}</span>
                      </>
                    ) : (
                      <>
                        <IconPlus size={18} className="text-ink-mist-dim" />
                        <span className="text-[9px] text-ink-mist-dim">{CATEGORY_LABELS[slot.category as FormationSlot["category"]]}</span>
                      </>
                    )}
                  </button>
                ))}
            </div>
          ))}
        </div>

        {squad?.coach && (
          <div className="mt-3 rounded-xl bg-white/5 px-3 py-2">
            <p className="text-xs font-semibold text-ink-chalk">{squad.coach.display_name}</p>
            <p className="mt-0.5 text-[11px] text-ink-mist">
              {squad.coach.boosts.map((b) => `${BOOST_TYPE_LABELS[b.boost_type]} +${b.magnitude}`).join(" · ")}
            </p>
          </div>
        )}
      </section>

      {pickerSlot && (
        <CardPickerModal
          open
          title={`Выбери на позицию ${CATEGORY_LABELS[pickerSlot.category as FormationSlot["category"]]}`}
          cards={cardsForSlot(pickerSlot)}
          disabledCardIds={cardsForSlot(pickerSlot).filter((c) => usedPlayerIds.includes(c.player.id)).map((c) => c.id)}
          onSelect={(card) => assignSlot(pickerSlot, card)}
          onClose={() => { setPickerSlot(null); setPickerSearch(""); }}
          searchValue={pickerSearch}
          onSearchChange={setPickerSearch}
        />
      )}

      <UserCoachCardPickerModal
        open={coachPickerOpen}
        cards={coachCards ?? []}
        onSelect={(card) => setCoachMutation.mutate(card ? card.id : null)}
        onClose={() => setCoachPickerOpen(false)}
      />
    </div>
  );
}

function TacticSelect({
  label, options, value, disabled, onChange,
}: {
  label: string;
  options: { value: string; label: string }[];
  value: string;
  disabled: boolean;
  onChange: (value: string) => void;
}) {
  const selected = options.find((o) => o.value === value);
  return (
    <div className={`relative flex items-center justify-between gap-3 rounded-xl bg-white/5 px-3 py-2.5 ${disabled ? "opacity-60" : ""}`}>
      <span className="shrink-0 text-[10px] uppercase tracking-wide text-ink-mist-dim">{label}</span>
      <span className="flex min-w-0 items-center gap-1.5">
        <span className="truncate text-sm font-semibold text-ink-chalk">{selected?.label ?? value}</span>
      </span>
      <select
        value={value}
        disabled={disabled}
        onChange={(e) => onChange(e.target.value)}
        aria-label={label}
        className="absolute inset-0 h-full w-full cursor-pointer appearance-none opacity-0 disabled:cursor-default"
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>{option.label}</option>
        ))}
      </select>
    </div>
  );
}
```

Note: there is deliberately no diamond-card cap check here (unlike `ArenaPage`/`TacticoSquadPage`) — `personal_squad_service.set_squad_cards` on the backend does not enforce one, so don't invent one client-side.

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`:
1. Add `import PlayerTournamentSquadPage from "@/pages/PlayerTournamentSquadPage";` next to `PlayerTournamentPage`'s import (added in Task 2).
2. Add `<Route path="/player-tournament/squad" element={<PlayerTournamentSquadPage />} />` right after the `/player-tournament` route added in Task 2.

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

---

### Task 4: Tournament detail and match replay pages

**Files:**
- Create: `frontend/src/pages/PlayerTournamentDetailPage.tsx`, `frontend/src/pages/PlayerTournamentMatchPage.tsx`
- Modify: `frontend/src/App.tsx` (add these 2 routes)

**Interfaces:**
- Consumes: `fetchPlayerTournamentDetail`, `fetchPlayerTournamentMatch` (Task 1); `TournamentMatchReplay` (existing, unmodified — its props are `events`, `clubAName`, `clubBName`, `scoreA`, `scoreB`, all generic despite the "club" naming); `formatCountdown` (existing, `@/lib/format`); `useAuthStore` (existing, `@/store/authStore`, for `user.id`).

- [ ] **Step 1: Write the detail page**

Create `frontend/src/pages/PlayerTournamentDetailPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchPlayerTournamentDetail } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconCoin, IconTrophy } from "@/components/icons";
import { formatCountdown } from "@/lib/format";
import { useAuthStore } from "@/store/authStore";
import type { PlayerTournamentMatchSummary, PlayerTournamentStanding } from "@/types";

function resultsGateKey(tournamentId: number) {
  return `player_tournament_results_seen_${tournamentId}`;
}

interface StandingRow extends PlayerTournamentStanding {
  played: number;
  wins: number;
  draws: number;
  losses: number;
}

function buildStandingsRows(
  standings: PlayerTournamentStanding[], matches: PlayerTournamentMatchSummary[],
): StandingRow[] {
  return standings.map((s) => {
    let played = 0;
    let wins = 0;
    let draws = 0;
    let losses = 0;
    for (const m of matches) {
      const isA = m.user_a_id === s.user_id;
      const isB = m.user_b_id === s.user_id;
      if (!isA && !isB) continue;
      played += 1;
      const my = isA ? m.score_a : m.score_b;
      const their = isA ? m.score_b : m.score_a;
      if (my > their) wins += 1;
      else if (my < their) losses += 1;
      else draws += 1;
    }
    return { ...s, played, wins, draws, losses };
  });
}

export default function PlayerTournamentDetailPage() {
  const { id } = useParams<{ id: string }>();
  const tournamentId = Number(id);
  const navigate = useNavigate();
  const myUserId = useAuthStore((s) => s.user?.id);
  const [resultsRevealed, setResultsRevealed] = useState(() => localStorage.getItem(resultsGateKey(tournamentId)) === "1");

  const { data: tournament, isLoading, isError } = useQuery({
    queryKey: ["player-tournament", "detail", tournamentId],
    queryFn: () => fetchPlayerTournamentDetail(tournamentId),
    enabled: Number.isFinite(tournamentId),
  });

  if (isLoading) return <ListSkeleton />;
  if (isError || !tournament) return <EmptyState title="Не удалось загрузить турнир" description="Попробуй обновить страницу" />;

  const revealResults = () => {
    localStorage.setItem(resultsGateKey(tournamentId), "1");
    setResultsRevealed(true);
  };

  const rows = buildStandingsRows(tournament.standings, tournament.matches);

  const matchesByRound = new Map<number, typeof tournament.matches>();
  for (const m of tournament.matches) {
    matchesByRound.set(m.round_number, [...(matchesByRound.get(m.round_number) ?? []), m]);
  }
  const rounds = [...matchesByRound.keys()].sort((a, b) => b - a);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <div>
          <h1 className="font-display text-xl font-bold text-ink-chalk">Турнир #{tournament.id}</h1>
          <p className="text-xs text-ink-mist-dim">
            {tournament.status === "completed" ? "Завершён" : `Тур ${tournament.rounds_simulated}/30`}
            {tournament.next_round_seconds_remaining != null &&
              ` · Новый тур через ${formatCountdown(tournament.next_round_seconds_remaining)}`}
          </p>
        </div>
      </div>

      {tournament.status === "completed" && !resultsRevealed && (
        <button
          onClick={revealResults}
          className="flex items-center justify-center gap-2 rounded-2xl bg-floodlight p-3 text-sm font-bold text-bg-base active:scale-95"
        >
          <IconTrophy size={16} />
          Турнир завершён — смотреть итоги
        </button>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Турнирная таблица</p>
        <div className="overflow-x-auto rounded-2xl bg-bg-surface">
          <table className="w-full min-w-[420px] text-xs">
            <thead>
              <tr className="border-b border-white/5 text-left text-[10px] uppercase text-ink-mist-dim">
                <th className="px-2 py-2 font-semibold">#</th>
                <th className="px-2 py-2 font-semibold">Игрок</th>
                <th className="px-2 py-2 text-center font-semibold">И</th>
                <th className="px-2 py-2 text-center font-semibold">В</th>
                <th className="px-2 py-2 text-center font-semibold">Н</th>
                <th className="px-2 py-2 text-center font-semibold">П</th>
                <th className="px-2 py-2 text-center font-semibold">Мячи</th>
                <th className="px-2 py-2 text-center font-semibold">РМ</th>
                <th className="px-2 py-2 text-right font-semibold">О</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((s) => (
                <tr
                  key={s.user_id}
                  onClick={() => navigate(`/users/${s.user_id}`)}
                  className={`cursor-pointer border-b border-white/5 last:border-0 active:bg-white/5 ${
                    s.user_id === myUserId ? "bg-accent-lime/10" : ""
                  }`}
                >
                  <td className="px-2 py-2 font-mono font-bold text-ink-mist-dim">{s.final_rank ?? "—"}</td>
                  <td className={`px-2 py-2 font-semibold ${s.user_id === myUserId ? "text-accent-lime" : "text-ink-chalk"}`}>
                    {s.display_name}
                  </td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.played}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.wins}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.draws}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.losses}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.goals_for}:{s.goals_against}</td>
                  <td className="px-2 py-2 text-center font-mono text-ink-mist">{s.goals_for - s.goals_against}</td>
                  <td className="px-2 py-2 text-right font-mono font-bold text-ink-chalk">{s.points}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      {tournament.status === "completed" && resultsRevealed && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Итоги турнира</p>
          {rows.map((s) => (
            <div key={s.user_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3 text-sm">
              <span className="text-ink-chalk">#{s.final_rank} {s.display_name}</span>
              <div className="flex items-center gap-3 font-mono text-xs">
                {s.rating_delta !== null && (
                  <span className={`flex items-center gap-1 ${
                    s.rating_delta > 0 ? "text-accent-lime" : s.rating_delta < 0 ? "text-red-400" : "text-ink-mist"
                  }`}>
                    <IconTrophy size={12} />
                    {s.rating_delta > 0 ? `+${s.rating_delta}` : s.rating_delta}
                  </span>
                )}
                {s.coins_awarded !== null && s.coins_awarded > 0 && (
                  <span className="flex items-center gap-1 text-accent-cyan">
                    <IconCoin size={12} />
                    +{s.coins_awarded}
                  </span>
                )}
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Матчи</p>
        {rounds.map((round) => (
          <div key={round} className="flex flex-col gap-1.5">
            <p className="text-xs text-ink-mist-dim">Тур {round}</p>
            {matchesByRound.get(round)!.map((m) => {
              const playerA = tournament.standings.find((s) => s.user_id === m.user_a_id);
              const playerB = tournament.standings.find((s) => s.user_id === m.user_b_id);
              return (
                <button
                  key={m.id}
                  onClick={() => navigate(`/player-tournament/${tournament.id}/matches/${m.id}`)}
                  className="grid grid-cols-[1fr_auto_1fr] items-center gap-2 rounded-xl bg-bg-surface px-3 py-2 text-left text-xs text-ink-chalk active:scale-[0.99]"
                >
                  <span className="truncate text-right">{playerA?.display_name ?? m.user_a_id}</span>
                  <span className="flex items-center justify-center gap-1 font-mono font-bold">
                    <span className="w-4 text-right">{m.score_a}</span>
                    <span>:</span>
                    <span className="w-4 text-left">{m.score_b}</span>
                  </span>
                  <span className="truncate">{playerB?.display_name ?? m.user_b_id}</span>
                </button>
              );
            })}
          </div>
        ))}
      </div>
    </div>
  );
}
```

A standings row navigates to `/users/:userId` (the existing `PublicProfilePage`) on click — there is no per-tournament "preview popup" equivalent to `ClubPreviewPopup`, and building one is out of scope; a full navigation is an acceptable, simpler alternative. Verify `PublicProfilePage` is already registered at `/users/:userId` in `App.tsx` (it is, per the existing route list) before relying on this.

- [ ] **Step 2: Write the match replay page**

Create `frontend/src/pages/PlayerTournamentMatchPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useParams } from "react-router-dom";

import { fetchPlayerTournamentMatch } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { TournamentMatchReplay } from "@/components/clubs/TournamentMatchReplay";

export default function PlayerTournamentMatchPage() {
  const { matchId } = useParams<{ id: string; matchId: string }>();
  const matchIdNum = Number(matchId);

  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["player-tournament", "matches", matchIdNum],
    queryFn: () => fetchPlayerTournamentMatch(matchIdNum),
    enabled: Number.isFinite(matchIdNum),
  });

  if (isError) return <EmptyState title="Не удалось загрузить матч" description="Попробуй обновить страницу" />;
  if (isLoading || !match) return <ListSkeleton />;

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Тур {match.round_number}</h1>
      <TournamentMatchReplay
        events={match.event_log}
        clubAName={match.user_a_name}
        clubBName={match.user_b_name}
        scoreA={match.score_a}
        scoreB={match.score_b}
      />
    </div>
  );
}
```

The `id` route param is intentionally unused here (the backend's match-detail endpoint is keyed only by `match_id`, unlike the club one) — the route still carries `:id` so back-navigation URLs stay symmetric with the detail page's links.

- [ ] **Step 3: Register both routes**

In `frontend/src/App.tsx`:
1. Add the two imports next to `PlayerTournamentSquadPage`'s import:
   ```tsx
   import PlayerTournamentDetailPage from "@/pages/PlayerTournamentDetailPage";
   import PlayerTournamentMatchPage from "@/pages/PlayerTournamentMatchPage";
   ```
2. Add these two routes right after `/player-tournament/squad`:
   ```tsx
   <Route path="/player-tournament/:id" element={<PlayerTournamentDetailPage />} />
   <Route path="/player-tournament/:id/matches/:matchId" element={<PlayerTournamentMatchPage />} />
   ```

- [ ] **Step 4: Verify**

Run: `cd frontend && npm run typecheck && npm run lint`
Expected: no errors.

---

### Task 5: Rating leaderboard page

**Files:**
- Create: `frontend/src/pages/PlayerTournamentRatingPage.tsx`
- Modify: `frontend/src/App.tsx` (add this one route)

**Interfaces:**
- Consumes: `fetchPlayerTournamentRating` (Task 1); `useAuthStore` (existing).

- [ ] **Step 1: Write the rating page**

Create `frontend/src/pages/PlayerTournamentRatingPage.tsx`:

```tsx
import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchPlayerTournamentRating } from "@/api/personalTournament";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconTrophy } from "@/components/icons";
import { useAuthStore } from "@/store/authStore";

export default function PlayerTournamentRatingPage() {
  const navigate = useNavigate();
  const myUserId = useAuthStore((s) => s.user?.id);
  const { data: rows, isLoading } = useQuery({ queryKey: ["player-tournament", "rating"], queryFn: fetchPlayerTournamentRating });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/player-tournament")} className="rounded-full bg-bg-surface p-2 active:scale-95">
          <IconChevronLeft size={18} className="text-ink-chalk" />
        </button>
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconTrophy size={20} className="text-accent-lime" />
          Рейтинг турнира
        </h1>
      </div>

      {isLoading && <ListSkeleton />}

      {!isLoading && !rows?.length && (
        <EmptyState icon={IconTrophy} title="Рейтинг ещё пуст" description="Сыграй турнир, чтобы попасть в список" />
      )}

      <div className="flex flex-col gap-2">
        {rows?.map((entry, index) => (
          <div
            key={entry.user_id}
            className={`flex items-center justify-between rounded-xl px-3 py-2.5 text-sm ${
              entry.user_id === myUserId ? "bg-accent-lime/12" : "bg-bg-surface"
            }`}
          >
            <div className="flex items-center gap-2">
              <span className="w-6 text-center font-mono text-sm font-bold text-ink-mist-dim">{index + 1}</span>
              <span className={entry.user_id === myUserId ? "font-semibold text-accent-lime" : "text-ink-chalk"}>
                {entry.display_name}
              </span>
            </div>
            <span className="font-mono font-bold text-accent-cyan">{entry.tournament_rating}</span>
          </div>
        ))}
      </div>
    </div>
  );
}
```

Note: the backend's `/player-tournaments/rating` endpoint deliberately omits players whose `tournament_rating` is still `0` — that's a backend design choice (see `player_tournament_query_service.get_rating_leaderboard`), not something to work around here; a brand-new player simply won't appear until they've played a tournament.

- [ ] **Step 2: Register the route**

In `frontend/src/App.tsx`:
1. Add `import PlayerTournamentRatingPage from "@/pages/PlayerTournamentRatingPage";` next to the other 4 player-tournament page imports.
2. Add `<Route path="/player-tournament/rating" element={<PlayerTournamentRatingPage />} />` right after `/player-tournament` and before `/player-tournament/squad` (grouping the 3 top-level routes together, ahead of the `:id`-parameterized ones — order doesn't affect matching in React Router v6, but keep it readable).

After this task, `App.tsx` must contain exactly these 5 new routes, in this relative order within the `<Route element={<AppLayout />}>` block:
```tsx
<Route path="/player-tournament" element={<PlayerTournamentPage />} />
<Route path="/player-tournament/rating" element={<PlayerTournamentRatingPage />} />
<Route path="/player-tournament/squad" element={<PlayerTournamentSquadPage />} />
<Route path="/player-tournament/:id" element={<PlayerTournamentDetailPage />} />
<Route path="/player-tournament/:id/matches/:matchId" element={<PlayerTournamentMatchPage />} />
```

- [ ] **Step 3: Verify**

Run: `cd frontend && npm run typecheck && npm run lint && npm run build`
Expected: no errors; the production build succeeds.

---

## Self-review

**Spec coverage:** hub with status/apply/queue — Task 2. Squad editor, 5 templates, formation/mentality/playstyle/coach — Task 3. Tournament table + matches + reveal-gate — Task 4 (detail page). Match replay reusing `TournamentMatchReplay` — Task 4 (match page). Rating leaderboard — Task 5. Entry point from `PlayPage` — Task 2. Exact bot deep-link path `/player-tournament` — Global Constraints + Task 2 route.

**Placeholder scan:** none found — every step contains complete, runnable code, not a description of what to write.

**Type consistency:** `PersonalSquadSlot`/`PersonalSquad`/`PlayerTournamentCurrent`/`PlayerTournamentDetail`/`PlayerTournamentMatchDetail`/`TournamentRatingRow` (Task 1) are consumed with identical field names in Tasks 2–5; `viewedIndex`/`squad`/`pickerSlot` naming is consistent within Task 3; route paths match exactly between where each task registers its route and where earlier/later tasks link to it (`/player-tournament`, `/player-tournament/squad`, `/player-tournament/rating`, `/player-tournament/:id`, `/player-tournament/:id/matches/:matchId`).
