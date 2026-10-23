import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchMyProfile, searchUsers } from "@/api/profile";
import {
  createStrategoBotMatch,
  createStrategoChallenge,
  createStrategoOpenChallenge,
  fetchStrategoInfo,
  fetchStrategoMatches,
  fetchStrategoSquad,
  fetchStrategoPuzzle,
  fetchStrategoStats,
  startStrategoPuzzle,
  startStrategoTutorial,
} from "@/api/stratego";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChat, IconCoin, IconFlag, IconHelp, IconPlay, IconShirt, IconTrophy, IconUsers } from "@/components/icons";
import StrategoRulesModal from "@/components/stratego/StrategoRulesModal";
import { formatGameError } from "@/lib/errors";
import { openTelegramLink } from "@/lib/telegram";
import type { StrategoMatch, UserPublic } from "@/types";
import { clampStake, stakeLabel, useStakeMax } from "@/lib/stakes";

type Tab = "pending" | "active" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending_accept: "Ожидает ответа",
  in_progress: "Идёт",
  finished: "Завершён",
  declined: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};
const OPPONENT_LABELS: Record<string, string> = {
  bot: "Против бота", friend: "Против друга", online: "Онлайн", chat: "Вызов из чата",
};
const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

export default function StrategoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [rulesOpen, setRulesOpen] = useState(false);
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [chatOpen, setChatOpen] = useState(false);
  const [botOpen, setBotOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: info } = useQuery({ queryKey: ["stratego-info"], queryFn: fetchStrategoInfo });
  const { data: stats } = useQuery({ queryKey: ["stratego-stats"], queryFn: fetchStrategoStats });
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: squad } = useQuery({ queryKey: ["stratego-squad"], queryFn: fetchStrategoSquad });
  const { data: matches, isLoading } = useQuery({ queryKey: ["stratego-matches"], queryFn: fetchStrategoMatches });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const activeMatch = matches?.find((m) => m.status === "in_progress");

  const onCreated = (match: StrategoMatch) => {
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    queryClient.invalidateQueries({ queryKey: ["stratego-matches"] });
    navigate(`/play/stratego/matches/${match.id}`);
  };
  const { data: puzzle } = useQuery({ queryKey: ["stratego-puzzle"], queryFn: fetchStrategoPuzzle });
  const startPuzzle = useMutation({
    mutationFn: startStrategoPuzzle,
    onSuccess: (m) => navigate(`/play/stratego/matches/${m.id}`),
    onError: (err) => setError(formatGameError(err, "Не удалось открыть задачу")),
  });
  const tutorial = useMutation({
    mutationFn: startStrategoTutorial,
    onSuccess: (m) => navigate(`/play/stratego/matches/${m.id}`),
    onError: (err) => setError(formatGameError(err, "Не удалось начать обучение")),
  });
  const bot = useMutation({
    mutationFn: (difficulty: "easy" | "hard") => createStrategoBotMatch(difficulty),
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось начать матч")),
  });
  const challenge = useMutation({
    mutationFn: (receiverId: number) => createStrategoChallenge(receiverId),
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось отправить вызов")),
  });

  const chatInvite = useMutation({
    mutationFn: (stakeCoins: number) => createStrategoOpenChallenge(stakeCoins),
    onSuccess: (match) => {
      if (profile?.telegram_bot_username) {
        const deepLink = `https://t.me/${profile.telegram_bot_username}?start=stratego_open_${match.id}`;
        const shareText = match.stake_coins > 0
          ? `🏆 Вызываю на «Футбольное Стратего»! Ставка: ${match.stake_coins} монет`
          : "🏆 Вызываю на «Футбольное Стратего»!";
        openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(deepLink)}&text=${encodeURIComponent(shareText)}`);
      }
      onCreated(match);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось создать приглашение")),
  });

  const filtered = (matches ?? []).filter((m) => {
    if (tab === "pending") return m.status === "pending_accept";
    if (tab === "active") return m.status === "in_progress";
    return ["finished", "declined", "cancelled", "expired"].includes(m.status);
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Стратего</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRulesOpen(true)}
            aria-label="Правила"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-95"
          >
            <IconHelp size={15} />
          </button>
          <button
            onClick={() => navigate("/play/stratego/squad")}
            className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95"
          >
            <IconShirt size={14} />
            Подготовка
          </button>
        </div>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {squad && !squad.is_complete && (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">
          Для игры нужно минимум {squad.cards_needed} карточек в коллекции.
        </p>
      )}
      {stats && (
        <button
          onClick={() => navigate("/ranking")}
          className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
        >
          <span className="flex items-center gap-2 text-xs text-ink-mist">
            <IconTrophy size={14} className="text-accent-lime" />
            Рейтинг Стратего
          </span>
          <span className="font-mono text-sm font-bold text-ink-chalk">
            {stats.stratego_rating}
            {stats.stratego_rank ? <span className="ml-1.5 text-caption font-normal text-ink-mist">#{stats.stratego_rank}</span> : null}
          </span>
        </button>
      )}
      {info && (
        <p className="text-caption text-ink-mist-dim">
          Наградных матчей сегодня: {info.rewarded_today}/{info.daily_limit} · победа {info.reward_win} монет
        </p>
      )}

      {activeMatch ? (
        <button
          onClick={() => navigate(`/play/stratego/matches/${activeMatch.id}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base active:scale-95"
        >
          <IconPlay size={19} />
          {activeMatch.my_turn ? "Твой ход — продолжить" : "Продолжить матч"}
        </button>
      ) : (
        <>
          {flags?.matchmaking_enabled !== false && (
            <button
              onClick={() => navigate("/play/stratego/search")}
              className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-5 text-base font-bold text-bg-base active:scale-95"
            >
              <IconPlay size={20} />
              Найти соперника
            </button>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setBotOpen(true)}
              disabled={bot.isPending}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95 disabled:opacity-50"
            >
              <IconPlay size={14} />
              С ботом
            </button>
            <button
              onClick={() => setChallengeOpen(true)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
            >
              <IconUsers size={14} />
              Вызвать друга
            </button>
          </div>
          <button
            onClick={() => setChatOpen(true)}
            className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconChat size={14} />
            Вызвать соперника через чат
          </button>
          <p className="-mt-1 text-center text-caption text-ink-mist-dim">
            Онлайн-матч даёт рейтинг ×2, матч с другом — без рейтинга. Матч стартует по твоей сохранённой расстановке — поменять её можно в «Подготовке»
          </p>
        </>
      )}

      {puzzle && (
        <button
          onClick={() => (puzzle.active_match_id ? navigate(`/play/stratego/matches/${puzzle.active_match_id}`) : startPuzzle.mutate())}
          disabled={startPuzzle.isPending}
          className="flex items-center gap-3 rounded-2xl border border-accent-lime/25 bg-gradient-to-r from-accent-lime/10 to-accent-cyan/5 p-3 text-left active:scale-[0.98]"
        >
          <span className="flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-floodlight text-bg-base">
            <IconTrophy size={20} />
          </span>
          <span className="min-w-0 flex-1">
            <span className="block font-mono text-micro uppercase tracking-wider text-accent-lime">Задача дня</span>
            <span className="block font-display text-sm font-bold text-ink-chalk">{puzzle.title}</span>
            <span className="block text-caption text-ink-mist">
              Захвати Кубок за {puzzle.moves} хода ·{" "}
              {puzzle.solved_today ? "решена сегодня ✓" : `+${puzzle.reward} монет`} · решено всего: {puzzle.solved_total}
            </span>
          </span>
        </button>
      )}
      <button
        onClick={() => tutorial.mutate()}
        disabled={tutorial.isPending}
        className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
      >
        <span>
          <span className="block text-sm font-semibold text-ink-chalk">Обучение</span>
          <span className="block text-caption text-ink-mist">Маленькое поле, подсказки, карточки не нужны</span>
        </span>
        <IconPlay size={16} className="text-accent-lime" />
      </button>

      <div className="flex gap-2">
        {(["pending", "active", "history"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-xl py-2 text-xs font-semibold ${tab === t ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
          >
            {{ pending: "Вызовы", active: "Идут", history: "История" }[t]}
          </button>
        ))}
      </div>

      {isLoading && <ListSkeleton />}
      {!isLoading && !filtered.length && (
        <EmptyState icon={IconFlag} title="Матчей нет" description="Сыграй с ботом или вызови друга" />
      )}
      <div className="flex flex-col gap-2.5">
        {filtered.map((m) => (
          <button
            key={m.id}
            onClick={() => navigate(`/play/stratego/matches/${m.id}`)}
            className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]"
          >
            <div className="min-w-0">
              <p className="truncate font-display text-sm font-bold text-ink-chalk">{m.opponent_name || "Открытый вызов"}</p>
              <p className="mt-0.5 text-caption text-ink-mist">
                {OPPONENT_LABELS[m.opponent_type]} · {STATUS_LABELS[m.status]}
                {m.status === "in_progress" && (m.my_turn ? " · твой ход" : " · ход соперника")}
                {m.stake_coins > 0 && ` · ставка ${m.stake_coins}`}
              </p>
            </div>
            {m.result && <span className="text-xs font-bold text-ink-chalk">{RESULT_LABELS[m.result]}</span>}
          </button>
        ))}
      </div>

      {challengeOpen && (
        <ChallengeSheet
          onClose={() => setChallengeOpen(false)}
          onPick={(u) => { setChallengeOpen(false); challenge.mutate(u.id); }}
        />
      )}
      {botOpen && (
        <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={() => setBotOpen(false)}>
          <div className="safe-bottom w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
            <p className="mb-3 font-display text-base font-bold text-ink-chalk">Выбери соперника</p>
            <div className="flex flex-col gap-2">
              <button
                onClick={() => { setBotOpen(false); bot.mutate("easy"); }}
                className="rounded-2xl bg-white/5 p-3 text-left active:scale-[0.98]"
              >
                <span className="block text-sm font-bold text-ink-chalk">Лёгкий бот</span>
                <span className="block text-caption text-ink-mist">
                  Иногда ошибается · {info ? `${Math.round((info.reward_win * (info.easy_reward_pct ?? 60)) / 100)} монет за победу · ` : ""}рейтинг максимум +1
                </span>
              </button>
              <button
                onClick={() => { setBotOpen(false); bot.mutate("hard"); }}
                className="rounded-2xl border border-accent-lime/30 bg-accent-lime/10 p-3 text-left active:scale-[0.98]"
              >
                <span className="block text-sm font-bold text-ink-chalk">Сильный бот</span>
                <span className="block text-caption text-ink-mist">
                  Охотится Провокатором за Звездой, бережёт Кубок · {info ? `${info.reward_win} монет за победу` : "полная награда"}
                </span>
              </button>
            </div>
          </div>
        </div>
      )}
      {chatOpen && (
        <ChatInviteSheet
          busy={chatInvite.isPending}
          onClose={() => setChatOpen(false)}
          onCreate={(stake) => { setChatOpen(false); chatInvite.mutate(stake); }}
        />
      )}
      <StrategoRulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} info={info} />
    </div>
  );
}

function ChallengeSheet({ onClose, onPick }: { onClose: () => void; onPick: (user: UserPublic) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search-stratego", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="safe-bottom w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-3 font-display text-base font-bold text-ink-chalk">Вызвать друга</p>
        <input
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Введи имя пользователя..."
          className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
        />
        <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
          {results?.map((u) => (
            <button
              key={u.id}
              onClick={() => onPick(u)}
              className="flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-ink-chalk active:scale-[0.98]"
            >
              <IconUsers size={14} className="text-ink-mist-dim" />
              {u.username ?? u.first_name ?? `#${u.id}`}
            </button>
          ))}
          {query.length >= 2 && !results?.length && <p className="text-xs text-ink-mist-dim">Никого не найдено</p>}
        </div>
      </div>
    </div>
  );
}

function ChatInviteSheet({ busy, onClose, onCreate }: { busy: boolean; onClose: () => void; onCreate: (stakeCoins: number) => void }) {
  const [stake, setStake] = useState("0");
  const maxStake = useStakeMax();
  const stakeCoins = clampStake(stake, maxStake);
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="safe-bottom w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-2 font-display text-base font-bold text-ink-chalk">Вызов через чат</p>
        <p className="mb-3 text-xs text-ink-mist">
          Создадим вызов и откроем «Поделиться» — выбери чат. Первый, кто примет вызов, станет твоим соперником.
        </p>
        <label className="mb-1 block text-xs text-ink-mist-dim">{stakeLabel(maxStake)}</label>
        <input
          type="number"
          min={0}
          inputMode="numeric"
          value={stake}
        max={maxStake || undefined}
        disabled={maxStake === 0}
          onChange={(e) => setStake(e.target.value)}
          className="mb-3 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
        />
        {stakeCoins > 0 && (
          <p className="mb-3 flex items-center gap-1 text-caption text-ink-mist-dim">
            Победитель заберёт {stakeCoins * 2} <IconCoin size={11} /> — по {stakeCoins} с каждой стороны, ничья вернёт ставки.
          </p>
        )}
        <button
          onClick={() => onCreate(stakeCoins)}
          disabled={busy}
          className="w-full rounded-xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {busy ? "Создаём..." : "Создать и поделиться"}
        </button>
      </div>
    </div>
  );
}
