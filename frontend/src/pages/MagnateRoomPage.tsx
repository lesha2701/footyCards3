import { useMutation, useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchMagnateRoom, joinMagnateRoom } from "@/api/magnate";
import { IconStadium } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

/** Landing page of an invite link (bot deep link magnate_<code>). */
export default function MagnateRoomPage() {
  const { code = "" } = useParams<{ code: string }>();
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const { data: room, isLoading, isError } = useQuery({
    queryKey: ["magnate-room", code],
    queryFn: () => fetchMagnateRoom(code),
    enabled: !!code,
    refetchInterval: 3000,
  });

  useEffect(() => {
    if (room?.is_member) navigate(`/play/magnate/matches/${room.id}`, { replace: true });
  }, [room, navigate]);

  const join = useMutation({
    mutationFn: () => joinMagnateRoom(code),
    onSuccess: (m) => {
      hapticNotify("success");
      navigate(`/play/magnate/matches/${m.id}`, { replace: true });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось занять место")),
  });

  if (isLoading) return null;
  if (isError || !room) {
    return (
      <div className="flex flex-col items-center gap-3 pt-16 text-center">
        <IconStadium size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">Комната не найдена.</p>
      </div>
    );
  }

  const open = room.status === "lobby" && room.players.length < room.seats_total;
  return (
    <div className="flex flex-col items-center gap-5 pt-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10">
        <IconStadium size={28} className="text-accent" />
      </div>
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">«Футбольный магнат»</h1>
        <p className="mt-1 text-sm text-ink-mist">{room.creator_name} зовёт за стол</p>
      </div>
      <div className="w-full max-w-xs rounded-2xl bg-bg-surface px-4 py-3 text-left">
        <p className="mb-1 text-caption text-ink-mist-dim">За столом {room.players.length}/{room.seats_total}</p>
        {room.players.map((name, i) => (
          <p key={i} className="truncate text-sm text-ink-chalk">{name}</p>
        ))}
      </div>
      {!open && (
        <p className="text-sm text-ink-mist">
          {room.status === "lobby" ? "Все места заняты." : room.status === "cancelled" ? "Комната закрыта." : "Партия уже началась."}
        </p>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      <div className="flex gap-2">
        <button
          onClick={() => navigate("/play/magnate")}
          className="rounded-xl bg-white/5 px-5 py-2.5 text-sm font-bold text-ink-mist active:scale-95"
        >
          {open ? "Отмена" : "К игре"}
        </button>
        {open && (
          <button
            onClick={() => join.mutate()}
            disabled={join.isPending}
            className="rounded-xl bg-accent-green px-5 py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
          >
            {join.isPending ? "Садимся..." : "Занять место"}
          </button>
        )}
      </div>
    </div>
  );
}
