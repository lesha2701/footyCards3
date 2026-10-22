import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchCosmetics } from "@/api/monetization";
import { fetchMyProfile } from "@/api/profile";
import {
  acceptMordoboiChallenge,
  applyMordoboiBrutality,
  cancelMordoboiChallenge,
  createMordoboiBotMatch,
  createMordoboiChallenge,
  declineMordoboiChallenge,
  fetchMordoboiMatch,
  forfeitMordoboiMatch,
  pickMordoboiAction,
} from "@/api/mordoboi";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import ErrorScreen from "@/components/common/ErrorScreen";
import LoadingScreen from "@/components/common/LoadingScreen";
import ShareButton from "@/components/common/ShareButton";
import { IconChevronLeft, IconCoin } from "@/components/icons";
import BoxingRing from "@/components/mordoboi/BoxingRing";
import BrutalityShow from "@/components/mordoboi/BrutalityShow";
import { ACTION_META, ACTION_ORDER, WIN_REASON_LABELS, describeExchange } from "@/components/mordoboi/mordoboiMeta";
import { formatGameError } from "@/lib/errors";
import { staticUrl } from "@/lib/api";
import { BRUTALITY_EMOJI } from "@/lib/cosmetics";
import { haptic, hapticNotify, openTelegramLink } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { MordoboiAction, MordoboiExchange, MordoboiMatch } from "@/types";

const RESULT_TITLES: Record<string, string> = { win: "Победа!", draw: "Ничья", loss: "Поражение" };
const OPPONENT_LABELS: Record<string, string> = { bot: "Бот", friend: "Друг", online: "Онлайн", chat: "Вызов из чата" };
// Beaten side: the finisher scene is shown once per bout on this device.
const SEEN_BRUTALITY_KEY = "mordoboi.seenBrutality";

function brutalitySeen(id: number): boolean {
  try {
    return (localStorage.getItem(SEEN_BRUTALITY_KEY) ?? "").split(",").includes(String(id));
  } catch {
    return true;
  }
}

function markBrutalitySeen(id: number): void {
  try {
    const ids = (localStorage.getItem(SEEN_BRUTALITY_KEY) ?? "").split(",").filter(Boolean).slice(-50);
    localStorage.setItem(SEEN_BRUTALITY_KEY, [...ids, String(id)].join(","));
  } catch {
    // storage unavailable — the scene may show again, harmless
  }
}

export default function MordoboiMatchPage() {
  const { matchId } = useParams();
  const id = Number(matchId);
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [error, setError] = useState<string | null>(null);
  const [hit, setHit] = useState<MordoboiExchange | null>(null);
  const [showResult, setShowResult] = useState(false);
  const [confirmForfeit, setConfirmForfeit] = useState(false);
  const [brutalityPicker, setBrutalityPicker] = useState(false);
  const [brutalityOpen, setBrutalityOpen] = useState(false);
  const seenN = useRef<number | null>(null);
  const seenStatus = useRef<string | null>(null);

  const { data: match, isLoading, isError } = useQuery({
    queryKey: ["mordoboi-match", id],
    queryFn: () => fetchMordoboiMatch(id),
    // Polling while waiting on the other side also keeps the server's lazy
    // deadline sweep running (see mordoboi_service._sweep).
    refetchInterval: (q) => {
      const m = q.state.data as MordoboiMatch | undefined;
      if (!m) return false;
      if (m.status === "pending_accept") return 5000;
      if (m.status !== "in_progress" || m.can_pick) return false;
      return m.live ? 1500 : 4000;
    },
  });

  // Animate exchanges we haven't shown yet; open the result when the bout ends here.
  useEffect(() => {
    if (!match) return;
    const lastN = match.log.length ? match.log[match.log.length - 1].n : 0;
    if (seenN.current === null) {
      seenN.current = lastN;
      seenStatus.current = match.status;
      if (match.status === "finished") setShowResult(true);
      return;
    }
    if (lastN > seenN.current) {
      const latest = match.log[match.log.length - 1];
      setHit(latest);
      if (latest.opponent_damage > latest.my_damage) hapticNotify("error");
      else haptic(latest.my_damage > 0 ? "heavy" : "light");
      seenN.current = lastN;
    }
    if (seenStatus.current !== "finished" && match.status === "finished") {
      const t = setTimeout(() => setShowResult(true), 900);
      hapticNotify(match.result === "win" ? "success" : match.result === "loss" ? "error" : "warning");
      seenStatus.current = match.status;
      return () => clearTimeout(t);
    }
    seenStatus.current = match.status;
  }, [match]);

  // The beaten side sees the finisher once, whenever they open the bout.
  useEffect(() => {
    if (match?.brutality && !match.brutality.by_me && !brutalitySeen(match.id)) {
      markBrutalitySeen(match.id);
      setShowResult(false);
      setBrutalityOpen(true);
      hapticNotify("error");
    }
  }, [match?.brutality, match?.id]);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: cosmetics } = useQuery({
    queryKey: ["cosmetics"], queryFn: fetchCosmetics, enabled: !!match?.can_brutality,
  });
  const ownedBrutalities = (cosmetics?.items ?? []).filter((c) => c.kind === "brutality" && c.owned);

  useEffect(() => {
    if (!hit) return;
    const t = setTimeout(() => setHit(null), 1600);
    return () => clearTimeout(t);
  }, [hit]);

  const updateBalance = useAuthStore((s) => s.updateBalance);
  const setMatch = (m: MordoboiMatch) => {
    queryClient.setQueryData(["mordoboi-match", id], m);
    queryClient.invalidateQueries({ queryKey: ["mordoboi-matches"] });
    if (m.status === "finished") {
      // Rewards, stakes and the finisher bonus land in the wallet: refresh the header.
      fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
      queryClient.invalidateQueries({ queryKey: ["mordoboi-info"] });
      queryClient.invalidateQueries({ queryKey: ["mordoboi-stats"] });
    }
  };
  const pick = useMutation({
    mutationFn: ({ action, version }: { action: MordoboiAction; version: number }) => pickMordoboiAction(id, action, version),
    onSuccess: (m) => { setError(null); setMatch(m); },
    onError: (err) => {
      hapticNotify("error");
      setError(formatGameError(err, "Удар не принят"));
      queryClient.invalidateQueries({ queryKey: ["mordoboi-match", id] });
    },
  });
  const action = useMutation({
    mutationFn: (kind: "accept" | "decline" | "cancel" | "forfeit") =>
      ({ accept: acceptMordoboiChallenge, decline: declineMordoboiChallenge, cancel: cancelMordoboiChallenge, forfeit: forfeitMordoboiMatch })[kind](id),
    onSuccess: (m) => { setError(null); setMatch(m); queryClient.invalidateQueries({ queryKey: ["game-limits"] }); },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const finish = useMutation({
    mutationFn: (cosmeticId: number) => applyMordoboiBrutality(id, cosmeticId),
    onSuccess: (m) => {
      setMatch(m);
      setBrutalityPicker(false);
      setShowResult(false);
      setBrutalityOpen(true);
      hapticNotify("success");
    },
    onError: (err) => setError(formatGameError(err, "Не получилось")),
  });
  const rematch = useMutation({
    mutationFn: (m: MordoboiMatch) =>
      m.opponent_type === "friend" && m.opponent_user_id
        ? createMordoboiChallenge(m.opponent_user_id)
        : createMordoboiBotMatch(m.difficulty === "easy" ? "easy" : "hard"),
    onSuccess: (m) => {
      setShowResult(false);
      seenN.current = null;
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/mordoboi/matches/${m.id}`, { replace: true });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });

  if (isLoading) return <LoadingScreen />;
  if (isError || !match || !match.me) return <ErrorScreen message="Бой не найден" />;

  const inPlay = match.status === "in_progress";
  const pending = match.status === "pending_accept";
  const totals = match.scorecards.reduce((a, c) => ({ mine: a.mine + c.mine, opponent: a.opponent + c.opponent }), { mine: 0, opponent: 0 });
  const recent = [...match.log].reverse().slice(0, 6);

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center justify-between">
        <button onClick={() => navigate("/play/mordoboi")} className="flex items-center gap-1 text-xs text-ink-mist active:scale-95">
          <IconChevronLeft size={16} />
          Мордобой
        </button>
        <span className="rounded-full bg-white/5 px-2.5 py-1 text-micro font-semibold text-ink-mist">
          {OPPONENT_LABELS[match.opponent_type]}
          {match.difficulty === "easy" ? " · лёгкий" : ""} · {match.opponent_name || "ждём соперника"}
          {match.stake_coins > 0 ? ` · ставка ${match.stake_coins}` : ""}
        </span>
      </div>

      <div className="flex items-center justify-between">
        <h1 className="font-display text-lg font-bold text-ink-chalk">
          {inPlay ? `Раунд ${match.round} из ${match.rounds}` : pending ? "Вызов" : "Бой окончен"}
        </h1>
        {inPlay && (
          <div className="flex gap-1" aria-label={`Обмен ${match.exchange} из ${match.exchanges_per_round}`}>
            {Array.from({ length: match.exchanges_per_round }, (_, i) => (
              <span key={i} className={`h-2 w-5 rounded-full ${i < match.exchange - 1 ? "bg-yellow-400" : i === match.exchange - 1 ? "bg-yellow-400/50" : "bg-white/10"}`} />
            ))}
          </div>
        )}
      </div>

      <BoxingRing me={match.me} opponent={match.opponent} hit={hit} />

      {match.scorecards.length > 0 && (
        <div className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-2 text-xs text-ink-mist">
          <span>Судьи</span>
          <span className="flex gap-2 font-mono">
            {match.scorecards.map((c, i) => (
              <span key={i} className="rounded bg-white/5 px-1.5">{c.mine}:{c.opponent}</span>
            ))}
            <span className="font-bold text-ink-chalk">= {totals.mine}:{totals.opponent}</span>
          </span>
        </div>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {pending && (
        match.viewer_side === "opponent" ? (
          <div className="flex gap-2">
            <button onClick={() => action.mutate("accept")} disabled={action.isPending} className="flex-1 rounded-2xl bg-yellow-500 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50">
              Выйти на ринг
            </button>
            <button onClick={() => action.mutate("decline")} disabled={action.isPending} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
              Отказаться
            </button>
          </div>
        ) : (
          <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 text-center">
            <p className="text-sm text-ink-chalk">
              {match.opponent_type === "chat" ? "Ждём, кто из чата примет вызов…" : `Ждём, когда ${match.opponent_name} примет вызов…`}
            </p>
            {match.opponent_type === "chat" && profile?.telegram_bot_username && (
              <button
                onClick={() => {
                  const link = `https://t.me/${profile.telegram_bot_username}?start=mordoboi_open_${match.id}`;
                  const text = match.stake_coins > 0 ? `🥊 Вызываю на «Мордобой»! Ставка: ${match.stake_coins} монет` : "🥊 Вызываю на «Мордобой»!";
                  openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`);
                }}
                className="rounded-xl bg-[#2AABEE] py-2.5 text-sm font-semibold text-white active:scale-95"
              >
                Отправить вызов в чат ещё раз
              </button>
            )}
            <button onClick={() => action.mutate("cancel")} disabled={action.isPending} className="text-xs text-ink-mist underline">
              Отменить вызов
            </button>
          </div>
        )
      )}

      {inPlay && (
        <>
          {match.can_pick ? (
            <div className="grid grid-cols-5 gap-1.5">
              {ACTION_ORDER.map((a) => {
                const meta = ACTION_META[a];
                const allowed = match.available_actions.includes(a);
                return (
                  <motion.button
                    key={a}
                    whileTap={{ scale: 0.9 }}
                    onClick={() => pick.mutate({ action: a, version: match.version })}
                    disabled={!allowed || pick.isPending}
                    aria-label={meta.label}
                    className={`flex flex-col items-center gap-0.5 rounded-2xl bg-gradient-to-b px-1 py-2.5 ring-1 disabled:opacity-30 ${meta.tone}`}
                  >
                    <span className="text-2xl leading-none">{meta.emoji}</span>
                    <span className="text-micro font-bold text-ink-chalk">{meta.label}</span>
                  </motion.button>
                );
              })}
            </div>
          ) : (
            <motion.div
              className="rounded-2xl bg-bg-surface px-4 py-3 text-center text-sm text-ink-mist"
              animate={{ opacity: [0.6, 1, 0.6] }}
              transition={{ repeat: Infinity, duration: 1.6 }}
            >
              {match.my_pick ? `Ты выбрал: ${ACTION_META[match.my_pick].label}. Ждём соперника…` : "Ждём соперника…"}
            </motion.div>
          )}
          <p className="text-center text-caption text-ink-mist-dim">
            {match.can_pick && match.opponent_ready ? "Соперник уже выбрал — твоя очередь. " : ""}
            {match.deadline ? `Ход до ${new Date(match.deadline).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit", second: match.live ? "2-digit" : undefined })}` : ""}
            {match.my_auto_moves > 0 ? ` · автопилот ${match.my_auto_moves}/${match.max_auto_moves}` : ""}
          </p>
        </>
      )}

      {recent.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <h2 className="font-mono text-caption uppercase tracking-wider text-ink-mist">Обмены</h2>
          {recent.map((e) => {
            const d = describeExchange(e);
            return (
              <div key={e.n} className="rounded-xl bg-bg-surface px-3 py-2 text-caption">
                <div className="mb-0.5 flex justify-between text-micro text-ink-mist-dim">
                  <span>Раунд {e.round} · обмен {e.exchange}</span>
                  <span className="font-mono">{e.my_hp} : {e.opponent_hp} HP</span>
                </div>
                <p className="text-ink-chalk">Ты: {d.mine}</p>
                <p className="text-ink-mist">Соперник: {d.theirs}</p>
              </div>
            );
          })}
        </div>
      )}

      {inPlay && (
        <button onClick={() => setConfirmForfeit(true)} className="mt-1 text-center text-xs text-ink-mist-dim underline">
          Выбросить полотенце
        </button>
      )}
      {!inPlay && !pending && !showResult && match.status === "finished" && (
        <div className="flex flex-col gap-2">
          {match.can_brutality && (
            <button
              onClick={() => setBrutalityPicker(true)}
              className="rounded-2xl bg-gradient-to-r from-red-600 to-yellow-500 py-3 text-sm font-black uppercase tracking-wide text-white active:scale-95"
            >
              😈 Сделать бруталити
            </button>
          )}
          {match.brutality && (
            <button onClick={() => setBrutalityOpen(true)} className="rounded-2xl bg-red-500/10 px-4 py-3 text-left text-sm text-red-200 active:scale-[0.98]">
              {match.brutality.emoji} Бруталити: {match.brutality.by_me ? "ты" : "соперник"} {match.brutality.text}
            </button>
          )}
          <button onClick={() => setShowResult(true)} className="rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
            Итог боя
          </button>
        </div>
      )}

      <ConfirmDialog
        open={confirmForfeit}
        title="Сдаться?"
        description="Бой засчитают поражением без награды."
        danger
        confirmLabel="Сдаться"
        onConfirm={() => { setConfirmForfeit(false); action.mutate("forfeit"); }}
        onCancel={() => setConfirmForfeit(false)}
      />

      {brutalityPicker && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setBrutalityPicker(false)}>
          <div className="safe-bottom flex w-full flex-col gap-2 rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="font-display text-base font-bold text-ink-chalk">Добить соперника 😈</p>
            <p className="-mt-1 text-caption text-ink-mist">Шутка для победителя: результат и рейтинг не меняет, но добавляет монет к выигрышу.</p>
            {ownedBrutalities.length ? (
              <div className="grid grid-cols-3 gap-2">
                {ownedBrutalities.map((b) => (
                  <button
                    key={b.id}
                    onClick={() => finish.mutate(b.id)}
                    disabled={finish.isPending}
                    className="flex flex-col items-center gap-1 rounded-2xl bg-white/5 p-3 active:scale-95 disabled:opacity-50"
                  >
                    {b.image_path ? (
                      <img src={staticUrl(b.image_path)} alt="" className="h-12 w-12 rounded-xl object-cover" />
                    ) : (
                      <span className="text-4xl">{BRUTALITY_EMOJI[b.style_key] ?? "🥊"}</span>
                    )}
                    <span className="text-center text-micro font-semibold text-ink-chalk">{b.name}</span>
                    {(b.win_bonus_coins ?? 0) > 0 && <span className="text-micro text-accent-lime">+{b.win_bonus_coins} монет</span>}
                  </button>
                ))}
              </div>
            ) : (
              <p className="rounded-xl bg-white/5 px-3 py-3 text-sm text-ink-mist">Пока нечем — бруталити продаются в магазине.</p>
            )}
            <button
              onClick={() => navigate("/packs?tab=style")}
              className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-accent-lime active:scale-95"
            >
              Магазин бруталити →
            </button>
          </div>
        </div>
      )}
      {match.brutality && (
        <BrutalityShow
          open={brutalityOpen}
          brutality={match.brutality}
          victimName={match.opponent_name}
          matchId={match.id}
          onClose={() => setBrutalityOpen(false)}
        />
      )}

      <AnimatePresence>
        {showResult && match.status === "finished" && (
          <motion.div
            className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            onClick={() => setShowResult(false)}
          >
            <motion.div
              className="w-full max-w-sm rounded-3xl bg-bg-base p-6 text-center"
              initial={{ scale: 0.7, rotate: -4 }}
              animate={{ scale: 1, rotate: 0 }}
              transition={{ type: "spring", stiffness: 260, damping: 18 }}
              onClick={(e) => e.stopPropagation()}
            >
              <p className="text-5xl">{match.result === "win" ? "🏆" : match.result === "loss" ? "🤕" : "🤝"}</p>
              <p className="mt-2 font-display text-2xl font-black text-ink-chalk">{RESULT_TITLES[match.result ?? "draw"]}</p>
              <p className="text-sm text-yellow-400">{WIN_REASON_LABELS[match.win_reason ?? ""] ?? ""}</p>
              {match.scorecards.length > 0 && (
                <p className="mt-1 font-mono text-xs text-ink-mist">Судьи: {totals.mine}:{totals.opponent}</p>
              )}
              <div className="mt-4 flex justify-center gap-4 text-sm">
                <span className="flex items-center gap-1 font-bold text-ink-chalk">
                  +{match.reward_coins} <IconCoin size={14} />
                </span>
                {match.rating_delta !== 0 && (
                  <span className={match.rating_delta > 0 ? "font-bold text-accent-green" : "font-bold text-red-400"}>
                    {match.rating_delta > 0 ? "+" : ""}{match.rating_delta} рейтинга
                  </span>
                )}
              </div>
              {match.can_brutality && (
                <button
                  onClick={() => { setShowResult(false); setBrutalityPicker(true); }}
                  className="mt-4 w-full rounded-2xl bg-gradient-to-r from-red-600 to-yellow-500 py-3 text-sm font-black uppercase tracking-wide text-white active:scale-95"
                >
                  😈 Сделать бруталити
                </button>
              )}
              {match.result === "win" && (
                <ShareButton kind="mordoboi_win" id={match.id} label="Похвастаться в чате" className="mt-2" />
              )}
              <div className="mt-3 flex gap-2">
                {match.opponent_type !== "online" && match.opponent_type !== "chat" && (
                  <button
                    onClick={() => rematch.mutate(match)}
                    disabled={rematch.isPending}
                    className="flex-1 rounded-2xl bg-yellow-500 py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
                  >
                    Реванш
                  </button>
                )}
                <button onClick={() => navigate("/play/mordoboi")} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
                  К режиму
                </button>
              </div>
            </motion.div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}
