import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { claimDailyReward } from "@/api/dailyRewards";
import { claimFreePack } from "@/api/freePack";
import { claimTask } from "@/api/tasks";
import { formatGameError } from "@/lib/errors";
import { grantedExtras } from "@/lib/rewards";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { PackOpenResult, Task } from "@/types";

/** The home claim actions shared by «Главное сейчас» and the «Сегодня»
 * tiles: daily reward + finished tasks in one go, and the free pack. */
export function useTodayClaims() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [summary, setSummary] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const refresh = () => {
    for (const key of [["daily-reward-calendar"], ["tasks"], ["collection"], ["card-skills"]]) {
      queryClient.invalidateQueries({ queryKey: key });
    }
  };

  const claimAll = useMutation({
    mutationFn: async ({ daily, tasks }: { daily: boolean; tasks: Task[] }) => {
      let coins = 0;
      let balance: number | null = null;
      const extras: string[] = [];
      const packs: PackOpenResult[] = [];
      if (daily) {
        const r = await claimDailyReward();
        coins += r.granted.coins + (r.month_bonus?.coins ?? 0);
        balance = r.new_balance;
        extras.push(...grantedExtras(r.granted));
        if (r.month_bonus) extras.push("бонус за месяц", ...grantedExtras(r.month_bonus));
      }
      for (const task of tasks) {
        const r = await claimTask(task.user_task_id);
        coins += r.reward_coins;
        balance = r.new_balance;
        if (r.granted_skill_tokens) extras.push(`жетоны ×${r.granted_skill_tokens.quantity}`);
        if (r.granted_pack) packs.push(r.granted_pack);
      }
      return { coins, balance, extras, packs };
    },
    onSuccess: ({ coins, balance, extras, packs }) => {
      if (balance !== null) updateBalance(balance);
      hapticNotify("success");
      setError(null);
      setSummary(["Забрано", coins ? `+${coins} монет` : null, ...extras].filter(Boolean).join(" · "));
      refresh();
      // Pack rewards play their opening animation one after another.
      if (packs.length) {
        navigate(`/packs/${packs[0].pack.id}/open`, { state: { result: packs[0], queue: packs.slice(1) } });
      }
    },
    onError: (err) => {
      setError(formatGameError(err, "Не удалось забрать награды"));
      refresh();
    },
  });

  const freePack = useMutation({
    mutationFn: claimFreePack,
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
      queryClient.invalidateQueries({ queryKey: ["free-pack-status"] });
      queryClient.invalidateQueries({ queryKey: ["collection"] });
      navigate(`/packs/${data.pack.id}/open`, { state: { result: data } });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось получить пак")),
  });

  return { claimAll, freePack, summary, error, busy: claimAll.isPending || freePack.isPending };
}
