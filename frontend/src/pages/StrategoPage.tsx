import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import { searchUsers } from "@/api/profile";
import { createStrategoBotMatch, createStrategoChallenge, fetchStrategoInfo, fetchStrategoMatches, fetchStrategoSquad } from "@/api/stratego";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconFlag, IconHelp, IconPlay, IconShirt, IconUsers } from "@/components/icons";
import StrategoRulesModal from "@/components/stratego/StrategoRulesModal";
import { formatGameError } from "@/lib/errors";
import type { StrategoMatch, UserPublic } from "@/types";

type Tab = "pending" | "active" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending_accept: "Ожидает ответа",
  in_progress: "Идёт",
  finished: "Завершён",
  declined: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};
const OPPONENT_LABELS: Record<string, string> = { bot: "Против бота", friend: "Против друга", online: "Онлайн" };
const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

export default function StrategoPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [rulesOpen, setRulesOpen] = useState(false);
  const [challengeOpen, setChallengeOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: info } = useQuery({ queryKey: ["stratego-info"], queryFn: fetchStrategoInfo });
  const { data: squad } = useQuery({ queryKey: ["stratego-squad"], queryFn: fetchStrategoSquad });
  const { data: matches, isLoading } = useQuery({ queryKey: ["stratego-matches"], queryFn: fetchStrategoMatches });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const activeMatch = matches?.find((m) => m.status === "in_progress");

  const onCreated = (match: StrategoMatch) => {
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    queryClient.invalidateQueries({ queryKey: ["stratego-matches"] });
    navigate(`/play/stratego/matches/${match.id}`);
  };
  const bot = useMutation({
    mutationFn: createStrategoBotMatch,
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось начать матч")),
  });
  const challenge = useMutation({
    mutationFn: (receiverId: number) => createStrategoChallenge(receiverId),
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось отправить вызов")),
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
      {info && (
        <p className="text-[11px] text-ink-mist-dim">
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
              onClick={() => bot.mutate()}
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
          <p className="-mt-2 text-center text-[11px] text-ink-mist-dim">
            Матч стартует по твоей сохранённой расстановке — поменять её можно в «Подготовке»
          </p>
        </>
      )}

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
              <p className="truncate font-display text-sm font-bold text-ink-chalk">{m.opponent_name}</p>
              <p className="mt-0.5 text-[11px] text-ink-mist">
                {OPPONENT_LABELS[m.opponent_type]} · {STATUS_LABELS[m.status]}
                {m.status === "in_progress" && (m.my_turn ? " · твой ход" : " · ход соперника")}
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
