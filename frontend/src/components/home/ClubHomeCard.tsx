import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { claimDailyReward, fetchMyClub, fetchNextOpponent, fetchTournamentCurrent } from "@/api/clubs";
import { ClubLogo } from "@/components/clubs/ClubLogo";
import { IconChevronRight, IconTrophy } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

/** The player's own club at a glance: emblem, next tournament opponent and
 * the club's daily reward (claimable right here). Renders nothing for a
 * player outside a club — the hero's "Клубы" shortcut covers joining. */
export default function ClubHomeCard() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  // Same keys/options as ClubsPage, so the two share one cache.
  const { data: club } = useQuery({ queryKey: ["clubs", "me"], queryFn: fetchMyClub, retry: false });
  const { data: tournament } = useQuery({
    queryKey: ["clubs", "tournament", "current"],
    queryFn: fetchTournamentCurrent,
    enabled: !!club,
    retry: false,
  });
  const { data: nextOpponent } = useQuery({
    queryKey: ["clubs", "tournament", "next-opponent"],
    queryFn: fetchNextOpponent,
    enabled: !!club && tournament?.status === "active",
    retry: false,
  });
  const claim = useMutation({
    mutationFn: claimDailyReward,
    onSuccess: () => {
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["clubs"] });
    },
  });

  if (!club) return null;
  const rewardReady = club.daily_reward_seconds_remaining === null;

  return (
    <section className="rounded-3xl bg-bg-surface p-4">
      <button onClick={() => navigate("/clubs")} className="flex w-full items-center gap-3 text-left">
        <ClubLogo shape={club.logo_shape} color={club.logo_color} size={44} />
        <span className="min-w-0 flex-1">
          <span className="block font-mono text-[10px] uppercase tracking-wider text-ink-mist">Мой клуб</span>
          <span className="block truncate font-display text-base font-bold text-ink-chalk">{club.name}</span>
          <span className="flex items-center gap-2 text-[11px] text-ink-mist">
            {club.member_count} в составе
            {club.cups_count > 0 && (
              <span className="flex items-center gap-0.5">
                <IconTrophy size={11} /> {club.cups_count}
              </span>
            )}
          </span>
        </span>
        <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
      </button>

      {(nextOpponent || rewardReady) && (
        <div className="mt-3 flex flex-col gap-2 border-t border-white/5 pt-3">
          {nextOpponent && (
            <p className="text-xs text-ink-mist">
              Тур {nextOpponent.round_number}: следующий соперник —{" "}
              <span className="font-semibold text-ink-chalk">{nextOpponent.opponent_club_name}</span>
            </p>
          )}
          {rewardReady && (
            <button
              onClick={() => claim.mutate()}
              disabled={claim.isPending}
              className="self-start rounded-full bg-floodlight px-3 py-1.5 text-xs font-bold text-bg-base active:scale-95 disabled:opacity-50"
            >
              {claim.isPending ? "Забираем..." : "Забрать награду клуба"}
            </button>
          )}
          {claim.isError && <p className="text-xs text-red-400">{formatGameError(claim.error, "Не удалось получить награду")}</p>}
        </div>
      )}
    </section>
  );
}
