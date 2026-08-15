# Tasks Page Design Cleanup

## Goal

`frontend/src/pages/TasksPage.tsx` is the last page still using leftover
emoji-as-UI-chrome and raw Tailwind `slate-*` text colors from the app's
earliest design. Every other current page (Ranking, Play, Collection,
Packs, Gifts) uses the app's own icon components (`@/components/icons`)
and semantic color tokens (`ink-chalk`/`ink-mist`/`ink-mist-dim`) instead.
This is a pure visual cleanup to bring Tasks in line — no structural,
layout, or behavioral changes.

## Reference pattern (already established elsewhere)

- Page header: `<h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk"><IconX size={20} className="text-accent-lime" />Title</h1>`
  (seen verbatim in `RankingPage.tsx`, `PlayPage.tsx`).
- Body/label text: `text-ink-chalk` (primary) / `text-ink-mist` (secondary),
  never raw `text-slate-*`.
- Reward/stat chips: icon component + text, e.g. `PacksPage.tsx`'s
  `<IconCoin size={10} />+{amount}`.
- One large "hero" emoji (`text-2xl`/`text-3xl`) as an illustrative icon for
  a special object inside a tinted rounded container is an accepted
  pattern (see `GiftsPage.tsx`'s 🎁), as is a single festive emoji prefix
  in a celebratory modal heading (`GiftsPage.tsx`'s "🎉 Подарок открыт!").
  These are *not* in scope for removal.

## Changes (`TasksPage.tsx` only)

1. **Page header**: `🎯 Задания` (`text-2xl`, `text-slate-100`) →
   `<IconTarget size={20} className="text-accent-lime" />` + "Задания"
   (`text-xl`, `text-ink-chalk`), matching the reference pattern above.
   `IconTarget` is already imported in this file.
2. **`TabButton`** (shared by the Обычные/Премиум tabs and the
   Активные/Выполненные filter): inactive label color `text-slate-300` →
   `text-ink-mist`. Active state (`bg-accent text-bg-base`) is unchanged.
3. **`TaskCard`**:
   - Name: `text-slate-100` → `text-ink-chalk`.
   - Description: `text-slate-400` → `text-ink-mist`.
   - Reward display (top-right): replace the literal `📦 {name}` /
     `+{coins} 🪙` string with an inline icon: `<IconPack size={14} />` or
     `<IconCoin size={14} />` next to the same text. Keep `text-amber-300`
     and the `font-display text-sm font-bold` sizing — unchanged, it
     already matches the app's legendary/premium amber.
   - Claimed marker: `✓ Награда получена` → `<IconCheck size={14} />` +
     "Награда получена", same `text-emerald-400` styling.
   - Premium border/background (`border-amber-500/30 bg-amber-500/5`) is
     **unchanged** — it already matches the app's legendary-rarity amber
     and is the intended premium marker per the user's explicit ask to
     keep premium tasks intuitively recognizable.
   - Subscribe/claim buttons: unchanged (styled in a prior session turn).
4. **`RewardClaimedModal`**: keep the large "🎉" as-is (matches the
   accepted hero-emoji pattern). Body text `text-slate-100`/`text-slate-400`
   → `text-ink-chalk`/`text-ink-mist`. The "Ок" button
   (`bg-accent text-bg-base`) is unchanged.

## Out of scope

- No changes to component structure, layout, tab/filter logic, or the
  progress bar.
- No changes to the subscribe-button / "Проверить подписку" claim-button
  work done previously in this repo.
- No changes to any other page.

## Testing

Visual-only change with no logic touched — no new automated tests.
Manually verify locally (`docker compose up`, `/tasks` in the Mini App)
that both regular and premium tabs, all task states (in-progress,
completed-unclaimed, claimed), and the reward-claimed modal all render
correctly, and run `npm run typecheck` / `npm run lint`.
