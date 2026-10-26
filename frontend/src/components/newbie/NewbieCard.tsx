import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimNewbieStep, fetchNewbie, openNewbieFirstPack, openNewbieSquadPack } from "@/api/newbie";
import { IconCheck, IconCoin, IconGift, IconLock, IconPack, IconPlay, IconStadium, IconTrophy, IconUsers, type IconProps } from "@/components/icons";
import NewbiePopup from "@/components/newbie/NewbiePopup";
import { RewardBundleChips } from "@/components/rewards/RewardBundleView";
import { isEmptyBundle } from "@/lib/rewards";
import { formatGameError } from "@/lib/errors";
import { RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { GrantedRewards, NewbieState, PackOpenResult } from "@/types";

/** «Путь дебютанта» on home: the next big step (team pack → first Arena
 * match → its card), «попробуй режим» tasks and the day-2 / day-3 gifts.
 * Gone once everything is claimed. */
export default function NewbieCard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: state } = useQuery({ queryKey: ["newbie"], queryFn: fetchNewbie });
  const [note, setNote] = useState<string | null>(null);

  const openPack = useMutation({
    mutationFn: (which: "first" | "squad") => (which === "first" ? openNewbieFirstPack() : openNewbieSquadPack()),
    onSuccess: (data: PackOpenResult) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["newbie"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      queryClient.invalidateQueries({ queryKey: ["lineup"] });
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data, returnTo: "/" } });
    },
  });
  const claim = useMutation({
    mutationFn: claimNewbieStep,
    onSuccess: (data) => {
      updateBalance(data.rewards.new_balance);
      hapticNotify("success");
      queryClient.setQueryData(["newbie"], data.state);
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      setNote(describe(data.rewards));
      if (data.rewards && !data.state.active) setFinished(data.rewards);
    },
  });
  const [finished, setFinished] = useState<GrantedRewards | null>(null);
  const busy = openPack.isPending || claim.isPending;
  const error = openPack.error ?? claim.error;

  if (finished) {
    return (
      <NewbiePopup
        open
        Icon={IconTrophy}
        kicker="Путь пройден!"
        title="Ты больше не дебютант — ты игрок VICTOR FC"
        text={<>{describe(finished)}. Дальше — свободная игра: турниры, клубы, Арена и коллекция.</>}
        cta="Играть дальше"
        onCta={() => setFinished(null)}
      />
    );
  }
  if (!state?.active) return null;
  const pct = state.steps_total ? Math.round((state.steps_done / state.steps_total) * 100) : 0;

  return (
    <section data-newbie className="rounded-3xl bg-bg-surface p-3 ring-1 ring-accent-lime/20">
      <div className="mb-2.5 px-1">
        <div className="flex items-center justify-between gap-2">
          <h2 className="font-display text-base font-bold text-ink-chalk">Путь дебютанта</h2>
          <span className="font-mono text-xs font-bold text-accent-lime tabular-nums">
            {state.steps_done}/{state.steps_total}
          </span>
        </div>
        <div className="mt-1.5 h-1.5 overflow-hidden rounded-full bg-white/10">
          <div className="h-full rounded-full bg-accent-lime transition-all" style={{ width: `${pct}%` }} />
        </div>
      </div>

      {state.finale_ready && (
        <div className="mb-2 flex flex-col items-center gap-2 rounded-2xl bg-accent-lime/10 p-4 text-center ring-1 ring-accent-lime/30">
          <IconTrophy size={30} className="text-accent-lime" />
          <p className="font-display text-lg font-bold text-ink-chalk">Все шаги пройдены!</p>
          {state.finale && !isEmptyBundle(state.finale) && <RewardBundleChips bundle={state.finale} />}
          <button
            onClick={() => claim.mutate("finale")}
            disabled={busy}
            className="animate-claim-glow mt-1 w-full rounded-2xl bg-floodlight py-3 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-60"
          >
            {claim.isPending ? "..." : "Забрать награду"}
          </button>
        </div>
      )}

      <MainStep
        state={state}
        busy={busy}
        onFirst={() => openPack.mutate("first")}
        onSquad={() => openPack.mutate("squad")}
        onArena={() => navigate("/play/arena")}
        onTask={(code, played, path) => (played ? claim.mutate(`task:${code}`) : navigate(path, { state: { fromNewbie: true } }))}
      />

      {(note || error) && (
        <p role="status" className={`mt-2 px-1 text-xs ${error ? "text-red-400" : "text-accent-lime"}`}>
          {error ? formatGameError(error, "Не получилось") : note}
        </p>
      )}

      {state.tasks.length > 0 && (
        <>
          <p className="mb-1.5 mt-3 px-1 text-xs font-semibold text-ink-mist">Попробуй режимы — награда сразу</p>
          <div className="grid grid-cols-2 gap-1.5">
            {state.tasks.map((t) => {
              const ready = t.played && !t.claimed;
              return (
                <button
                  key={t.code}
                  disabled={t.claimed || (ready && busy)}
                  onClick={() => {
                    haptic("light");
                    if (ready) claim.mutate(`task:${t.code}`);
                    else navigate(t.path, { state: { fromNewbie: true } });
                  }}
                  className={`flex min-w-0 flex-col items-start gap-0.5 rounded-2xl px-2.5 py-2 text-left active:scale-95 ${
                    ready ? "bg-accent-lime/10 ring-1 ring-accent-lime/30" : t.claimed ? "bg-bg-raised/40 opacity-60" : "bg-bg-raised/60"
                  }`}
                >
                  <span className="line-clamp-2 text-caption font-semibold leading-tight text-ink-chalk">{t.label}</span>
                  <span className={`flex items-center gap-1 text-micro ${ready ? "font-bold text-accent-lime" : "text-ink-mist"}`}>
                    {t.claimed ? (
                      <>
                        <IconCheck size={11} /> Получено
                      </>
                    ) : (
                      <>
                        {ready ? "Забрать" : "Играть"} · <IconCoin size={11} className="text-accent-lime" />
                        {t.coins.toLocaleString("ru-RU")}
                        {t.pack_name ? ` + пак` : ""}
                      </>
                    )}
                  </span>
                </button>
              );
            })}
          </div>
        </>
      )}

      <div className="mt-3 grid grid-cols-2 gap-1.5">
        {state.gifts.map((g) => {
          const ready = g.ready && !g.claimed;
          const what = g.card_rarity ? `${RARITY_LABELS[g.card_rarity]} карта` : `${g.coins.toLocaleString("ru-RU")} монет`;
          return (
            <button
              key={g.day}
              disabled={!ready || busy}
              onClick={() => claim.mutate(`day${g.day}`)}
              className={`flex min-w-0 items-center gap-2 rounded-2xl px-2.5 py-2 text-left ${
                ready ? "animate-claim-glow bg-accent-lime/10 ring-1 ring-accent-lime/30 active:scale-95" : "bg-bg-raised/60"
              } ${g.claimed ? "opacity-60" : ""}`}
            >
              <span className={ready ? "text-accent-lime" : "text-ink-mist"}>
                {g.claimed ? <IconCheck size={18} /> : g.ready ? <IconGift size={18} /> : <IconLock size={18} />}
              </span>
              <span className="min-w-0">
                <span className="block text-micro text-ink-mist">День {g.day}</span>
                <span className={`block truncate text-caption font-bold ${g.card_rarity ? RARITY_TEXT[g.card_rarity] : "text-ink-chalk"}`}>
                  {what}
                </span>
                <span className={`block text-micro ${ready ? "font-bold text-accent-lime" : "text-ink-mist"}`}>
                  {g.claimed ? "Получено" : ready ? "Забрать" : g.day - state.day === 1 ? "Завтра" : `Через ${g.day - state.day} дн.`}
                </span>
              </span>
            </button>
          );
        })}
      </div>

      {state.bound_days > 0 && (
        <p className="mt-2 px-1 text-micro leading-snug text-ink-mist-dim">
          Подарочные карты — твои: ими можно играть сразу, а продать или обменять — через {state.bound_days} дн.
        </p>
      )}
    </section>
  );
}

function MainStep({
  state, busy, onFirst, onSquad, onArena, onTask,
}: {
  state: NewbieState;
  busy: boolean;
  onFirst: () => void;
  onSquad: () => void;
  onArena: () => void;
  onTask: (code: string, played: boolean, path: string) => void;
}) {
  const rarity = state.arena_rarity;
  const reward = rarity ? (
    <span className={`font-bold ${RARITY_TEXT[rarity]}`}>{RARITY_LABELS[rarity].toLowerCase()} карта</span>
  ) : null;
  if (!state.first_pack_done) {
    return <Step Icon={IconPack} step={1} title="Открой «Пак дебютанта»" text="Первые карты в коллекцию" cta="Открыть" onClick={onFirst} busy={busy} />;
  }
  if (!state.squad_pack_done) {
    return (
      <Step
        Icon={IconUsers}
        step={2}
        title="Получи свою команду"
        text={`${state.squad_size} игроков на все позиции — состав соберётся сам`}
        cta="Получить"
        onClick={onSquad}
        busy={busy}
      />
    );
  }
  if (!state.arena_claimed) {
    return state.arena_played ? (
      <Step Icon={IconGift} step={3} title="Первый матч сыгран!" text={<>Награда ждёт в Арене: {reward}</>} cta="Забрать" onClick={onArena} busy={busy} glow />
    ) : (
      <Step Icon={IconStadium} step={3} title="Сыграй матч в Card Arena" text={<>Твоя команда готова. Награда: {reward}</>} cta="Играть" onClick={onArena} busy={false} />
    );
  }
  // Then the «попробуй режим» tasks one by one.
  const next = state.tasks.find((t) => !t.claimed);
  if (!next) return null;
  const n = state.tasks.indexOf(next) + 4;
  return (
    <Step
      Icon={next.played ? IconGift : IconPlay}
      step={n}
      title={next.played ? `Готово: ${next.label}` : next.label}
      text={<>Награда сразу: {next.coins.toLocaleString("ru-RU")} монет{next.pack_name ? " + пак" : ""}</>}
      cta={next.played ? "Забрать" : "Играть"}
      onClick={() => onTask(next.code, next.played, next.path)}
      busy={busy}
      glow={next.played}
    />
  );
}

function Step({
  Icon, step, title, text, cta, onClick, busy, glow,
}: {
  Icon: (props: IconProps) => JSX.Element;
  step: number;
  title: string;
  text: React.ReactNode;
  cta: string;
  onClick: () => void;
  busy: boolean;
  glow?: boolean;
}) {
  return (
    <div className="flex items-center gap-3 rounded-2xl bg-accent-lime/10 p-2.5 ring-1 ring-accent-lime/30">
      <span className="relative flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-bg-base text-accent-lime">
        <Icon size={22} />
        <span className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-accent-lime font-mono text-micro font-bold text-bg-base">
          {step}
        </span>
      </span>
      <div className="min-w-0 flex-1">
        <p className="text-sm font-bold leading-tight text-ink-chalk">{title}</p>
        <p className="text-micro leading-snug text-ink-mist">{text}</p>
      </div>
      <button
        onClick={() => {
          haptic("medium");
          onClick();
        }}
        disabled={busy}
        className={`shrink-0 rounded-full bg-floodlight px-3.5 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-60 ${
          glow ? "animate-claim-glow" : ""
        }`}
      >
        {busy ? "..." : cta}
      </button>
    </div>
  );
}

function describe(r: GrantedRewards): string {
  const parts: string[] = [];
  if (r.coins) parts.push(`+${r.coins.toLocaleString("ru-RU")} монет`);
  if (r.badge) parts.push(`значок «${r.badge.name}»`);
  if (r.pack_name) parts.push(`пак «${r.pack_name}»`);
  for (const c of r.cards) parts.push(`${c.player.display_name} (${RARITY_LABELS[c.player.rarity].toLowerCase()})`);
  return parts.length ? `Получено: ${parts.join(", ")}` : "Получено";
}
