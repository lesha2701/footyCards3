import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { claimNewbieStep, fetchNewbie } from "@/api/newbie";
import { IconParty } from "@/components/icons";
import NewbiePopup from "@/components/newbie/NewbiePopup";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

/** «Попробуй режим» tasks of the «Путь дебютанта»: while the player is in a
 * task's mode, watches for the finished game and then congratulates, pays
 * and sends him back to the list for the next one. */
export default function NewbieTaskWatcher() {
  const { pathname } = useLocation();
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [later, setLater] = useState<string[]>([]);

  const cached = queryClient.getQueryData<{ active: boolean; tasks: { path: string; claimed: boolean }[] }>(["newbie"]);
  const watching =
    !!cached?.active && cached.tasks.some((t) => !t.claimed && t.path !== "/" && pathname.startsWith(t.path));
  const { data: state } = useQuery({
    queryKey: ["newbie"],
    queryFn: fetchNewbie,
    enabled: watching,
    refetchInterval: watching ? 5000 : false,
  });

  const task = state?.active
    ? state.tasks.find((t) => t.played && !t.claimed && pathname.startsWith(t.path) && !later.includes(t.code))
    : undefined;

  const claim = useMutation({
    mutationFn: (code: string) => claimNewbieStep(`task:${code}`),
    onSuccess: (data) => {
      updateBalance(data.rewards.new_balance);
      hapticNotify("success");
      queryClient.setQueryData(["newbie"], data.state);
      navigate("/");
    },
  });

  return (
    <NewbiePopup
      open={!!task}
      Icon={IconParty}
      kicker="Задание выполнено!"
      title={task?.label ?? ""}
      text={
        task ? (
          <>
            Награда: <b className="text-accent-lime">{task.coins.toLocaleString("ru-RU")} монет</b>
            {task.pack_name ? ` и пак «${task.pack_name}»` : ""}. Дальше — следующее задание.
          </>
        ) : null
      }
      cta="Забрать и дальше"
      onCta={() => task && claim.mutate(task.code)}
      busy={claim.isPending}
      error={claim.error ? formatGameError(claim.error, "Не получилось") : null}
      secondary="Ещё поиграю"
      onSecondary={() => task && setLater([...later, task.code])}
    />
  );
}
