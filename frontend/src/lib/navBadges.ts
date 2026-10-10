import { useQuery } from "@tanstack/react-query";

import { fetchMyAttention } from "@/api/profile";
import { useTodayState } from "@/lib/today";

/** Every tab says when something waits there, so nothing has to be found by
 * opening each section in turn. */
export function useNavBadges(): Record<string, number> {
  const { claimableCount } = useTodayState();
  const { data: attention } = useQuery({
    queryKey: ["attention"],
    queryFn: fetchMyAttention,
    refetchInterval: 60000,
  });
  return {
    "/": claimableCount,
    "/play": (attention?.match_challenges ?? 0) + (attention?.active_friend_matches ?? 0),
    "/collection": attention?.incoming_trades ?? 0,
    "/profile": attention?.league_unseen_rewards ?? 0,
  };
}
