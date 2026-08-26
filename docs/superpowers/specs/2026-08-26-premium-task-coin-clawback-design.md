# Premium Task Coin Clawback — Design Spec

## Goal

Premium (channel-subscription) tasks currently check membership once, at claim time, and never again. This adds an ongoing check: if a player who claimed a premium task's coins later leaves the channel, the coins are debited back (even into a negative balance); if they rejoin, the coins are re-credited. Also retroactively assigns `reward_coins=1000` to the currently-active premium tasks that don't have a reward configured yet, and backfills that amount (with the same ongoing check) onto players who already claimed those tasks for 0 coins.

## Why membership checking can't happen per-request

`check_channel_membership` (`backend/app/services/telegram_service.py`) is a live `getChatMember` call to the Telegram Bot API — a real network round-trip (10s timeout), not a local check. Re-running it on every `GET /tasks` load, for every claimed premium task, for every player, would add real latency and risk hitting Telegram's API rate limits. Instead this follows the same "opportunistic sweep" shape this codebase already uses for Tactico's stale-round resolution (see `_auto_play_overdue_rounds`): a periodic background job, run from the bot process (which already runs jobs like this — see `bot/services/free_pack_notifier.py`, `bot/services/notifier.py` — and talks to Postgres directly per this repo's bot architecture), re-checks membership for everyone who's claimed a premium channel task and adjusts their balance on transitions.

## Data model

```python
# backend/app/models/task.py — UserTask, two new columns
reward_coins_granted: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
coins_withdrawn: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
```

- `reward_coins_granted` is a **snapshot of what this specific claim actually credited** (`0` if `game_rewards_blocked` was set, whatever `definition.reward_coins` was at the moment of claim otherwise) — never a live join to `TaskDefinition.reward_coins`, which an admin can edit later for future claimants. This is what makes the clawback amount correct even after an admin changes a task's reward value going forward. `NULL` means "claimed before this feature existed, no snapshot recorded" — used to identify rows needing the one-time backfill.
- `coins_withdrawn` tracks current state: `False` = coins currently held (or never granted), `True` = clawed back due to confirmed non-membership. The periodic job only acts on state *transitions*, never re-processes a row that's already in the correct state for its current membership.
- Stored on every claim (not just premium ones) for consistency — harmless for non-premium/non-channel tasks since the periodic job's query filters to `category=premium` with a channel set, so a regular task's snapshot is simply never read.

New `TransactionType.premium_subscription_adjustment` (Alembic `ALTER TYPE ... ADD VALUE`, same pattern used repeatedly in this codebase) — the ledger entry type for both the clawback debit and the resubscribe credit.

## Claim path change

`task_service.claim_task_reward` already computes `reward_coins = 0 if locked_user.game_rewards_blocked else definition.reward_coins` before crediting it. Add one line: `user_task.reward_coins_granted = reward_coins`, right after that computation, for every claim.

## One-time retroactive backfill

New admin-triggered endpoint, `POST /admin/tasks/backfill-premium-coins` (idempotent — safe to click more than once):

1. For every active `TaskDefinition` with `category=premium`, a channel set (`channel_username` or `channel_chat_id`), and `reward_coins == 0`: set `reward_coins = 1000`.
2. For every `UserTask` row referencing those definitions where `reward_claimed = True` and `reward_coins_granted IS NULL`: row-lock the user, credit `1000` coins (`TransactionType.premium_subscription_adjustment`, description noting this is a retroactive backfill), set `reward_coins_granted = 1000`.
3. Returns a summary: how many task definitions were updated, how many users were credited — surfaced as a confirmation toast in the admin panel (`AdminTasksPage.tsx`), reusing the same "one-off admin action with a summary result" pattern the leagues feature's retroactive reward pass already established in this codebase.

Step 2 runs inside the same request as step 1 uses the *new* `reward_coins` value it just set — both steps commit as one action, so re-running finds nothing left to do (every matching definition's `reward_coins` is now non-zero, every matching `UserTask.reward_coins_granted` is now set).

## Periodic subscription check (bot process)

New `bot/services/premium_subscription_check.py`, `run_premium_subscription_check(bot)`, following `daily_reminder.py`'s `while True: ... sleep(interval)` shape, registered in `bot/bot.py` alongside the currently-active `run_notification_dispatcher`/`run_free_pack_notifier` calls (both `run_polling` and `run_webhook`) — not alongside the currently-*disabled* `daily_reminder` job, which stays disabled; this is a different, balance-correcting job, not another player-facing nag.

Interval: every 6 hours (plain module constant, matching `daily_reminder.py`'s `CHECK_INTERVAL_SECONDS` convention — this is an ops cadence, not a game-economy number, so it doesn't belong on `GameConfig`).

Each cycle:
1. Query every `user_tasks` row joined to `task_definitions`/`users` where `reward_claimed = true`, `reward_coins_granted IS NOT NULL AND reward_coins_granted > 0`, `task_definitions.category = 'premium'`, and a channel is set.
2. For each row, call `bot.get_chat_member(chat_id, telegram_id)` (aiogram's own method — the bot process already holds a live `Bot` instance, no need for `telegram_service`'s raw `httpx` call). **On any error or ambiguous result (bot not admin, network failure, channel not found), skip the row and log a warning — never guess.** A clawback triggered by a transient API failure would incorrectly debit a real player; "skip and retry next cycle" is the only safe failure mode here, the opposite of `check_channel_membership`'s fail-closed-to-False behavior (which is fine for a claim gate, but wrong for a balance-changing sweep).
3. Member and `coins_withdrawn = True` → credit `reward_coins_granted` back, set `coins_withdrawn = False`.
4. Not a member and `coins_withdrawn = False` → debit `reward_coins_granted`, allowing the balance to go negative, set `coins_withdrawn = True`.
5. Otherwise (state already matches membership) → no-op.
6. A small `asyncio.sleep(0.05)` between `get_chat_member` calls to stay well under Telegram's rate limits across a large sweep.

Balance mutation reuses `bot/db.py`'s existing `give_coins`'s row-locked-transaction shape (`SELECT ... FOR UPDATE` then update + insert a `coin_transactions` row) as a new `adjust_coins_allow_negative(user_id, amount, description)` function — `give_coins` itself is left untouched since it's used elsewhere for admin top-ups and isn't the right place to bolt on negative-balance semantics.

## Frontend

No balance-clamping exists anywhere in the frontend (checked `ProfilePage.tsx`/`HomePage.tsx`) — a negative balance renders correctly as-is, e.g. "-450". `TX_TYPE_LABELS` (`ProfilePage.tsx`) gains an entry for `premium_subscription_adjustment` so the transaction history reads sensibly instead of falling back to the raw enum string. `AdminTasksPage.tsx` gets one new button ("Начислить монеты за старые премиум-задания" or similar) wired to the new backfill endpoint, showing its summary result.

## Testing

Backend:
- Claiming a premium task now stores `reward_coins_granted` matching what was actually credited (including the `game_rewards_blocked → 0` case).
- The backfill endpoint: sets `reward_coins=1000` on a zero-reward active premium task, credits 1000 to a user who'd already claimed it at 0, is a no-op the second time it's called, and does not touch a premium task that already has a non-zero `reward_coins`.
- `adjust_coins_allow_negative`-equivalent logic (tested at the service layer the bot's raw SQL mirrors, since the bot's `db.py` itself isn't exercised by the backend's pytest suite) allows the balance to go negative and never rejects the debit.

Manual/bot-side: the periodic job itself (real Telegram API calls, bot-process-only) is verified by manual walkthrough per this codebase's existing convention for bot-side behavior — there's no automated harness for the bot process's Telegram-facing code.
