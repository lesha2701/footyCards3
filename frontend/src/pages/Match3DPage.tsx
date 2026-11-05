import { useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { finishFergieTime, startFergieTime } from "@/api/games";
import Match3DGame from "@/components/match3d/Match3DGame";
import { useAuthStore } from "@/store/authStore";

/** «Ферги Тайм»: a short 11-a-side match in landscape. The server records a
 * match played to the end and pays its flat fee; those calls never get in the
 * way of the match itself. */
export default function Match3DPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const session = useRef<Promise<number | null>>(Promise.resolve(null));
  const [reward, setReward] = useState<string | null>(null);

  const kickOff = () => {
    setReward(null);
    session.current = startFergieTime().then((r) => r.session_id, () => null);
  };
  const fullTime = () => {
    void session.current.then(async (id) => {
      if (id === null) {
        setReward("Этот матч без награды");
        return;
      }
      try {
        const done = await finishFergieTime(id);
        updateBalance(done.new_balance);
        setReward(done.reward_coins > 0 ? `+${done.reward_coins} монет` : done.daily_cap_reached ? "Награды за матчи на сегодня закончились" : null);
      } catch {
        setReward("Награду за матч получить не удалось");
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["newbie"] });
    });
  };

  return <Match3DGame onExit={() => navigate("/play")} onKickOff={kickOff} onFullTime={fullTime} reward={reward} />;
}
