import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import type { ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { fetchAcademy } from "@/api/academy";
import { fetchCareer, type CareerSeason } from "@/api/career";
import { claimDailyReward, fetchMyClub, fetchNextOpponent, fetchTournamentCurrent } from "@/api/clubs";
import { fetchArenaStats } from "@/api/matches";
import { fetchMyPlayer } from "@/api/myPlayer";
import { fetchPlayerTournamentCurrent } from "@/api/personalTournament";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import NewBadge from "@/components/common/NewBadge";
import { IconBall, IconFlagCheckered, IconStar, IconTrophy, IconUsers } from "@/components/icons";
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
  const academyBuilding = academy?.construction
    ? academy.wings.find((w) => w.code === academy.construction!.building_code)
    : null;

  return (
    <section>
      <h2 className="mb-2 font-display text-base font-bold text-ink-chalk">Режимы</h2>
      <div className="grid grid-cols-2 gap-2">
        {career?.enabled !== false && (
          <ModeTile
            tint="cyan"
            icon={<IconTrophy size={18} />}
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
        {academy?.enabled !== false && (
          <ModeTile
            tint="path"
            icon={<span className="text-base" aria-hidden>🌱</span>}
            title={
              <>
                Академия <NewBadge section="academy" />
              </>
            }
            status={
              !academy
                ? "Молодые игроки"
                : academy.scout_report?.available
                  ? "Скаутский отчёт готов!"
                  : academyBuilding
                    ? `Строится: ${academyBuilding.name}`
                    : academy.level === 0
                      ? "Построй первый корпус"
                      : `ур. ${academy.level} · стройка свободна`
            }
            alert={!!academy?.scout_report?.available}
            onClick={() => navigate("/academy")}
          />
        )}
        {myPlayer?.enabled !== false && (
          <ModeTile
            tint="lime"
            icon={<IconStar size={18} />}
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
          icon={<IconFlagCheckered size={18} />}
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
  tint, icon, title, status, alert, onClick,
}: {
  tint: keyof typeof TINTS;
  icon: ReactNode;
  title: ReactNode;
  status: string;
  alert?: boolean;
  onClick: () => void;
}) {
  const t = TINTS[tint];
  return (
    <button
      onClick={onClick}
      className={`relative flex min-h-[88px] flex-col justify-between gap-2 rounded-2xl p-3 text-left ring-1 active:scale-[0.97] ${t.box}`}
    >
      <span className={`flex h-9 w-9 items-center justify-center overflow-hidden rounded-xl ${t.icon}`}>{icon}</span>
      {alert && (
        <span className="absolute right-3 top-3 h-2.5 w-2.5 animate-pulse rounded-full bg-accent-lime" aria-label="Есть действие" />
      )}
      <span className="min-w-0">
        <span className="flex min-w-0 items-center gap-1 whitespace-nowrap font-display text-sm font-bold text-ink-chalk">{title}</span>
        <span className={`block truncate text-xs ${alert ? `font-semibold ${t.text}` : "text-ink-mist"}`}>{status}</span>
      </span>
    </button>
  );
}
