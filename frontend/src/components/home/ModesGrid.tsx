import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchAcademy } from "@/api/academy";
import { fetchCareer, type CareerSeason } from "@/api/career";
import { fetchClubBase } from "@/api/clubBase";
import { claimDailyReward, fetchMyClub, fetchNextOpponent, fetchTournamentCurrent } from "@/api/clubs";
import { fetchArenaStats } from "@/api/matches";
import { fetchMyPlayer } from "@/api/myPlayer";
import { fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import NewBadge from "@/components/common/NewBadge";
import { IconBall, IconCampus, IconProfile, IconTrophy, IconUsers, IconWhistle } from "@/components/icons";
import { artOf } from "@/lib/gameArt";
import { hapticNotify } from "@/lib/telegram";

function careerPlace(season: CareerSeason): number | null {
  const table = [...season.table].sort(
    (a, b) => b.points - a.points || (b.gf - b.ga) - (a.gf - a.ga) || b.gf - a.gf,
  );
  const idx = table.findIndex((r) => r.team_index === season.my_team_index);
  return idx >= 0 ? idx + 1 : null;
}

/** Each mode keeps its own colour so the grid reads at a glance. */
const TINTS = {
  cyan: { box: "bg-accent-cyan/10 ring-accent-cyan/25", icon: "bg-accent-cyan/20 text-accent-cyan", text: "text-accent-cyan" },
  amber: { box: "bg-amber-400/10 ring-amber-400/25", icon: "bg-amber-400/20 text-amber-300", text: "text-amber-300" },
  path: { box: "bg-path/10 ring-path/25", icon: "bg-path/20 text-path", text: "text-path" },
  lime: { box: "bg-accent-lime/10 ring-accent-lime/25", icon: "bg-accent-lime/20 text-accent-lime", text: "text-accent-lime" },
  violet: { box: "bg-violet-400/10 ring-violet-400/25", icon: "bg-violet-400/20 text-violet-300", text: "text-violet-300" },
  green: { box: "bg-accent-green/10 ring-accent-green/25", icon: "bg-accent-green/20 text-accent-green", text: "text-accent-green" },
} as const;

/** «Режимы»: the long-running modes as a 2-column grid of tiles, each with
 * one status line; a tile with something waiting gets a pulsing dot. */
export default function ModesGrid() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();

  // Same query keys as the mode pages, so the caches are shared.
  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const { data: clubTournament } = useQuery({
    queryKey: ["clubs", "tournament", "current"],
    queryFn: fetchTournamentCurrent,
    enabled: !!club,
    retry: false,
  });
  const { data: nextOpponent } = useQuery({
    queryKey: ["clubs", "tournament", "next-opponent"],
    queryFn: fetchNextOpponent,
    enabled: !!club && clubTournament?.status === "active",
    retry: false,
  });
  const { data: career } = useQuery({ queryKey: ["career"], queryFn: fetchCareer, staleTime: 60_000 });
  const { data: base } = useQuery({ queryKey: ["club-base"], queryFn: fetchClubBase, staleTime: 30_000 });
  // «Академия» lives inside the base: its free scouting report still lights the tile.
  const { data: academy } = useQuery({ queryKey: ["academy"], queryFn: fetchAcademy, staleTime: 30_000 });
  const { data: myPlayer } = useQuery({ queryKey: ["my-player"], queryFn: fetchMyPlayer });
  const { data: tournament } = useQuery({
    queryKey: ["player-tournament", "current"],
    queryFn: fetchPlayerTournamentCurrent,
  });
  const { data: arena } = useQuery({ queryKey: ["arena-stats"], queryFn: fetchArenaStats });

  const claimClub = useMutation({
    mutationFn: claimDailyReward,
    onSuccess: () => {
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
  });

  const clubRewardReady = !!club && club.daily_reward_seconds_remaining === null;
  const season = career?.season;
  const seasonOn = !!season && (season.status === "active" || season.status === "pending") && season.my_status === "accepted";
  const place = season?.status === "active" ? careerPlace(season) : null;
  const baseIncome = base?.income.pending ?? 0;
  const scoutReady = !!academy?.scout_report?.available;

  return (
    <section>
      <h2 className="mb-2 font-display text-base font-bold text-ink-chalk">Режимы</h2>
      <div className="grid grid-cols-2 gap-2">
        {career?.enabled !== false && (
          <ModeTile
            tint="cyan"
            icon={<IconWhistle size={18} />}
            art="career"
            title="Карьера"
            status={
              career?.invite
                ? "Зовут в сезон"
                : seasonOn && season
                  ? season.status === "pending"
                    ? "Сезон собирается"
                    : `${place ? `${place} место · ` : ""}тур ${Math.min(season.rounds_played + 1, season.total_rounds)}/${season.total_rounds}`
                  : "Начать сезон"
            }
            alert={!!career?.invite}
            onClick={() => navigate("/play/career")}
          />
        )}
        <ModeTile
          tint="amber"
          icon={
            club ? (
              <ClubLogo shape={club.logo_shape} color={club.logo_color} emblem={club.emblem} size={30} />
            ) : (
              <IconUsers size={18} />
            )
          }
          art="home-club"
          badge={club ? <ClubLogo shape={club.logo_shape} color={club.logo_color} emblem={club.emblem} size={24} /> : undefined}
          title="Клуб"
          status={
            club
              ? clubRewardReady
                ? "Забрать награду"
                : nextOpponent
                  ? `Тур ${nextOpponent.round_number}: ${nextOpponent.opponent_club_name}`
                  : club.name
              : "Вступи в клуб"
          }
          alert={clubRewardReady}
          onClick={() => (clubRewardReady && !claimClub.isPending ? claimClub.mutate() : navigate("/clubs"))}
        />
        {base?.enabled !== false && (
          <ModeTile
            tint="path"
            icon={<IconCampus size={18} />}
            art="home-base"
            title="Клубная база"
            corner={<NewBadge section="club-base" />}
            status={
              !base
                ? "Стадион, корпуса, Академия"
                : baseIncome > 0
                  ? `Доход готов: +${baseIncome}`
                  : scoutReady
                    ? "Скаутский отчёт готов!"
                    : base.construction
                      ? `Строится: ${base.construction.name}`
                      : base.total_level === 0
                        ? "Начни со штаб-квартиры"
                        : `ур. ${base.total_level} · бригада свободна`
            }
            alert={baseIncome > 0 || scoutReady}
            onClick={() => navigate("/base")}
          />
        )}
        {myPlayer?.enabled !== false && (
          <ModeTile
            tint="lime"
            icon={<IconProfile size={18} />}
            art="home-player"
            title="Мой игрок"
            status={
              myPlayer?.player
                ? myPlayer.points_available > 0
                  ? `Очков навыков: ${myPlayer.points_available}`
                  : `${myPlayer.player.rating} OVR · ур. ${myPlayer.level}`
                : "Создай своего игрока"
            }
            alert={!!myPlayer?.player && myPlayer.points_available > 0}
            onClick={() => navigate("/my-player")}
          />
        )}
        <ModeTile
          tint="violet"
          icon={<IconTrophy size={18} />}
          art="player-tournament"
          title="Турнир"
          status={
            tournament?.status === "queued"
              ? `В очереди: ${tournament.queue_position ?? "?"}`
              : tournament?.status === "active"
                ? "Турнир идёт"
                : "Подать заявку"
          }
          onClick={() => navigate("/player-tournament")}
        />
        <ModeTile
          tint="green"
          icon={<IconBall size={18} />}
          art="arena"
          title="Арена"
          status={
            arena?.division
              ? `Див. ${arena.division.division} · ${arena.division.points} очк.`
              : `Рейтинг ${arena?.arena_rating ?? 1000}`
          }
          onClick={() => navigate("/play/arena")}
        />
      </div>
    </section>
  );
}

function ModeTile({
  tint, icon, art, badge, title, status, alert, corner, onClick,
}: {
  tint: keyof typeof TINTS;
  icon: ReactNode;
  /** Illustrated picture in place of the icon (lib/gameArt key), also blurred behind the tile. */
  art?: string;
  /** Small overlay on the picture's corner (the club's own emblem). */
  badge?: ReactNode;
  title: ReactNode;
  status: string;
  alert?: boolean;
  /** Small label in the top-right corner (e.g. «Новое»), hidden under the alert dot. */
  corner?: ReactNode;
  onClick: () => void;
}) {
  const t = TINTS[tint];
  const picture = art ? artOf(art) : undefined;
  return (
    <button
      onClick={onClick}
      className={`relative flex min-h-[96px] flex-col justify-between gap-2 overflow-hidden rounded-2xl p-3 text-left ring-1 active:scale-[0.97] ${t.box}`}
    >
      {picture && (
        <img src={picture} alt="" aria-hidden className="pointer-events-none absolute inset-0 h-full w-full scale-125 object-cover opacity-25 blur-xl" />
      )}
      {picture ? (
        <span className="relative h-12 w-12 shrink-0">
          <img src={picture} alt="" className="h-12 w-12 rounded-xl object-cover shadow-[0_8px_18px_-8px_rgba(0,0,0,0.8)] ring-1 ring-white/15" />
          {badge && <span className="absolute -bottom-1.5 -right-1.5">{badge}</span>}
        </span>
      ) : (
        <span className={`flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl ${t.icon}`}>{icon}</span>
      )}
      {alert ? (
        <span className="absolute right-3 top-3 h-2.5 w-2.5 animate-pulse rounded-full bg-accent-lime" aria-label="Есть действие" />
      ) : (
        corner && <span className="absolute right-2.5 top-2.5">{corner}</span>
      )}
      <span className="relative min-w-0">
        <span className="block truncate font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className={`block truncate text-xs ${alert ? `font-semibold ${t.text}` : "text-ink-mist"}`}>{status}</span>
      </span>
    </button>
  );
}
