import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { acceptTacticoOpenChallenge, fetchTacticoOpenChallenge } from "@/api/tactico";
import { IconCoin, IconFlagCheckered } from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { hapticNotify } from "@/lib/telegram";

const STATUS_MESSAGES: Record<string, string> = {
  finished: "Этот вызов уже сыгран.",
  declined: "Этот вызов отклонён.",
  cancelled: "Этот вызов отменён создателем.",
  expired: "Срок действия этого вызова истёк.",
  in_progress: "Этот вызов уже принят — матч идёт.",
};

export default function TacticoOpenChallengePage() {
  const { matchId } = useParams<{ matchId: string }>();
  const id = Number(matchId);
  const navigate = useNavigate();
  const [error, setError] = useState<string | null>(null);

  const { data: preview, isLoading } = useQuery({
    queryKey: ["tactico-open-challenge", id],
    queryFn: () => fetchTacticoOpenChallenge(id),
    enabled: Number.isFinite(id),
  });

  const acceptMutation = useMutation({
    mutationFn: () => acceptTacticoOpenChallenge(id),
    onSuccess: (match) => {
      hapticNotify("success");
      navigate(`/play/tactico/matches/${match.id}`, { replace: true });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось принять вызов")),
  });

  if (isLoading) return null;
  if (!preview) {
    return (
      <div className="flex flex-col items-center gap-3 pt-16 text-center">
        <IconFlagCheckered size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">Вызов не найден.</p>
      </div>
    );
  }

  if (preview.is_own_challenge) {
    return (
      <div className="flex flex-col items-center gap-4 pt-16 text-center">
        <IconFlagCheckered size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">Это твой собственный вызов — дождись, пока кто-нибудь его примет.</p>
        <button
          onClick={() => navigate(`/play/tactico/matches/${preview.id}`)}
          className="rounded-xl bg-floodlight px-5 py-2.5 text-sm font-bold text-bg-base active:scale-95"
        >
          Открыть вызов
        </button>
      </div>
    );
  }

  if (preview.status !== "pending_accept") {
    return (
      <div className="flex flex-col items-center gap-3 pt-16 text-center">
        <IconFlagCheckered size={32} className="text-ink-mist-dim" />
        <p className="text-sm text-ink-mist">{STATUS_MESSAGES[preview.status] ?? "Этот вызов больше не активен."}</p>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-center gap-5 pt-10 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-full bg-accent/10">
        <IconFlagCheckered size={28} className="text-accent" />
      </div>
      <div>
        <h1 className="font-display text-xl font-bold text-ink-chalk">Вызов на матч в Тактико</h1>
        <p className="mt-1 text-sm text-ink-mist">от {preview.creator_name}</p>
      </div>

      {preview.stake_coins > 0 ? (
        <div className="flex flex-col items-center gap-1 rounded-2xl bg-bg-surface px-6 py-4">
          <span className="flex items-center gap-1.5 font-mono text-lg font-bold text-accent-lime">
            {preview.stake_coins} <IconCoin size={16} />
          </span>
          <p className="text-xs text-ink-mist-dim">
            ставка с каждой стороны · победитель заберёт {preview.stake_coins * 2}
          </p>
        </div>
      ) : (
        <p className="rounded-2xl bg-bg-surface px-6 py-4 text-sm text-ink-mist">Обычная игра, без ставки</p>
      )}

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <div className="flex gap-2">
        <button
          onClick={() => navigate("/play/tactico")}
          className="rounded-xl bg-white/5 px-5 py-2.5 text-sm font-bold text-ink-mist active:scale-95"
        >
          Отмена
        </button>
        <button
          onClick={() => acceptMutation.mutate()}
          disabled={acceptMutation.isPending}
          className="rounded-xl bg-accent-green px-5 py-2.5 text-sm font-bold text-bg-base active:scale-95 disabled:opacity-50"
        >
          {acceptMutation.isPending ? "Принимаем..." : "Согласиться"}
        </button>
      </div>
    </div>
  );
}
