import { useQuery } from "@tanstack/react-query";

import { fetchDailyRewardCalendar } from "@/api/dailyRewards";
import { fetchFreePackStatus } from "@/api/freePack";
import { fetchTasks } from "@/api/tasks";
import type { Task } from "@/types";

/** Shared queries behind the home "Сегодня" block and the nav badge — the
 * same query keys as the rest of the app, so TanStack Query dedupes them. */
export function useTodayState() {
  const { data: calendar } = useQuery({ queryKey: ["daily-reward-calendar"], queryFn: fetchDailyRewardCalendar });
  const { data: taskList } = useQuery({ queryKey: ["tasks"], queryFn: fetchTasks });
  const { data: freePack } = useQuery({
    queryKey: ["free-pack-status"],
    queryFn: fetchFreePackStatus,
    refetchInterval: 30000,
  });
  const claimableTasks: Task[] = [...(taskList?.regular ?? []), ...(taskList?.premium ?? [])].filter(
    (t) => t.is_completed && !t.is_claimed,
  );
  const dailyReady = !!calendar && !calendar.already_claimed_today;
  const freePackReady = !!freePack?.available;
  return {
    calendar,
    taskList,
    freePack,
    claimableTasks,
    dailyReady,
    freePackReady,
    claimableCount: (dailyReady ? 1 : 0) + claimableTasks.length + (freePackReady ? 1 : 0),
  };
}

export function formatClock(iso: string | null | undefined): string {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}
