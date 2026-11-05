import { useQueryClient } from "@tanstack/react-query";
import { useRef } from "react";
import { useNavigate } from "react-router-dom";

import { finishFergieTime, startFergieTime } from "@/api/games";
import Match3DGame from "@/components/match3d/Match3DGame";

/** «Ферги Тайм»: a short 11-a-side match in landscape. It pays nothing by itself:
 * the server only records a match played to the end, for tasks and the «Путь
 * дебютанта». Those calls never get in the way of the match. */
export default function Match3DPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const session = useRef<Promise<number | null>>(Promise.resolve(null));

  const kickOff = () => {
    session.current = startFergieTime().then((r) => r.session_id, () => null);
  };
  const fullTime = () => {
    void session.current.then(async (id) => {
      if (id === null) return;
      try {
        await finishFergieTime(id);
      } catch {
        return;
      }
      void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      void queryClient.invalidateQueries({ queryKey: ["newbie"] });
    });
  };

  return <Match3DGame onExit={() => navigate("/play")} onKickOff={kickOff} onFullTime={fullTime} />;
}
