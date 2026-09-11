import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ClubLogo } from "@/components/clubs/ClubLogo";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconBrain, IconChart, IconChevronRight, IconClock, IconCoin, IconFlagCheckered, IconGift, IconGlobe, IconGoal, IconLock, IconPlus, IconStar, IconTrophy, IconUsers } from "@/components/icons";
import {
  acceptJoinRequest,
  appointAssistant,
  applyToTournament,
  claimDailyReward,
  createJoinRequest,
  fetchClubs,
  fetchMyClub,
  fetchMyJoinRequests,
  fetchNextOpponent,
  fetchTournamentCurrent,
  joinClub,
  kickMember,
  leaveClub,
  rejectJoinRequest,
  removeAssistant,
  setMemberPersonalReward,
  updateClubType,
} from "@/api/clubs";
import { fetchMyProfile } from "@/api/profile";
import { ApiRequestError } from "@/lib/api";
import { formatCountdown } from "@/lib/format";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { Club } from "@/types";

export default function ClubsPage() {
  const { data: myClub, isLoading: loadingMine, error: myClubError } = useQuery({
    queryKey: ["clubs", "me"],
    queryFn: fetchMyClub,
    retry: false,
  });

  const inClub = !loadingMine && !myClubError;

  if (loadingMine) return <ListSkeleton />;
  if (inClub && myClub) return <ClubHome club={myClub} />;
  return <ClubBrowseList />;
}

function ClubBrowseList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [joinError, setJoinError] = useState<string | null>(null);
  const [requestSentId, setRequestSentId] = useState<number | null>(null);
  const [previewClubId, setPreviewClubId] = useState<number | null>(null);
  const queryClient = useQueryClient();
  const { data: clubs, isLoading } = useQuery({ queryKey: ["clubs", "list", search], queryFn: () => fetchClubs(search) });

  const joinMutation = useMutation({
    mutationFn: (id: number) => joinClub(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs"] }),
    onError: (err) => setJoinError(err instanceof ApiRequestError ? err.message : "Не удалось вступить"),
  });
  const requestMutation = useMutation({
    mutationFn: (id: number) => createJoinRequest(id),
    onSuccess: (_data, id) => setRequestSentId(id),
    onError: (err) => setJoinError(err instanceof ApiRequestError ? err.message : "Не удалось отправить заявку"),
  });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Клубы</h1>
        <button
          onClick={() => navigate("/clubs/create")}
          className="flex items-center gap-1 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
        >
          <IconPlus size={13} />
          Создать
        </button>
      </div>

      <input
        value={search}
        onChange={(e) => setSearch(e.target.value)}
        placeholder="Поиск клуба..."
        className="rounded-xl bg-bg-surface px-3 py-2 text-sm text-ink-chalk outline-none"
      />

      <button
        onClick={() => navigate("/clubs/leaderboard")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconChart size={16} className="text-accent-lime" />
        Рейтинг клубов
      </button>

      {joinError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{joinError}</p>}
      {isLoading && <ListSkeleton />}
      {!isLoading && !clubs?.length && <EmptyState icon={IconUsers} title="Клубов пока нет" description="Стань первым, кто создаст клуб" />}

      <div className="flex flex-col gap-2">
        {clubs?.map((c) => (
          <div key={c.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <button
              onClick={() => setPreviewClubId(c.id)}
              className="flex flex-1 items-center gap-3 text-left"
            >
              <ClubLogo shape={c.logo_shape} color={c.logo_color} size={40} />
              <div className="flex-1">
                <p className="font-display text-sm font-bold text-ink-chalk">{c.name}</p>
                <p className="text-xs text-ink-mist-dim">{c.member_count}/11 участников</p>
              </div>
            </button>
            {c.club_type === "open" ? (
              <button
                onClick={() => joinMutation.mutate(c.id)}
                className="rounded-xl bg-accent-green px-3 py-2 text-xs font-bold text-bg-base active:scale-95"
              >
                Вступить
              </button>
            ) : requestSentId === c.id ? (
              <span className="rounded-xl bg-accent-green/10 px-3 py-2 text-xs font-semibold text-accent-green">
                Заявка отправлена
              </span>
            ) : (
              <button
                onClick={() => requestMutation.mutate(c.id)}
                disabled={requestMutation.isPending}
                className="rounded-xl bg-white/5 px-3 py-2 text-xs font-semibold text-ink-mist active:scale-95"
              >
                Подать заявку
              </button>
            )}
          </div>
        ))}
      </div>

      <ClubPreviewPopup clubId={previewClubId} onClose={() => setPreviewClubId(null)} />
    </div>
  );
}

const ROLE_LABELS: Record<string, string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };
const MAX_ASSISTANTS = 4;

function ClubHome({ club }: { club: Club }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const isManager = club.my_role === "captain" || club.my_role === "assistant";
  const isCaptain = club.my_role === "captain";
  const assistantCount = club.members.filter((m) => m.role === "assistant").length;
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: tournamentCurrent } = useQuery({ queryKey: ["clubs", "tournament", "current"], queryFn: fetchTournamentCurrent });
  const { data: nextOpponent } = useQuery({
    queryKey: ["clubs", "tournament", "next-opponent"],
    queryFn: fetchNextOpponent,
    enabled: tournamentCurrent?.status === "active",
    retry: false,
  });
  const [applyError, setApplyError] = useState<string | null>(null);
  const applyMutation = useMutation({
    mutationFn: applyToTournament,
    onSuccess: () => { queryClient.invalidateQueries({ queryKey: ["clubs", "tournament", "current"] }); setApplyError(null); },
    onError: (err) => setApplyError(err instanceof ApiRequestError ? err.message : "Не удалось подать заявку"),
  });

  const [actionError, setActionError] = useState<string | null>(null);
  const invalidate = () => { queryClient.invalidateQueries({ queryKey: ["clubs"] }); setActionError(null); };
  const onActionError = (err: unknown) => setActionError(err instanceof ApiRequestError ? err.message : "Не удалось выполнить действие");
  const leaveMutation = useMutation({ mutationFn: leaveClub, onSuccess: invalidate, onError: onActionError });
  const kickMutation = useMutation({ mutationFn: (id: number) => kickMember(id), onSuccess: invalidate, onError: onActionError });
  const appointMutation = useMutation({ mutationFn: (id: number) => appointAssistant(id), onSuccess: invalidate, onError: onActionError });
  const removeAssistantMutation = useMutation({ mutationFn: (id: number) => removeAssistant(id), onSuccess: invalidate, onError: onActionError });
  const togglePersonalRewardMutation = useMutation({
    mutationFn: ({ userId, enabled }: { userId: number; enabled: boolean }) => setMemberPersonalReward(userId, enabled),
    onSuccess: invalidate,
    onError: onActionError,
  });
  const [confirmMemberAction, setConfirmMemberAction] = useState<{ type: "appoint" | "kick"; userId: number; name: string } | null>(null);
  const clubTypeMutation = useMutation({ mutationFn: updateClubType, onSuccess: invalidate, onError: onActionError });

  const [claimError, setClaimError] = useState<string | null>(null);
  const claimMutation = useMutation({
    mutationFn: claimDailyReward,
    onSuccess: () => { invalidate(); setClaimError(null); },
    onError: (err) => setClaimError(err instanceof ApiRequestError ? err.message : "Не удалось получить награду"),
  });

  const { data: joinRequests } = useQuery({
    queryKey: ["clubs", "join-requests"],
    queryFn: fetchMyJoinRequests,
    enabled: isManager && club.club_type === "closed",
  });
  const acceptMutation = useMutation({ mutationFn: (id: number) => acceptJoinRequest(id), onSuccess: invalidate, onError: onActionError });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectJoinRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "join-requests"] }),
    onError: onActionError,
  });

  const [showLeaveConfirm, setShowLeaveConfirm] = useState(false);

  return (
    <div className="flex flex-col gap-4">
      <div className="rounded-2xl bg-bg-surface p-4">
        <div className="flex items-center gap-3">
          <ClubLogo shape={club.logo_shape} color={club.logo_color} size={56} />
          <div className="flex-1">
            <h1 className="font-display text-xl font-bold text-ink-chalk">{club.name}</h1>
            <p className="text-xs text-ink-mist-dim">{club.member_count}/11 участников · {ROLE_LABELS[club.my_role ?? "member"]}</p>
          </div>
        </div>
        <div className="mt-3 flex items-center gap-4 border-t border-white/5 pt-3 text-xs text-ink-mist">
          <span className="flex items-center gap-1">
            <IconClock size={13} />
            С {new Date(club.founded_at).toLocaleDateString("ru-RU")}
          </span>
          <span className="flex items-center gap-1 font-mono font-bold text-accent-lime">
            <IconTrophy size={13} />
            {club.cups_count}
          </span>
          <span className="flex items-center gap-1 font-mono font-bold text-accent-cyan">
            <IconStar size={13} />
            {club.stars_count}
          </span>
        </div>
        {club.description && <p className="mt-3 border-t border-white/5 pt-3 text-sm text-ink-mist">{club.description}</p>}
        <div className="mt-3 flex items-center justify-between border-t border-white/5 pt-3">
          <span className="flex items-center gap-1.5 text-xs text-ink-mist">
            {club.club_type === "open" ? <IconGlobe size={13} /> : <IconLock size={13} />}
            {club.club_type === "open" ? "Открытый клуб" : "Закрытый клуб (по заявке)"}
          </span>
          {isCaptain && (
            <button
              onClick={() => clubTypeMutation.mutate(club.club_type === "open" ? "closed" : "open")}
              disabled={clubTypeMutation.isPending}
              className="rounded-lg bg-white/5 px-2 py-1 text-[11px] font-semibold text-ink-mist active:scale-95 disabled:opacity-40"
            >
              Сделать {club.club_type === "open" ? "закрытым" : "открытым"}
            </button>
          )}
        </div>
      </div>

      <div className="flex items-center justify-between rounded-2xl bg-bg-surface p-3">
        <div>
          <p className="text-xs text-ink-mist-dim">Бюджет клуба</p>
          <p className="flex items-center gap-1 font-mono text-lg font-bold text-accent-lime">
            <IconCoin size={16} />
            {club.budget}
          </p>
        </div>
        {club.daily_reward_seconds_remaining !== null ? (
          <div className="text-right text-xs text-ink-mist-dim">
            <p>Награда получена</p>
            <p className="flex items-center justify-end gap-1 font-semibold text-ink-mist">
              <IconClock size={12} />
              через {formatCountdown(club.daily_reward_seconds_remaining)}
            </p>
          </div>
        ) : (
          <button
            onClick={() => claimMutation.mutate()}
            disabled={claimMutation.isPending}
            className="rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
          >
            Ежедневная награда
          </button>
        )}
      </div>
      {claimError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{claimError}</p>}

      {(tournamentCurrent?.status === "active" || tournamentCurrent?.status === "completed") && tournamentCurrent.tournament_id && (
        <button
          onClick={() => navigate(`/clubs/tournament/${tournamentCurrent.tournament_id}`)}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconFlagCheckered size={16} className="text-accent-lime" />
          Турнир клуба
          {tournamentCurrent.status === "active" && (
            <span className="ml-auto flex items-center gap-1.5 rounded-full bg-accent-lime/10 px-2 py-1 text-[10px] font-bold text-accent-lime">
              <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-accent-lime" />
              Идёт
            </span>
          )}
        </button>
      )}

      {tournamentCurrent?.status === "active" && nextOpponent && (
        <div className="rounded-2xl bg-bg-surface p-3">
          <div className="mb-2 flex items-center gap-2 text-xs text-ink-mist">
            <IconGoal size={14} className="text-accent-lime" />
            Тур {nextOpponent.round_number} · Следующий соперник
          </div>
          <p className="mb-2 font-display text-sm font-bold text-ink-chalk">{nextOpponent.opponent_club_name}</p>
          <div className="grid grid-cols-4 gap-2 text-center">
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.attack}</p>
              <p className="text-[9px] text-ink-mist-dim">Атака</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.midfield}</p>
              <p className="text-[9px] text-ink-mist-dim">Полузащита</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.defence}</p>
              <p className="text-[9px] text-ink-mist-dim">Защита</p>
            </div>
            <div>
              <p className="font-mono text-sm font-bold text-accent-cyan">{nextOpponent.goalkeeping}</p>
              <p className="text-[9px] text-ink-mist-dim">Вратарь</p>
            </div>
          </div>
          {isManager && (
            <div className="mt-3 flex gap-2">
              <button
                onClick={() => navigate("/clubs/squad")}
                className="flex-1 rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95"
              >
                Изменить состав
              </button>
            </div>
          )}
        </div>
      )}

      {tournamentCurrent?.status === "queued" && (
        <div className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">
          <IconFlagCheckered size={16} className="text-accent-lime" />
          В очереди на турнир — место {tournamentCurrent.queue_position}
        </div>
      )}

      {isManager && tournamentCurrent?.can_apply && (
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
            <p className="font-display text-base font-bold text-ink-chalk">Клуб готов к турниру!</p>
            <p className="mt-0.5 text-xs leading-snug text-ink-mist">
              Можно подать заявку прямо сейчас — не упусти момент, пока в клубе достаточно участников
            </p>
          </div>
          <IconChevronRight size={18} className="relative shrink-0 text-ink-mist-dim" />
        </button>
      )}
      {isManager && !tournamentCurrent?.can_apply && tournamentCurrent?.cooldown_seconds_remaining != null && (
        <div className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-xs text-ink-mist-dim">
          <IconClock size={14} />
          Новую заявку на турнир можно подать через {formatCountdown(tournamentCurrent.cooldown_seconds_remaining)}
        </div>
      )}
      {applyError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{applyError}</p>}

      {club.invite_code && profile && (
        <div className="rounded-2xl bg-bg-surface p-3">
          <p className="text-xs text-ink-mist">Ссылка-приглашение</p>
          <div className="mt-2 flex items-center gap-2 rounded-xl bg-black/20 px-3 py-2">
            <span className="flex-1 truncate font-mono text-xs text-ink-mist">
              https://t.me/{profile.telegram_bot_username}?start=club_{club.invite_code}
            </span>
            <button
              onClick={() => {
                navigator.clipboard.writeText(`https://t.me/${profile.telegram_bot_username}?start=club_${club.invite_code}`);
                hapticNotify("success");
              }}
              className="shrink-0 rounded-lg bg-floodlight px-2 py-1 text-[11px] font-bold text-bg-base"
            >
              Копировать
            </button>
          </div>
        </div>
      )}

      <button
        onClick={() => navigate("/clubs/squad")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconGoal size={16} className="text-accent-lime" />
        {isManager ? "Управление составом" : "Состав клуба"}
      </button>

      <button
        onClick={() => navigate("/clubs/activity")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconChart size={16} className="text-accent-lime" />
        Активность клуба
      </button>

      {isManager && (
        <button
          onClick={() => navigate("/clubs/packs")}
          className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          <IconGift size={16} className="text-accent-lime" />
          Клубные паки
        </button>
      )}

      <button
        onClick={() => navigate("/clubs/games")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconBrain size={16} className="text-accent-lime" />
        Клубные игры
      </button>

      <button
        onClick={() => navigate("/clubs/leaderboard")}
        className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
      >
        <IconChart size={16} className="text-accent-lime" />
        Рейтинг клубов
      </button>

      {isManager && club.club_type === "closed" && joinRequests && joinRequests.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Заявки на вступление</p>
          {joinRequests.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
              <span className="text-sm text-ink-chalk">{r.username ?? r.first_name ?? `#${r.user_id}`}</span>
              <div className="flex gap-2">
                <button
                  onClick={() => acceptMutation.mutate(r.id)}
                  disabled={acceptMutation.isPending}
                  className="rounded-lg bg-accent-green px-2 py-1 text-[11px] font-bold text-bg-base disabled:opacity-50"
                >
                  Принять
                </button>
                <button
                  onClick={() => rejectMutation.mutate(r.id)}
                  disabled={rejectMutation.isPending}
                  className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400 disabled:opacity-50"
                >
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {actionError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{actionError}</p>}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Участники</p>
        {club.members.map((m) => (
          <div key={m.user_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
            <span className="text-sm text-ink-chalk">{m.username ?? m.first_name ?? `#${m.user_id}`} · {ROLE_LABELS[m.role]}</span>
            <div className="flex gap-2">
              {isCaptain && m.role === "member" && m.user_id !== userId && assistantCount < MAX_ASSISTANTS && (
                <button
                  onClick={() => setConfirmMemberAction({ type: "appoint", userId: m.user_id, name: m.username ?? m.first_name ?? `#${m.user_id}` })}
                  className="rounded-lg bg-accent-lime/10 px-2 py-1 text-[11px] text-accent-lime"
                >
                  Назначить ассистентом
                </button>
              )}
              {isCaptain && m.role === "assistant" && m.user_id !== userId && (
                <button
                  onClick={() => removeAssistantMutation.mutate(m.user_id)}
                  className="rounded-lg bg-white/5 px-2 py-1 text-[11px] text-ink-mist"
                >
                  Понизить
                </button>
              )}
              {isManager && m.role === "member" && m.user_id !== userId && (
                <button
                  onClick={() => setConfirmMemberAction({ type: "kick", userId: m.user_id, name: m.username ?? m.first_name ?? `#${m.user_id}` })}
                  className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400"
                >
                  Исключить
                </button>
              )}
              {isCaptain && (
                <button
                  onClick={() => togglePersonalRewardMutation.mutate({ userId: m.user_id, enabled: !m.personal_reward_enabled })}
                  className={`rounded-lg px-2 py-1 text-[11px] ${m.personal_reward_enabled ? "bg-accent-lime/10 text-accent-lime" : "bg-white/5 text-ink-mist"}`}
                  title="Личная награда за матчи турнира"
                >
                  {m.personal_reward_enabled ? "Награда: вкл" : "Награда: выкл"}
                </button>
              )}
            </div>
          </div>
        ))}
      </div>

      <button onClick={() => setShowLeaveConfirm(true)} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
        Покинуть клуб
      </button>

      {showLeaveConfirm && (
        <div
          className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-6"
          onClick={() => setShowLeaveConfirm(false)}
        >
          <div className="w-full max-w-sm rounded-2xl bg-bg-surface p-5 text-center" onClick={(e) => e.stopPropagation()}>
            <p className="font-display text-base font-bold text-ink-chalk">Покинуть клуб?</p>
            <p className="mt-2 text-sm text-ink-mist">
              {club.my_role === "captain"
                ? "Капитанство перейдёт ассистенту (или клуб распустится, если ассистентов нет)."
                : "Это действие нельзя отменить."}
            </p>
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => setShowLeaveConfirm(false)}
                className="flex-1 rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-chalk active:scale-95"
              >
                Остаться
              </button>
              <button
                onClick={() => { setShowLeaveConfirm(false); leaveMutation.mutate(); }}
                className="flex-1 rounded-xl bg-red-500/80 py-2.5 text-sm font-bold text-white active:scale-95"
              >
                Покинуть
              </button>
            </div>
          </div>
        </div>
      )}

      <ConfirmDialog
        open={!!confirmMemberAction}
        title={confirmMemberAction?.type === "kick" ? `Исключить ${confirmMemberAction.name}?` : `Назначить ${confirmMemberAction?.name} ассистентом?`}
        description={
          confirmMemberAction?.type === "kick"
            ? "Участник будет удалён из клуба. Это действие нельзя отменить."
            : "Ассистент сможет управлять составом, паками и заявками на вступление."
        }
        danger={confirmMemberAction?.type === "kick"}
        confirmLabel={confirmMemberAction?.type === "kick" ? "Исключить" : "Назначить"}
        onConfirm={() => {
          if (!confirmMemberAction) return;
          if (confirmMemberAction.type === "kick") kickMutation.mutate(confirmMemberAction.userId);
          else appointMutation.mutate(confirmMemberAction.userId);
          setConfirmMemberAction(null);
        }}
        onCancel={() => setConfirmMemberAction(null)}
      />
    </div>
  );
}
