import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { motion, useReducedMotion } from "framer-motion";
import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { buyPathAttempt, createPathStarsInvoice, fetchPathStarsInvoiceStatus, fetchPathState } from "@/api/path";
import { IconCoin } from "@/components/icons";
import PrestigeSection from "@/components/path/PrestigeSection";
import StageUpCelebration from "@/components/path/StageUpCelebration";
import TalentBlock from "@/components/path/TalentBlock";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { levelFraction, shownLevelXp, markStageSeen, pathFraction, seenStage, SOURCE_LABELS, stageIcon } from "@/lib/pathCards";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PathStage, PathState, Player } from "@/types";

async function waitForInvoice(token: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt++) {
    const status = await fetchPathStarsInvoiceStatus(token);
    if (status.status === "completed") return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

function Bar({ value, className = "" }: { value: number; className?: string }) {
  return (
    <div className={`h-2 overflow-hidden rounded-full bg-black/30 ${className}`}>
      <div className="h-full rounded-full bg-gradient-to-r from-emerald-400 to-lime-300" style={{ width: `${Math.round(value * 100)}%` }} />
    </div>
  );
}

/** One node of the road: the stage mark on the line, its name, rating band,
 * talent unlock and — for the current and future stages — its tasks. */
function StageNode({ stage, isLast, reduced }: { stage: PathStage; isLast: boolean; reduced: boolean | null }) {
  const state = stage.reached ? "done" : stage.current ? "current" : "future";
  // Future stages start collapsed: only the current one is spelled out.
  const [open, setOpen] = useState(false);
  const showTasks = state === "current" || (state === "future" && open);
  const doneTasks = stage.tasks.filter((t) => t.done).length;
  return (
    <li className="relative flex gap-3 pb-5 last:pb-0">
      {!isLast && (
        <span
          aria-hidden
          className={`absolute left-[19px] top-10 h-[calc(100%-2.5rem)] w-1 rounded-full ${
            stage.reached ? "bg-gradient-to-b from-emerald-400 to-lime-300" : "bg-white/10"
          }`}
        />
      )}
      <motion.span
        aria-hidden
        className={`relative z-10 grid h-10 w-10 shrink-0 place-items-center rounded-full text-lg ${
          state === "done"
            ? "bg-emerald-400/90"
            : state === "current"
              ? "bg-emerald-400/20 ring-2 ring-emerald-300"
              : "bg-white/5 grayscale"
        }`}
        animate={state === "current" && !reduced ? { scale: [1, 1.08, 1] } : undefined}
        transition={state === "current" && !reduced ? { duration: 2.4, repeat: Infinity } : undefined}
      >
        {stageIcon(stage.index)}
      </motion.span>
      <div className={`min-w-0 flex-1 rounded-2xl p-3 ${state === "current" ? "border border-emerald-400/30 bg-emerald-400/5" : "bg-white/5"}`}>
        <div className="flex items-baseline justify-between gap-2">
          <p className={`font-display text-sm font-bold ${state === "future" ? "text-ink-mist" : "text-ink-chalk"}`}>{stage.name}</p>
          <p className="font-mono text-caption text-ink-mist">
            {stage.min_rating}–{stage.max_rating}
          </p>
        </div>
        <p className="mt-0.5 text-caption text-ink-mist">
          {state === "done" ? "Пройден ✓" : state === "current" ? "Ты здесь" : "Впереди"}
          {stage.talent_level > 0 && (
            <span className="ml-1.5 text-path">· талант {stage.talent_level === 2 ? "II" : "I"}</span>
          )}
        </p>
        {state === "future" && stage.tasks.length > 0 && (
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            aria-expanded={open}
            className="mt-1 min-h-[32px] text-caption font-semibold text-ink-mist underline-offset-2 hover:underline"
          >
            {open ? "Скрыть задания" : `Задания этапа · ${stage.tasks.length}`}
          </button>
        )}
        {showTasks && stage.tasks.length > 0 && (
          <div className="mt-2">
            <p className="text-micro font-semibold uppercase tracking-wider text-ink-mist-dim">
              Задания для перехода дальше · {doneTasks}/{stage.tasks.length}
            </p>
            <ul className="mt-1 space-y-1.5">
              {stage.tasks.map((task) => (
                <li key={task.id} className={state === "future" ? "opacity-60" : ""}>
                  <div className="flex items-center justify-between gap-2 text-xs">
                    <span className={task.done ? "text-path" : "text-ink-chalk"}>
                      {task.done ? "✓ " : ""}
                      {task.label}
                      {!task.applies && <span className="text-ink-mist-dim"> — не для его позиции</span>}
                    </span>
                    <span className="font-mono text-ink-mist">
                      {task.applies ? `${task.progress}/${task.target}` : "—"}
                    </span>
                  </div>
                  {task.applies && <Bar value={task.target ? task.progress / task.target : 1} className="mt-1 h-1.5" />}
                </li>
              ))}
            </ul>
          </div>
        )}
        {state !== "done" && stage.tasks.length === 0 && !isLast && (
          <p className="mt-1 text-caption text-ink-mist-dim">Без заданий — только опыт</p>
        )}
      </div>
    </li>
  );
}

/** «Сегодня»: what can be done right now — attempts left and the closest
 * unfinished task of the current stage — with one button to go and play. */
function TodayBlock({ state, onPlay }: { state: PathState; onPlay: () => void }) {
  const current = state.stages.find((s) => s.current);
  const next = current?.tasks
    .filter((t) => t.applies && !t.done)
    .sort((a, b) => (a.target - a.progress) / a.target - (b.target - b.progress) / b.target)[0];
  const attempts = state.daily.arena_free_left + state.daily.bought_attempts;
  return (
    <section className="rounded-2xl border border-path/30 bg-path/5 p-3" aria-label="Сегодня">
      <h3 className="text-xs font-semibold uppercase tracking-wider text-path">Сегодня</h3>
      <div className="mt-2 grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-black/20 py-1.5">
          <p className="font-mono text-base font-bold text-ink-chalk">{attempts}</p>
          <p className="text-micro text-ink-mist">попыток Арены</p>
        </div>
        <div className="rounded-xl bg-black/20 py-1.5">
          <p className="font-mono text-base font-bold text-ink-chalk">{state.daily.ptour_left}</p>
          <p className="text-micro text-ink-mist">матчей турнира</p>
        </div>
        <div className="rounded-xl bg-black/20 py-1.5">
          <p className="font-mono text-base font-bold text-ink-chalk">{state.daily.career_left}</p>
          <p className="text-micro text-ink-mist">туров карьеры</p>
        </div>
      </div>
      {next && (
        <p className="mt-2 text-xs text-ink-chalk">
          Ближайшее задание: <b>{next.label}</b> — ещё {next.target - next.progress}
        </p>
      )}
      <button
        type="button"
        onClick={onPlay}
        disabled={!state.enabled || attempts <= 0}
        className="mt-2 min-h-[44px] w-full rounded-xl bg-floodlight text-sm font-bold text-bg-base disabled:opacity-40"
      >
        {attempts > 0 ? "Играть в Card Arena" : "Попытки Арены на сегодня закончились"}
      </button>
    </section>
  );
}

/** «Путь» screen of one «Академия» card: header with the level bar, the
 * road of stages with their tasks, the talent, today's attempts (with
 * purchases) and how experience is earned. Full-screen sheet, mobile-first. */
export default function PathSheet({ cardId, player, onClose }: { cardId: number; player: Player; onClose: () => void }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const reduced = useReducedMotion();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const [error, setError] = useState<string | null>(null);
  const [celebrate, setCelebrate] = useState<{ index: number; name: string; talent?: string | null } | null>(null);
  const { data: state, isLoading } = useQuery({ queryKey: ["path", cardId], queryFn: () => fetchPathState(cardId) });

  // A stage reached since the player last looked: celebrate it once.
  useEffect(() => {
    if (!state) return;
    const seen = seenStage(cardId);
    if (seen == null) {
      markStageSeen(cardId, state.stage);
      return;
    }
    if (state.stage > seen) {
      const reachedStage = state.stages.find((s) => s.index === state.stage);
      const unlocks = reachedStage && reachedStage.talent_level > 0 && state.talent
        ? `Талант открыт: ${state.talent.emoji} ${state.talent.name} ${reachedStage.talent_level === 2 ? "II" : "I"}`
        : null;
      setCelebrate({ index: state.stage, name: state.stage_name, talent: unlocks });
      markStageSeen(cardId, state.stage);
    }
  }, [cardId, state]);

  const afterPurchase = (next: PathState) => {
    hapticNotify("success");
    setError(null);
    queryClient.setQueryData(["path", cardId], next);
  };
  const coinMutation = useMutation({
    mutationFn: () => buyPathAttempt(cardId, crypto.randomUUID()),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      afterPurchase(data);
    },
    onError: (err) => {
      hapticNotify("error");
      setError(formatGameError(err, "Не удалось купить попытку"));
    },
  });
  const starsMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createPathStarsInvoice(cardId);
      const status = await openTelegramInvoice(invoice.invoice_link);
      if (status === "cancelled") return null;
      if (status === "failed") throw new Error("Платёж не прошёл");
      await waitForInvoice(invoice.payload_token);
      return fetchPathState(cardId);
    },
    onSuccess: (data) => data && afterPurchase(data),
    onError: (err) => {
      hapticNotify("error");
      setError(formatGameError(err, "Не удалось оплатить"));
    },
  });

  const image = staticUrl(player.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp");

  return (
    <div className="fixed inset-0 z-[60] flex flex-col bg-bg-base" role="dialog" aria-modal="true" aria-label="Путь карточки">
      <header className="flex items-center gap-3 border-b border-white/10 bg-bg-surface/95 px-4 pb-3 pt-[calc(0.75rem+env(safe-area-inset-top))]">
        <button type="button" onClick={onClose} className="rounded-xl bg-white/5 px-3 py-1.5 text-sm font-semibold text-ink-mist">
          ← Назад
        </button>
        <p className="font-display text-base font-bold text-ink-chalk">{state?.title ?? "Академия"}</p>
      </header>

      <div className="flex-1 overflow-y-auto overscroll-contain px-4 pb-[calc(1.5rem+env(safe-area-inset-bottom))] pt-4">
        {isLoading || !state ? (
          <div className="space-y-3" aria-busy>
            <div className="h-28 animate-pulse rounded-2xl bg-white/5" />
            <div className="h-64 animate-pulse rounded-2xl bg-white/5" />
          </div>
        ) : (
          <div className="mx-auto max-w-md space-y-4">
            <section
              className={`rounded-3xl bg-gradient-to-br p-[2px] ${
                state.is_legend ? "from-amber-200 via-lime-200 to-amber-400" : "from-emerald-300 via-lime-200 to-cyan-300"
              }`}
            >
              <div className="flex gap-3 rounded-[22px] bg-bg-surface p-3">
                <img decoding="async" loading="lazy" src={image} alt={player.display_name} className="h-20 w-16 shrink-0 rounded-xl object-cover" />
                <div className="min-w-0 flex-1">
                  <p className="truncate font-display text-sm font-bold text-ink-chalk">{state.player_name}</p>
                  <p className="text-xs text-ink-mist">
                    {stageIcon(state.stage)} {state.stage_name} · уровень {state.level}/{state.max_level}
                  </p>
                  <p className="mt-1 flex items-baseline gap-1.5">
                    <span className="font-display text-2xl font-bold text-path">{state.rating}</span>
                    <span className="text-xs text-ink-mist">из {state.ceiling}</span>
                  </p>
                  <Bar value={pathFraction(state)} className="mt-1" />
                </div>
              </div>
              <div className="rounded-b-[22px] bg-bg-surface px-3 pb-3">
                {state.xp_for_next ? (
                  <>
                    <div className="flex justify-between text-caption text-ink-mist">
                      <span>Опыт до {state.rating + 1}</span>
                      <span className="font-mono">{shownLevelXp(state)}/{state.xp_for_next}</span>
                    </div>
                    <Bar value={levelFraction(state)} className="mt-1" />
                    {state.blocked_by_tasks && (
                      <p className="mt-1.5 rounded-lg bg-amber-400/10 px-2 py-1 text-caption text-legend">
                        Опыта хватает — выполни задания этапа, чтобы расти дальше
                      </p>
                    )}
                  </>
                ) : (
                  <p className="text-center text-xs font-semibold text-legend">Путь пройден до конца 👑</p>
                )}
              </div>
            </section>

            {!state.enabled && (
              <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">
                Механика сейчас выключена: опыт не начисляется, полученные уровни остаются.
              </p>
            )}

            <TodayBlock state={state} onPlay={() => { onClose(); navigate("/play/arena"); }} />

            <section aria-label="Этапы пути">
              <h3 className="mb-2 text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Путь</h3>
              <ol>
                {state.stages.map((stage, i) => (
                  <StageNode key={stage.index} stage={stage} isLast={i === state.stages.length - 1} reduced={reduced} />
                ))}
              </ol>
            </section>

            {state.talent && <TalentBlock talent={state.talent} />}

            {state.prestige && state.prestige.max_tier > 0 && (
              <PrestigeSection cardId={cardId} prestige={state.prestige} title={state.title} />
            )}

            <section className="rounded-2xl bg-white/5 p-3" aria-label="Попытки на сегодня">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Опыт сегодня</h3>
              <ul className="mt-2 space-y-1 text-xs">
                <li className="flex justify-between">
                  <span className="text-ink-mist">Card Arena, бесплатно</span>
                  <b className="font-mono text-ink-chalk">{state.daily.arena_free_left}/{state.daily.arena_free_total}</b>
                </li>
                <li className="flex justify-between">
                  <span className="text-ink-mist">Купленные попытки (не сгорают)</span>
                  <b className="font-mono text-ink-chalk">{state.daily.bought_attempts}</b>
                </li>
                <li className="flex justify-between">
                  <span className="text-ink-mist">Турнир игроков</span>
                  <b className="font-mono text-ink-chalk">{state.daily.ptour_left}/{state.daily.ptour_total}</b>
                </li>
                <li className="flex justify-between">
                  <span className="text-ink-mist">Карьера тренера</span>
                  <b className="font-mono text-ink-chalk">{state.daily.career_left}/{state.daily.career_total}</b>
                </li>
              </ul>
              <div className="mt-3 grid grid-cols-2 gap-2">
                <button
                  type="button"
                  disabled={!state.enabled || state.daily.next_coin_price == null || coinMutation.isPending || balance < (state.daily.next_coin_price ?? 0)}
                  onClick={() => coinMutation.mutate()}
                  className="flex flex-col items-center rounded-xl bg-bg-raised py-2 text-xs font-semibold text-ink-chalk disabled:opacity-40"
                >
                  <span>+1 попытка</span>
                  <span className="mt-0.5 flex items-center gap-1 text-accent-lime">
                    {state.daily.next_coin_price != null ? (
                      <>
                        <IconCoin size={12} /> {state.daily.next_coin_price}
                      </>
                    ) : (
                      "лимит на сегодня"
                    )}
                  </span>
                  <span className="text-micro font-normal text-ink-mist-dim">осталось {state.daily.coin_buys_left}</span>
                </button>
                <button
                  type="button"
                  disabled={!state.enabled || state.daily.next_stars_price == null || starsMutation.isPending}
                  onClick={() => starsMutation.mutate()}
                  className="flex flex-col items-center rounded-xl bg-bg-raised py-2 text-xs font-semibold text-ink-chalk disabled:opacity-40"
                >
                  <span>+1 попытка</span>
                  <span className="mt-0.5 text-legend">
                    {state.daily.next_stars_price != null ? `⭐ ${state.daily.next_stars_price}` : "лимит на сегодня"}
                  </span>
                  <span className="text-micro font-normal text-ink-mist-dim">осталось {state.daily.stars_buys_left}</span>
                </button>
              </div>
              {error && <p className="mt-2 rounded-lg bg-red-500/10 px-2 py-1 text-xs text-red-400">{error}</p>}
              {state.academy && (state.academy.xp_pct > 0 || state.academy.attempts > 0 || state.academy.task_cut_pct > 0) && (
                <p className="mt-2 rounded-lg bg-path/10 px-2 py-1 text-caption text-path">
                  🏫 Бонусы здания Академии: +{state.academy.xp_pct}% опыта · +{state.academy.attempts} попыт. · задания −{state.academy.task_cut_pct}%
                </p>
              )}
              <p className="mt-2 text-micro text-ink-mist-dim">
                Опыт идёт только за наградные матчи с этой карточкой в составе. Попытки Card Arena тратятся сначала бесплатные,
                потом купленные; турнир игроков и карьера попытки не тратят.
              </p>
            </section>

            <section className="rounded-2xl bg-white/5 p-3" aria-label="Как получать опыт">
              <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Опыт за матч</h3>
              <div className="mt-2 grid grid-cols-5 gap-1 text-center">
                {[
                  ["Матч", state.xp_rules.match],
                  ["Победа", state.xp_rules.win],
                  ["Ничья", state.xp_rules.draw],
                  ["Гол", state.xp_rules.goal],
                  ["Пас", state.xp_rules.assist],
                ].map(([label, value]) => (
                  <div key={label} className="rounded-lg bg-black/20 py-1.5">
                    <p className="font-mono text-sm font-bold text-path">+{value}</p>
                    <p className="text-micro text-ink-mist">{label}</p>
                  </div>
                ))}
              </div>
            </section>

            {state.recent.length > 0 && (
              <section className="rounded-2xl bg-white/5 p-3" aria-label="Последние матчи">
                <h3 className="text-xs font-semibold uppercase tracking-wider text-ink-mist-dim">Последние матчи</h3>
                <ul className="mt-2 divide-y divide-white/5">
                  {state.recent.map((item, i) => (
                    <li key={i} className="flex items-center justify-between py-1.5 text-xs">
                      <span className="text-ink-mist">
                        {SOURCE_LABELS[item.source_type] ?? item.source_type}
                        {item.result && <> · {item.result === "win" ? "победа" : item.result === "draw" ? "ничья" : "поражение"}</>}
                        {item.goals > 0 && <> · ⚽{item.goals}</>}
                        {item.assists > 0 && <> · 🅰️{item.assists}</>}
                        {item.stages.length > 0 && <span className="text-path"> · новый этап!</span>}
                      </span>
                      <b className="font-mono text-path">+{item.xp}</b>
                    </li>
                  ))}
                </ul>
              </section>
            )}
          </div>
        )}
      </div>

      <StageUpCelebration
        open={celebrate != null}
        stageIndex={celebrate?.index ?? 0}
        stageName={celebrate?.name ?? ""}
        talentText={celebrate?.talent}
        onClose={() => setCelebrate(null)}
      />
    </div>
  );
}
