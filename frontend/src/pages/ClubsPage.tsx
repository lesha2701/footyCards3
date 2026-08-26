import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { ClubLogo } from "@/components/clubs/ClubLogo";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconPlus, IconUsers } from "@/components/icons";
import {
  acceptJoinRequest,
  createJoinRequest,
  fetchClubs,
  fetchMyClub,
  fetchMyJoinRequests,
  joinClub,
  kickMember,
  leaveClub,
  rejectJoinRequest,
} from "@/api/clubs";
import { fetchMyProfile } from "@/api/profile";
import { ApiRequestError } from "@/lib/api";
import { hapticNotify, showConfirm } from "@/lib/telegram";
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

      {joinError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{joinError}</p>}
      {isLoading && <ListSkeleton />}
      {!isLoading && !clubs?.length && <EmptyState icon={IconUsers} title="Клубов пока нет" description="Стань первым, кто создаст клуб" />}

      <div className="flex flex-col gap-2">
        {clubs?.map((c) => (
          <div key={c.id} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3">
            <ClubLogo shape={c.logo_shape} color={c.logo_color} size={40} />
            <div className="flex-1">
              <p className="font-display text-sm font-bold text-ink-chalk">{c.name}</p>
              <p className="text-xs text-ink-mist-dim">{c.member_count}/11 участников</p>
            </div>
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
    </div>
  );
}

const ROLE_LABELS: Record<string, string> = { captain: "Капитан", assistant: "Ассистент", member: "Участник" };

function ClubHome({ club }: { club: Club }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const isManager = club.my_role === "captain" || club.my_role === "assistant";
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });

  const invalidate = () => queryClient.invalidateQueries({ queryKey: ["clubs"] });
  const leaveMutation = useMutation({ mutationFn: leaveClub, onSuccess: invalidate });
  const kickMutation = useMutation({ mutationFn: (id: number) => kickMember(id), onSuccess: invalidate });

  const { data: joinRequests } = useQuery({
    queryKey: ["clubs", "join-requests"],
    queryFn: fetchMyJoinRequests,
    enabled: isManager && club.club_type === "closed",
  });
  const acceptMutation = useMutation({ mutationFn: (id: number) => acceptJoinRequest(id), onSuccess: invalidate });
  const rejectMutation = useMutation({
    mutationFn: (id: number) => rejectJoinRequest(id),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["clubs", "join-requests"] }),
  });

  const handleLeave = async () => {
    const confirmMsg = club.my_role === "captain" ? "Покинуть клуб? Капитанство перейдёт ассистенту (или клуб распустится, если ассистентов нет)." : "Покинуть клуб?";
    if (await showConfirm(confirmMsg)) leaveMutation.mutate();
  };

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-3">
        <ClubLogo shape={club.logo_shape} color={club.logo_color} size={56} />
        <div>
          <h1 className="font-display text-xl font-bold text-ink-chalk">{club.name}</h1>
          <p className="text-xs text-ink-mist-dim">{club.member_count}/11 участников · {ROLE_LABELS[club.my_role ?? "member"]}</p>
        </div>
      </div>

      {club.description && <p className="rounded-2xl bg-bg-surface p-3 text-sm text-ink-mist">{club.description}</p>}

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

      {isManager && (
        <button
          onClick={() => navigate("/clubs/squad")}
          className="rounded-2xl bg-bg-surface p-3 text-left text-sm font-semibold text-ink-chalk active:scale-[0.99]"
        >
          ⚽ Управление составом
        </button>
      )}

      {isManager && club.club_type === "closed" && joinRequests && joinRequests.length > 0 && (
        <div className="flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Заявки на вступление</p>
          {joinRequests.map((r) => (
            <div key={r.id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
              <span className="text-sm text-ink-chalk">{r.username ?? r.first_name ?? `#${r.user_id}`}</span>
              <div className="flex gap-2">
                <button onClick={() => acceptMutation.mutate(r.id)} className="rounded-lg bg-accent-green px-2 py-1 text-[11px] font-bold text-bg-base">
                  Принять
                </button>
                <button onClick={() => rejectMutation.mutate(r.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400">
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div className="flex flex-col gap-2">
        <p className="font-display text-sm font-bold text-ink-chalk">Участники</p>
        {club.members.map((m) => (
          <div key={m.user_id} className="flex items-center justify-between rounded-xl bg-bg-surface p-3">
            <span className="text-sm text-ink-chalk">{m.username ?? m.first_name ?? `#${m.user_id}`} · {ROLE_LABELS[m.role]}</span>
            {isManager && m.role === "member" && m.user_id !== userId && (
              <button
                onClick={() => kickMutation.mutate(m.user_id)}
                className="rounded-lg bg-red-500/10 px-2 py-1 text-[11px] text-red-400"
              >
                Исключить
              </button>
            )}
          </div>
        ))}
      </div>

      <button onClick={handleLeave} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
        Покинуть клуб
      </button>
    </div>
  );
}
