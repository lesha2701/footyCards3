import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createPenaltyChallenge, createPenaltyOpenChallenge, fetchPenaltyMatches } from "@/api/penalty";
import { fetchFeatureFlags } from "@/api/featureFlags";
import { fetchMyProfile, searchUsers } from "@/api/profile";
import { fetchCollection } from "@/api/collection";
import CardPickerModal from "@/components/cards/CardPickerModal";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin, IconFlagCheckered, IconPlay, IconUsers } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { openTelegramLink } from "@/lib/telegram";
import type { PenaltyMatch, UserPublic } from "@/types";

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
  friend: "Против друга",
  online: "Против соперника",
  chat: "Вызов из чата",
};

export default function PenaltyMatchesPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [challengeSheetOpen, setChallengeSheetOpen] = useState(false);
  const [pickingOpponent, setPickingOpponent] = useState<UserPublic | null>(null);
  const [pickingForSearch, setPickingForSearch] = useState(false);
  const [chatInviteSheetOpen, setChatInviteSheetOpen] = useState(false);
  const [pickingForChatInvite, setPickingForChatInvite] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");

  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: matches, isLoading } = useQuery({ queryKey: ["penalty-matches"], queryFn: fetchPenaltyMatches });
  const { data: collection } = useQuery({
    queryKey: ["collection", "penalty-pvp", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: pickingOpponent !== null || pickingForSearch || pickingForChatInvite !== null,
  });
  const activeMatch = matches?.find((m) => m.status === "in_progress");
  // Refetches periodically so an admin's "kill switch" toggle takes effect
  // for already-open sessions without requiring a reload.
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });

  const challengeMutation = useMutation({
    mutationFn: (cardId: number) => createPenaltyChallenge(pickingOpponent!.id, cardId),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      navigate(`/play/penalty/matches/${match.id}`);
    },
    onError: (err) => {
      // Close the card picker so the error is actually visible — it's a
      // full-screen overlay, so leaving it open (e.g. after the hourly
      // limit is hit) hid the message behind it, reading as the tap on a
      // card just doing nothing.
      setPickingOpponent(null);
      setError(formatGameError(err, "Не удалось отправить вызов"));
    },
  });
  const chatInviteMutation = useMutation({
    mutationFn: (cardId: number) => createPenaltyOpenChallenge(cardId, pickingForChatInvite ?? 0),
    onSuccess: (match) => {
      queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      if (profile?.telegram_bot_username) {
        const deepLink = `https://t.me/${profile.telegram_bot_username}?start=penalty_open_${match.id}`;
        const shareText = match.stake_coins > 0
          ? `🥅 Вызываю на серию пенальти! Ставка: ${match.stake_coins} монет`
          : "🥅 Вызываю на серию пенальти!";
        openTelegramLink(`https://t.me/share/url?url=${encodeURIComponent(deepLink)}&text=${encodeURIComponent(shareText)}`);
      }
      navigate(`/play/penalty/matches/${match.id}`);
    },
    onError: (err) => {
      setPickingForChatInvite(null);
      setError(formatGameError(err, "Не удалось создать приглашение"));
    },
  });

  const filtered = (matches ?? []).filter((m) => {
    if (tab === "pending") return m.status === "pending_accept";
    if (tab === "active") return m.status === "in_progress";
    return ["finished", "declined", "cancelled", "expired"].includes(m.status);
  });

  return (
    <div className="flex flex-col gap-4">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Пенальти с другом</h1>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {activeMatch && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-xs text-ink-mist">
          У тебя есть незавершённый матч — заверши его, чтобы начать новый.
        </p>
      )}

      {activeMatch ? (
        <button
          onClick={() => navigate(`/play/penalty/matches/${activeMatch.id}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base ring-2 ring-accent-green/40 active:scale-95"
        >
          Продолжить матч
        </button>
      ) : (
        <>
          {flags?.matchmaking_enabled !== false && (
            <>
              <button
                onClick={() => setPickingForSearch(true)}
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
          <button
            onClick={() => setChatInviteSheetOpen(true)}
            className="flex items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
          >
            <IconCoin size={14} />
            Вызвать соперника через чат
          </button>
          <div className="flex gap-2">
            <button
              onClick={() => setChallengeSheetOpen(true)}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95"
            >
              <IconUsers size={14} />
              Вызвать друга
            </button>
          </div>
        </>
      )}

      <div className="flex gap-2">
        <TabButton active={tab === "pending"} label="Вызовы" onClick={() => setTab("pending")} />
        <TabButton active={tab === "active"} label="В процессе" onClick={() => setTab("active")} />
        <TabButton active={tab === "history"} label="История" onClick={() => setTab("history")} />
      </div>

      {isLoading && <ListSkeleton />}
      {!isLoading && !filtered.length && (
        <EmptyState icon={IconFlagCheckered} title="Матчей нет" description="Вызови друга на серию пенальти" />
      )}

      <div className="flex flex-col gap-2.5">
        {filtered.map((match) => (
          <MatchRow key={match.id} match={match} onClick={() => navigate(`/play/penalty/matches/${match.id}`)} />
        ))}
      </div>

      {challengeSheetOpen && !pickingOpponent && (
        <ChallengeSheet
          onClose={() => setChallengeSheetOpen(false)}
          onPick={(u) => setPickingOpponent(u)}
        />
      )}

      {pickingOpponent && (
        <CardPickerModal
          open
          title={`Выбери карточку против ${pickingOpponent.username ?? pickingOpponent.first_name ?? "соперника"}`}
          cards={collection?.items ?? []}
          onSelect={(card) => { setChallengeSheetOpen(false); challengeMutation.mutate(card.id); }}
          onClose={() => { setPickingOpponent(null); setChallengeSheetOpen(false); setCardSearch(""); }}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      )}

      {chatInviteSheetOpen && (
        <ChatInviteSheet
          onClose={() => setChatInviteSheetOpen(false)}
          onCreate={(stake) => { setChatInviteSheetOpen(false); setPickingForChatInvite(stake); }}
        />
      )}

      {pickingForChatInvite !== null && (
        <CardPickerModal
          open
          title="Выбери карточку для вызова"
          cards={collection?.items ?? []}
          onSelect={(card) => chatInviteMutation.mutate(card.id)}
          onClose={() => { setPickingForChatInvite(null); setCardSearch(""); }}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      )}

      {pickingForSearch && (
        <CardPickerModal
          open
          title="Выбери карточку для матча"
          cards={collection?.items ?? []}
          onSelect={(card) => navigate("/play/penalty/matches/search", { state: { userCardId: card.id } })}
          onClose={() => { setPickingForSearch(false); setCardSearch(""); }}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      )}
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

function MatchRow({ match, onClick }: { match: PenaltyMatch; onClick: () => void }) {
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

function ChatInviteSheet({ onClose, onCreate }: { onClose: () => void; onCreate: (stakeCoins: number) => void }) {
  const [stake, setStake] = useState("0");
  const stakeCoins = Math.max(0, Math.floor(Number(stake) || 0));

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-3 font-display text-base font-bold text-ink-chalk">Вызвать соперника через чат</p>
        <p className="mb-3 text-xs text-ink-mist">
          Выбери ставку, затем карточку для удара — после этого откроется окно «Поделиться». Первый, кто примет вызов, станет соперником.
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
          className="w-full rounded-xl bg-floodlight py-3 text-sm font-bold text-bg-base active:scale-95"
        >
          Выбрать карточку
        </button>
      </div>
    </div>
  );
}

function ChallengeSheet({ onClose, onPick }: { onClose: () => void; onPick: (user: UserPublic) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search-penalty", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });

  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="w-full rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-3 font-display text-base font-bold text-ink-chalk">Вызвать друга</p>
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
      </div>
    </div>
  );
}
