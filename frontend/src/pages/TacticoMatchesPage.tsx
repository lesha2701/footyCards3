import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createTacticoBotMatch, createTacticoChallenge, createTacticoOpenChallenge, fetchTacticoMatches } from "@/api/tactico";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchMyProfile } from "@/api/profile";
import { searchUsers } from "@/api/profile";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin, IconFlagCheckered, IconHelp, IconPlay, IconShirt, IconUsers } from "@/components/icons";
import TacticoRulesModal from "@/components/tactico/TacticoRulesModal";
import { formatGameError } from "@/lib/errors";
import { openTelegramLink } from "@/lib/telegram";
import type { MatchDifficulty, TacticoMatch, UserPublic } from "@/types";

type Tab = "pending" | "active" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending_accept: "Ожидает ответа",
  in_progress: "В процессе",
  finished: "Завершён",
  declined: "Отклонён",
  cancelled: "Отменён",
  expired: "Истёк",
};

const OPPONENT_TYPE_LABELS: Record<string, string> = {
  bot: "Против бота",
  friend: "Против друга",
  online: "Против соперника",
  chat: "Вызов из чата",
};

const DIFFICULTY_LABELS: { value: MatchDifficulty; label: string }[] = [
  { value: "easy", label: "Лёгкий" },
  { value: "medium", label: "Продвинутый" },
];

export default function TacticoMatchesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [botSheetOpen, setBotSheetOpen] = useState(false);
  const [challengeSheetOpen, setChallengeSheetOpen] = useState(false);
  const [chatInviteSheetOpen, setChatInviteSheetOpen] = useState(false);
  const [rulesOpen, setRulesOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: matches, isLoading } = useQuery({ queryKey: ["tactico-matches"], queryFn: fetchTacticoMatches });
  const activeMatch = matches?.find((m) => m.status === "in_progress");
  // Refetches periodically so an admin's "kill switch" toggle takes effect
  // for already-open sessions without requiring a reload.
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });

  const botMutation = useMutation({
    mutationFn: (difficulty: MatchDifficulty) => createTacticoBotMatch(difficulty),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/tactico/matches/${match.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось начать матч")),
  });
  const challengeMutation = useMutation({
    mutationFn: (receiverId: number) => createTacticoChallenge(receiverId),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/tactico/matches/${match.id}`);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось отправить вызов")),
  });
  const chatInviteMutation = useMutation({
    mutationFn: (stakeCoins: number) => createTacticoOpenChallenge(stakeCoins),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      if (profile?.telegram_bot_username) {
        const deepLink = `https://t.me/${profile.telegram_bot_username}?start=tactico_open_${match.id}`;
        const shareText = match.stake_coins > 0
          ? `⚔️ Вызываю на матч в Тактико! Ставка: ${match.stake_coins} монет`
          : "⚔️ Вызываю на матч в Тактико!";
        openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(deepLink)}&text=${encodeURIComponent(shareText)}`);
      }
      navigate(`/play/tactico/matches/${match.id}`);
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
        <h1 className="font-display text-xl font-bold text-ink-chalk">Тактико</h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => setRulesOpen(true)}
            aria-label="Правила"
            className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-95"
          >
            <IconHelp size={15} />
          </button>
          <button
            onClick={() => navigate("/play/tactico/squad")}
            className="flex items-center gap-1.5 rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-accent-lime active:scale-95"
          >
            <IconShirt size={14} />
            Состав
          </button>
        </div>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {activeMatch && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">
          У тебя есть незавершённый матч — заверши его, чтобы начать новый.
        </p>
      )}

      {activeMatch ? (
        <button
          onClick={() => navigate(`/play/tactico/matches/${activeMatch.id}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base ring-2 ring-accent-green/40 active:scale-95"
        >
          <IconPlay size={19} />
          Продолжить матч
        </button>
      ) : (
        <>
          {flags?.matchmaking_enabled !== false && (
            <>
              <button
                onClick={() => navigate("/play/tactico/search")}
                className="flex items-center justify-center gap-2 rounded-2xl bg-accent py-5 text-base font-bold text-bg-base ring-2 ring-accent/40 active:scale-95"
              >
                <IconPlay size={20} />
                Играть
              </button>
              <p className="-mt-2 text-center text-[11px] text-ink-mist-dim">
                За онлайн-матч рейтинг в <span className="font-semibold text-accent-lime">2 раза больше</span>, чем с ботом или другом
              </p>
            </>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setBotSheetOpen(true)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
            >
              <IconPlay size={14} />
              С ботом
            </button>
            <button
              onClick={() => setChallengeSheetOpen(true)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
            >
              <IconUsers size={14} />
              Вызвать друга
            </button>
          </div>
          <button
            onClick={() => setChatInviteSheetOpen(true)}
            className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconCoin size={14} />
            Вызвать соперника через чат
          </button>
        </>
      )}

      <div className="flex gap-2">
        <TabButton active={tab === "pending"} label="Вызовы" onClick={() => setTab("pending")} />
        <TabButton active={tab === "active"} label="В процессе" onClick={() => setTab("active")} />
        <TabButton active={tab === "history"} label="История" onClick={() => setTab("history")} />
      </div>

      {isLoading && <ListSkeleton />}
      {!isLoading && !filtered.length && (
        <EmptyState icon={IconFlagCheckered} title="Матчей нет" description="Сыграй с ботом или вызови друга" />
      )}

      <div className="flex flex-col gap-2.5">
        {filtered.map((match) => (
          <MatchRow key={match.id} match={match} onClick={() => navigate(`/play/tactico/matches/${match.id}`)} />
        ))}
      </div>

      {botSheetOpen && (
        <Sheet onClose={() => setBotSheetOpen(false)} title="Выбери сложность">
          <div className="flex flex-col gap-2">
            {DIFFICULTY_LABELS.map((d) => (
              <button
                key={d.value}
                onClick={() => { setBotSheetOpen(false); botMutation.mutate(d.value); }}
                className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95"
              >
                {d.label}
              </button>
            ))}
          </div>
        </Sheet>
      )}

      {challengeSheetOpen && (
        <ChallengeSheet
          onClose={() => setChallengeSheetOpen(false)}
          onPick={(u) => { setChallengeSheetOpen(false); challengeMutation.mutate(u.id); }}
        />
      )}

      {chatInviteSheetOpen && (
        <ChatInviteSheet
          busy={chatInviteMutation.isPending}
          onClose={() => setChatInviteSheetOpen(false)}
          onCreate={(stake) => { setChatInviteSheetOpen(false); chatInviteMutation.mutate(stake); }}
        />
      )}

      <TacticoRulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} />
    </div>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl py-2 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}

function MatchRow({ match, onClick }: { match: TacticoMatch; onClick: () => void }) {
  return (
    <button onClick={onClick} className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]">
      <div>
        <p className="font-display text-sm font-bold text-ink-chalk">{match.opponent_name || "Открытый вызов"}</p>
        <p className="mt-0.5 text-[11px] text-ink-mist">
          {OPPONENT_TYPE_LABELS[match.opponent_type]} · {STATUS_LABELS[match.status]}
          {match.stake_coins > 0 && ` · Ставка ${match.stake_coins}`}
        </p>
      </div>
      {match.status !== "pending_accept" && (
        <span className="font-mono text-sm font-bold text-ink-chalk">
          {match.user_score}:{match.opponent_score}
        </span>
      )}
    </button>
  );
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-3 font-display text-base font-bold text-ink-chalk">{title}</p>
        {children}
      </div>
    </div>
  );
}

function ChallengeSheet({ onClose, onPick }: { onClose: () => void; onPick: (user: UserPublic) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search-tactico", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });

  return (
    <Sheet title="Вызвать друга" onClose={onClose}>
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Введи имя пользователя..."
        className="mb-2 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
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
    </Sheet>
  );
}

function ChatInviteSheet({ busy, onClose, onCreate }: { busy: boolean; onClose: () => void; onCreate: (stakeCoins: number) => void }) {
  const [stake, setStake] = useState("0");
  const stakeCoins = Math.max(0, Math.floor(Number(stake) || 0));

  return (
    <Sheet title="Вызвать соперника через чат" onClose={onClose}>
      <p className="mb-3 text-xs text-ink-mist">
        Создадим вызов и откроем окно «Поделиться» — выбери чат, куда его отправить. Первый, кто примет вызов, станет твоим соперником.
      </p>
      <label className="mb-1 block text-xs text-ink-mist-dim">Ставка, монеты (0 — без ставки)</label>
      <input
        type="number"
        min={0}
        inputMode="numeric"
        value={stake}
        onChange={(e) => setStake(e.target.value)}
        className="mb-3 w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none"
      />
      {stakeCoins > 0 && (
        <p className="mb-3 text-[11px] text-ink-mist-dim">
          Победитель заберёт {stakeCoins * 2} монет — по {stakeCoins} с каждой стороны.
        </p>
      )}
      <button
        onClick={() => onCreate(stakeCoins)}
        disabled={busy}
        className="w-full rounded-xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
      >
        {busy ? "Создаём..." : "Создать и поделиться"}
      </button>
    </Sheet>
  );
}
