import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useLocation, useNavigate, useSearchParams } from "react-router-dom";

import { ClubLogo } from "@/components/clubs/ClubLogo";
import { ClubNow, ClubSection, ClubTabs, ClubTile } from "@/components/clubs/ClubNow";
import { ClubPreviewPopup } from "@/components/clubs/ClubPreviewPopup";
import { ClubSheet } from "@/components/clubs/ClubSheet";
import { SponsorBadge } from "@/components/clubs/SponsorBadge";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconBrain, IconChart, IconChat, IconChevronRight, IconClock, IconCoin, IconFire, IconFlagCheckered, IconGift, IconGlobe, IconGoal, IconLock, IconPlus, IconShirt, IconShop, IconStar, IconSwap, IconSwords, IconTarget, IconTrophy, IconUsers } from "@/components/icons";
import {
  acceptJoinRequest,
  applyToTournament,
  claimDailyReward,
  createJoinRequest,
  fetchClubLeague,
  fetchClubs,
  fetchMyClub,
  fetchMyJoinRequests,
  fetchNextOpponent,
  fetchTournamentCurrent,
  joinClub,
  kickMember,
  leaveClub,
  rejectJoinRequest,
  setClubBudgetPolicy,
  setClubMemberRole,
  setMemberPersonalReward,
  updateClubType,
  type ClubListFilters,
} from "@/api/clubs";
import { fetchClubWar } from "@/api/clubFeatures";
import { fetchMyProfile } from "@/api/profile";
import { ApiRequestError } from "@/lib/api";
import { formatCountdown } from "@/lib/format";
import { hapticNotify, shareToTelegram } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import { useOpenClubSheet } from "@/lib/clubSheet";
import { CLUB_SHEETS, CLUB_TABS, type ClubSheetKey, type ClubTab } from "@/lib/clubTabs";
import { ASSIGNABLE_CLUB_ROLES, CLUB_ROLE_LABELS, isClubManager } from "@/lib/clubRoles";
import type { Club, ClubRole } from "@/types";

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
  const [filters, setFilters] = useState<ClubListFilters>({});
  const { data: clubs, isLoading } = useQuery({
    queryKey: ["clubs", "list", search, filters],
    queryFn: () => fetchClubs(search, filters),
  });

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

      <div className="-mt-2 flex flex-wrap gap-1.5">
        {([
          ["Открытые", filters.club_type === "open", () => setFilters((f) => ({ ...f, club_type: f.club_type === "open" ? undefined : "open" }))],
          ["По заявке", filters.club_type === "closed", () => setFilters((f) => ({ ...f, club_type: f.club_type === "closed" ? undefined : "closed" }))],
          ["Есть места", !!filters.has_space, () => setFilters((f) => ({ ...f, has_space: !f.has_space }))],
        ] as [string, boolean, () => void][]).map(([label, active, onClick]) => (
          <button
            key={label}
            onClick={onClick}
            className={`rounded-full px-3 py-1 text-caption font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {label}
          </button>
        ))}
        <select
          value={filters.sort ?? "members"}
          onChange={(e) => setFilters((f) => ({ ...f, sort: e.target.value as ClubListFilters["sort"] }))}
          className="ml-auto rounded-full bg-bg-surface px-3 py-1 text-caption font-semibold text-ink-mist outline-none"
          aria-label="Сортировка клубов"
        >
          <option value="members">По участникам</option>
          <option value="cups">По кубкам</option>
          <option value="stars">По звёздам</option>
          <option value="new">Новые</option>
        </select>
      </div>

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
              <ClubLogo shape={c.logo_shape} color={c.logo_color} emblem={c.emblem} size={40} />
              <div className="flex-1">
                <p className="font-display text-sm font-bold text-ink-chalk">{c.name}</p>
                <p className="flex items-center gap-2 text-xs text-ink-mist-dim">
                  <span>{c.member_count}/11</span>
                  <span className="flex items-center gap-0.5 text-accent-lime"><IconTrophy size={11} />{c.cups_count}</span>
                  <span className="flex items-center gap-0.5 text-accent-cyan"><IconStar size={11} />{c.stars_count}</span>
                  {c.club_type === "closed" && <IconLock size={11} />}
                </p>
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


function ClubHome({ club }: { club: Club }) {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const userId = useAuthStore((s) => s.user?.id);
  const isManager = isClubManager(club.my_role);
  const isCaptain = club.my_role === "captain";
  const { data: profile } = useQuery({ queryKey: ["profile", "me"], queryFn: fetchMyProfile });
  const { data: tournamentCurrent } = useQuery({ queryKey: ["clubs", "tournament", "current"], queryFn: fetchTournamentCurrent });
  const { data: nextOpponent } = useQuery({
    queryKey: ["clubs", "tournament", "next-opponent"],
    queryFn: fetchNextOpponent,
    enabled: tournamentCurrent?.status === "active",
    retry: false,
  });
  const { data: league } = useQuery({ queryKey: ["clubs", "league"], queryFn: fetchClubLeague });
  const { data: war } = useQuery({ queryKey: ["clubs", "war"], queryFn: fetchClubWar });
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
  const roleMutation = useMutation({
    mutationFn: ({ userId, role }: { userId: number; role: ClubRole }) => setClubMemberRole(userId, role),
    onSuccess: invalidate,
    onError: onActionError,
  });
  const budgetPolicyMutation = useMutation({ mutationFn: setClubBudgetPolicy, onSuccess: invalidate, onError: onActionError });
  const togglePersonalRewardMutation = useMutation({
    mutationFn: ({ userId, enabled }: { userId: number; enabled: boolean }) => setMemberPersonalReward(userId, enabled),
    onSuccess: invalidate,
    onError: onActionError,
  });
  const [confirmMemberAction, setConfirmMemberAction] = useState<{ type: "kick"; userId: number; name: string } | null>(null);
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

  // In the URL: coming back from a section returns to the same tab.
  const [params, setParams] = useSearchParams();
  const location = useLocation();
  const tabParam = params.get("tab") as ClubTab | null;
  const tab: ClubTab = tabParam && CLUB_TABS.includes(tabParam) ? tabParam : "now";
  const setTab = (next: ClubTab) => setParams(next === "now" ? {} : { tab: next }, { replace: true });
  const pendingRequests = club.club_type === "closed" ? joinRequests?.length ?? 0 : 0;
  const swipeFrom = useRef<{ x: number; y: number } | null>(null);
  const openSheet = useOpenClubSheet();
  // A sheet opened by a direct link has nothing behind it in the history.
  const closeSheet = () => {
    if (location.key !== "default") { navigate(-1); return; }
    setParams(tab === "now" ? {} : { tab }, { replace: true });
  };
  const sheetParam = params.get("sheet");
  const sheet = sheetParam === "trophies" || (CLUB_SHEETS as readonly string[]).includes(sheetParam ?? "")
    ? (sheetParam as ClubSheetKey | "trophies")
    : null;

  return (
    <div
      className="flex flex-col gap-4"
      onTouchStart={(e) => { swipeFrom.current = { x: e.touches[0].clientX, y: e.touches[0].clientY }; }}
      onTouchEnd={(e) => {
        const from = swipeFrom.current;
        swipeFrom.current = null;
        if (!from) return;
        const dx = e.changedTouches[0].clientX - from.x;
        const dy = e.changedTouches[0].clientY - from.y;
        if (Math.abs(dx) <= 60 || Math.abs(dx) <= 2 * Math.abs(dy)) return;
        const next = CLUB_TABS[CLUB_TABS.indexOf(tab) + (dx < 0 ? 1 : -1)];
        if (next) setTab(next);
      }}
    >
      <section
        className="overflow-hidden rounded-3xl bg-bg-surface"
        style={{ backgroundImage: `linear-gradient(135deg, color-mix(in srgb, ${club.logo_color} 26%, transparent), transparent 72%)` }}
      >
        <div className="p-4">
        <div className="flex items-center gap-3">
          <button onClick={() => navigate("/clubs/emblem")} className="shrink-0 active:scale-95" aria-label="Эмблема клуба">
            <ClubLogo shape={club.logo_shape} color={club.logo_color} emblem={club.emblem} size={64} />
          </button>
          <div className="min-w-0 flex-1">
            <h1 className="truncate font-display text-xl font-bold text-ink-chalk">{club.name}</h1>
            <p className="text-xs text-ink-mist">{club.member_count}/11 · {CLUB_ROLE_LABELS[club.my_role ?? "member"]}</p>
            <p className="mt-1 flex items-center gap-3 text-xs">
              <span className="flex items-center gap-1 font-mono font-bold text-accent-lime"><IconTrophy size={13} /> {club.cups_count}</span>
              <span className="flex items-center gap-1 font-mono font-bold text-accent-cyan"><IconStar size={13} /> {club.stars_count}</span>
              <span className="flex items-center gap-1 text-ink-mist">{club.club_type === "open" ? <IconGlobe size={12} /> : <IconLock size={12} />}{club.club_type === "open" ? "открытый" : "по заявке"}</span>
            </p>
          </div>
        </div>
        {club.description && <p className="mt-3 text-sm text-ink-mist">{club.description}</p>}
        <div className="mt-3 flex items-center justify-between gap-3 border-t border-white/5 pt-3">
          <button onClick={() => openSheet("treasury")} className="min-w-0 text-left active:scale-95">
            <span className="block text-caption text-ink-mist">Бюджет клуба</span>
            <span className="flex items-center gap-1 font-mono text-lg font-bold text-accent-lime">
              <IconCoin size={16} />
              {club.budget}
              {!!club.star_balance && (
                <span className="ml-2 flex items-center gap-1 text-base text-amber-500">
                  <IconStar size={14} />
                  {club.star_balance}
                </span>
              )}
            </span>
          </button>
          {club.daily_reward_seconds_remaining !== null ? (
            <span className="flex shrink-0 items-center gap-1 text-caption text-ink-mist">
              <IconClock size={12} />
              награда через {formatCountdown(club.daily_reward_seconds_remaining)}
            </span>
          ) : (
            <button
              onClick={() => claimMutation.mutate()}
              disabled={claimMutation.isPending}
              className="shrink-0 rounded-xl bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-40"
            >
              Ежедневная награда
            </button>
          )}
        </div>
        </div>
        <ClubTabs
          tab={tab}
          onChange={setTab}
          badges={{ together: club.wall_unread ?? 0, treasury: club.rewards_unclaimed ?? 0, club: pendingRequests }}
        />
      </section>
      {claimError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{claimError}</p>}

      {tab === "now" && <>
      <ClubNow
        club={club}
        war={war}
        tournament={tournamentCurrent}
        nextOpponent={nextOpponent}
        isManager={isManager}
        pendingRequests={pendingRequests}
        onOpenRequests={() => setTab("club")}
        onApply={() => applyMutation.mutate()}
        applying={applyMutation.isPending}
      />
      {applyError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{applyError}</p>}

      <ClubSection title="Матчи">
        {tournamentCurrent?.tournament_id && (tournamentCurrent.status === "active" || tournamentCurrent.status === "completed") && (
          <ClubTile
            icon={IconFlagCheckered}
            title="Турнир"
            hint={tournamentCurrent.status === "active" ? "идёт сейчас" : "итоги"}
            onClick={() => navigate(`/clubs/tournament/${tournamentCurrent.tournament_id}`)}
          />
        )}
        <ClubTile icon={IconGoal} title="Состав" hint={isManager ? "управление" : "посмотреть"} onClick={() => navigate("/clubs/squad")} />
        {league?.enabled && (
          <ClubTile
            icon={IconTrophy}
            title="Лига клубов"
            hint={league.my_row ? `${league.my_row.rank} место · ${league.my_row.points} очк.` : "пока без очков"}
            onClick={() => openSheet("league")}
          />
        )}
        <ClubTile
          icon={IconSwords}
          tint="text-red-500"
          title="Война"
          hint={war?.state === "active" ? `идёт · ${war.me?.score ?? 0}:${war.opponent?.score ?? 0}` : war ? `рейтинг ${war.war_rating}` : undefined}
          onClick={() => openSheet("war")}
        />
        <ClubTile icon={IconBrain} title="Клубные игры" onClick={() => openSheet("games")} />
      </ClubSection>
      {isManager && !tournamentCurrent?.can_apply && tournamentCurrent?.cooldown_seconds_remaining != null && (
        <p className="flex items-center gap-2 rounded-2xl bg-bg-surface p-3 text-xs text-ink-mist">
          <IconClock size={14} />
          Новую заявку на турнир можно подать через {formatCountdown(tournamentCurrent.cooldown_seconds_remaining)}
        </p>
      )}
      </>}

      {tab === "together" && <ClubSection title="Вместе">
        <ClubTile icon={IconTarget} title="Задания недели" onClick={() => openSheet("quests")} />
        <ClubTile icon={IconFire} tint="text-orange-500" title="Рейд" hint="босс недели" onClick={() => openSheet("raid")} />
        <ClubTile icon={IconChart} title="Активность" onClick={() => openSheet("activity")} />
        <ClubTile
          icon={IconChat}
          tint="text-accent-cyan"
          title="Стена"
          badge={club.wall_unread ? club.wall_unread : undefined}
          onClick={() => openSheet("wall")}
        />
      </ClubSection>}

      {tab === "treasury" && <ClubSection title="Казна и карты">
        <ClubTile
          icon={IconShop}
          title="Магазин"
          badge={club.rewards_unclaimed ? `🎁 ${club.rewards_unclaimed}` : undefined}
          onClick={() => openSheet("shop")}
        />
        <ClubTile icon={IconStar} tint="text-amber-500" title="Казна" hint="поддержать звёздами" onClick={() => openSheet("treasury")} />
        {club.can_spend_budget && <ClubTile icon={IconGift} title="Клубные паки" onClick={() => navigate("/clubs/packs")} />}
        <ClubTile icon={IconSwap} title="Лишние карты" hint="продать или слить" onClick={() => navigate("/clubs/surplus")} />
        <ClubTile icon={IconShirt} tint="text-accent-cyan" title="Эмблема" hint={isCaptain ? "конструктор" : "посмотреть"} onClick={() => navigate("/clubs/emblem")} />
      </ClubSection>}

      {tab === "club" && <>
      <ClubSection title="О клубе">
        <ClubTile icon={IconTrophy} tint="text-amber-500" title="Трофеи" onClick={() => openSheet("trophies")} />
        <ClubTile icon={IconTarget} title="Статистика" onClick={() => openSheet("stats")} />
        <ClubTile icon={IconChart} tint="text-accent-cyan" title="Рейтинг клубов" onClick={() => openSheet("leaderboard")} />
      </ClubSection>

      {club.invite_code && profile && (
        <div className="flex gap-2">
          <button
            onClick={() => {
              const link = `https://t.me/${profile.telegram_bot_username}?start=club_${club.invite_code}`;
              const text = `Вступай в мой клуб «${club.name}» в VICTOR FC — вместе играем турниры и лигу!`;
              void shareToTelegram(null, `https://t.me/share/url?url=${encodeURIComponent(link)}&text=${encodeURIComponent(text)}`);
            }}
            className="flex-1 rounded-xl bg-floodlight py-2.5 text-xs font-bold text-bg-base active:scale-95"
          >
            Пригласить друга в Telegram
          </button>
          <button
            onClick={() => {
              navigator.clipboard.writeText(`https://t.me/${profile.telegram_bot_username}?start=club_${club.invite_code}`);
              hapticNotify("success");
            }}
            className="shrink-0 rounded-xl bg-white/10 px-3 py-2.5 text-xs font-bold text-ink-chalk active:scale-95"
          >
            Копировать ссылку
          </button>
        </div>
      )}

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
                  className="rounded-lg bg-accent-green px-2 py-1 text-caption font-bold text-bg-base disabled:opacity-50"
                >
                  Принять
                </button>
                <button
                  onClick={() => rejectMutation.mutate(r.id)}
                  disabled={rejectMutation.isPending}
                  className="rounded-lg bg-red-500/10 px-2 py-1 text-caption text-red-400 disabled:opacity-50"
                >
                  Отклонить
                </button>
              </div>
            </div>
          ))}
        </div>
      )}

      {actionError && <p className="rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{actionError}</p>}

      <details open className="group flex flex-col gap-2">
        <summary className="flex cursor-pointer list-none items-center gap-2 rounded-2xl bg-bg-surface p-3 text-sm font-semibold text-ink-chalk">
          <IconUsers size={16} className="text-accent-lime" />
          <span className="flex-1">Участники · {club.member_count}/11</span>
          <IconChevronRight size={16} className="text-ink-mist-dim transition-transform group-open:rotate-90" />
        </summary>
        <div className="mt-2 flex flex-col gap-2">
        {isCaptain && (
          <button
            onClick={() => clubTypeMutation.mutate(club.club_type === "open" ? "closed" : "open")}
            disabled={clubTypeMutation.isPending}
            className="rounded-xl bg-white/5 px-3 py-2 text-left text-xs text-ink-mist active:scale-95 disabled:opacity-40"
          >
            Сделать клуб {club.club_type === "open" ? "закрытым (по заявке)" : "открытым"}
          </button>
        )}
        {isCaptain && (
          <label className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-mist">
            <input
              type="checkbox"
              checked={!!club.budget_treasurer_only}
              disabled={budgetPolicyMutation.isPending}
              onChange={(e) => budgetPolicyMutation.mutate(e.target.checked)}
            />
            Бюджет тратят только капитан, вице-капитан и казначей (без ассистентов)
          </label>
        )}
        {club.members.map((m) => (
          <div key={m.user_id} className="flex flex-wrap items-center justify-between gap-2 rounded-xl bg-bg-surface p-3">
            <span className="flex min-w-0 items-center gap-1.5 text-sm text-ink-chalk">
              <span className="truncate">{m.username ?? m.first_name ?? `#${m.user_id}`} · {CLUB_ROLE_LABELS[m.role]}</span>
              {m.sponsor_tier && <SponsorBadge tier={m.sponsor_tier} />}
            </span>
            <div className="flex gap-2">
              {isCaptain && m.role !== "captain" && (
                <select
                  value={m.role}
                  onChange={(e) => roleMutation.mutate({ userId: m.user_id, role: e.target.value as ClubRole })}
                  disabled={roleMutation.isPending}
                  className="rounded-lg bg-white/5 px-1.5 py-1 text-caption text-ink-mist outline-none"
                  aria-label="Роль участника"
                >
                  {ASSIGNABLE_CLUB_ROLES.map((r) => <option key={r} value={r}>{CLUB_ROLE_LABELS[r]}</option>)}
                </select>
              )}
              {isManager && (m.role === "member" || m.role === "treasurer") && m.user_id !== userId && (
                <button
                  onClick={() => setConfirmMemberAction({ type: "kick", userId: m.user_id, name: m.username ?? m.first_name ?? `#${m.user_id}` })}
                  className="rounded-lg bg-red-500/10 px-2 py-1 text-caption text-red-400"
                >
                  Исключить
                </button>
              )}
              {isCaptain && (
                <button
                  onClick={() => togglePersonalRewardMutation.mutate({ userId: m.user_id, enabled: !m.personal_reward_enabled })}
                  className={`rounded-lg px-2 py-1 text-caption ${m.personal_reward_enabled ? "bg-accent-lime/10 text-accent-lime" : "bg-white/5 text-ink-mist"}`}
                  title="Личная награда за матчи турнира"
                >
                  {m.personal_reward_enabled ? "Награда: вкл" : "Награда: выкл"}
                </button>
              )}
            </div>
          </div>
        ))}
        </div>
      </details>

      <button onClick={() => setShowLeaveConfirm(true)} className="rounded-xl bg-white/5 py-2.5 text-sm font-semibold text-ink-mist active:scale-95">
        Покинуть клуб
      </button>
      </>}

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

      <ClubSheet sheet={sheet} clubId={club.id} onClose={closeSheet} />

      <ConfirmDialog
        open={!!confirmMemberAction}
        title={`Исключить ${confirmMemberAction?.name ?? ""}?`}
        description="Участник будет удалён из клуба. Это действие нельзя отменить."
        danger
        confirmLabel="Исключить"
        onConfirm={() => {
          if (!confirmMemberAction) return;
          kickMutation.mutate(confirmMemberAction.userId);
          setConfirmMemberAction(null);
        }}
        onCancel={() => setConfirmMemberAction(null)}
      />
    </div>
  );
}
