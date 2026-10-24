import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { createMagnateBotMatch, createMagnateRoom, fetchMagnateInfo, fetchMagnateMatches, joinMagnateLobby } from "@/api/magnate";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconChevronLeft, IconCoin, IconHelp, IconPlay, IconStadium, IconTrophy, IconUsers } from "@/components/icons";
import MagnateRulesModal from "@/components/magnate/MagnateRulesModal";
import { MODE_LABELS } from "@/components/magnate/magnateMeta";
import GameHero from "@/components/common/GameHero";
import { formatGameError } from "@/lib/errors";
import type { MagnateMatch } from "@/types";

const STATUS_LABELS: Record<string, string> = {
  lobby: "Ждёт игроков", in_progress: "Идёт", finished: "Завершена", cancelled: "Отменена",
};

export default function MagnatePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [rulesOpen, setRulesOpen] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const { data: info } = useQuery({ queryKey: ["magnate-info"], queryFn: fetchMagnateInfo });
  const { data: matches, isLoading } = useQuery({ queryKey: ["magnate-matches"], queryFn: fetchMagnateMatches });

  const open = (m: MagnateMatch) => {
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    queryClient.invalidateQueries({ queryKey: ["magnate-info"] });
    queryClient.setQueryData(["magnate-match", m.id], m);
    navigate(`/play/magnate/matches/${m.id}`);
  };
  const start = useMutation({
    mutationFn: (kind: "bot" | "public" | "private") =>
      ({ bot: createMagnateBotMatch, public: joinMagnateLobby, private: createMagnateRoom })[kind](),
    onSuccess: open,
    onError: (err) => setError(formatGameError(err, "Не удалось начать партию")),
  });

  const activeId = info?.active_match_id;
  const rewards = info?.place_rewards ?? [];

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center gap-2">
        <button onClick={() => navigate("/play")} className="rounded-full bg-white/5 p-2 text-ink-mist active:scale-95" aria-label="Назад">
          <IconChevronLeft size={16} />
        </button>
        <div className="min-w-0 flex-1">
          <GameHero game="magnate" title="Футбольный магнат">
            <button
              onClick={() => setRulesOpen(true)}
              aria-label="Правила"
              className="flex h-8 w-8 items-center justify-center rounded-full bg-black/35 text-ink-chalk active:scale-95"
            >
              <IconHelp size={15} />
            </button>
          </GameHero>
        </div>
      </div>

      <p className="text-xs leading-relaxed text-ink-mist">
        Покупай клубы и стадионы, собирай страны целиком, строй Трибуны и Арены и собирай аренду с соперников. Четыре
        игрока, {info?.max_rounds ?? "—"} кругов или {info?.time_limit_minutes ?? "—"} минут — побеждает самый богатый.
      </p>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {info && (
        <div className="grid grid-cols-2 gap-2">
          <div className="rounded-2xl bg-bg-surface px-3 py-2.5">
            <p className="flex items-center gap-1.5 text-caption text-ink-mist">
              <IconTrophy size={12} className="text-accent-lime" /> Побед
            </p>
            <p className="font-mono text-base font-bold text-ink-chalk">{info.wins}</p>
          </div>
          <div className="rounded-2xl bg-bg-surface px-3 py-2.5">
            <p className="flex items-center gap-1.5 text-caption text-ink-mist">
              <IconCoin size={12} className="text-accent-lime" /> Наградных сегодня
            </p>
            <p className="font-mono text-base font-bold text-ink-chalk">{info.rewarded_today}/{info.daily_limit}</p>
          </div>
          <p className="col-span-2 text-caption text-ink-mist-dim">
            Награда по месту: {rewards.map((r, i) => `${i + 1}-е ${r}`).join(" · ")} монет · с одними ботами — {info.bot_reward_pct}%
          </p>
        </div>
      )}

      {activeId ? (
        <button
          onClick={() => navigate(`/play/magnate/matches/${activeId}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base active:scale-95"
        >
          <IconPlay size={19} />
          Вернуться к партии
        </button>
      ) : (
        <div className="flex flex-col gap-2">
          <button
            onClick={() => start.mutate("bot")}
            disabled={start.isPending}
            className="flex items-center gap-3 rounded-2xl bg-floodlight p-4 text-left text-bg-base active:scale-[0.98] disabled:opacity-60"
          >
            <IconPlay size={22} />
            <span>
              <span className="block font-display text-base font-bold">Против 3 ботов</span>
              <span className="block text-caption opacity-80">Сразу за стол, боты ходят мгновенно</span>
            </span>
          </button>
          <button
            onClick={() => start.mutate("public")}
            disabled={start.isPending}
            className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98] disabled:opacity-60"
          >
            <IconStadium size={22} className="text-accent-cyan" />
            <span>
              <span className="block font-display text-sm font-bold text-ink-chalk">Онлайн-лобби на 4</span>
              <span className="block text-caption text-ink-mist">
                Ждём игроков {info?.lobby_wait_seconds ?? "—"} с, свободные места займут боты
              </span>
            </span>
          </button>
          <button
            onClick={() => start.mutate("private")}
            disabled={start.isPending}
            className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98] disabled:opacity-60"
          >
            <IconUsers size={22} className="text-accent-lime" />
            <span>
              <span className="block font-display text-sm font-bold text-ink-chalk">Комната для друзей</span>
              <span className="block text-caption text-ink-mist">Отправь ссылку-приглашение в чат и начни, когда соберётесь</span>
            </span>
          </button>
        </div>
      )}

      <p className="mt-1 font-display text-sm font-bold text-ink-chalk">История</p>
      {isLoading && <ListSkeleton />}
      {!isLoading && !matches?.length && (
        <EmptyState icon={IconStadium} title="Партий пока нет" description="Сыграй с ботами, чтобы освоиться" />
      )}
      <div className="flex flex-col gap-2">
        {matches?.map((m) => (
          <button
            key={m.id}
            onClick={() => navigate(`/play/magnate/matches/${m.id}`)}
            className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]"
          >
            <span className="min-w-0">
              <span className="block text-sm font-semibold text-ink-chalk">{MODE_LABELS[m.mode]}</span>
              <span className="block text-caption text-ink-mist">
                {STATUS_LABELS[m.status]}
                {m.left && " · ты вышел"}
                {" · "}
                {new Date(m.created_at).toLocaleString("ru-RU", { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" })}
              </span>
            </span>
            {m.my_place !== null && (
              <span className="text-right">
                <span className="block font-display text-sm font-bold text-ink-chalk">{m.my_place}-е место</span>
                {m.reward_coins > 0 && (
                  <span className="flex items-center justify-end gap-1 font-mono text-caption text-accent-lime">
                    +{m.reward_coins} <IconCoin size={10} />
                  </span>
                )}
              </span>
            )}
          </button>
        ))}
      </div>

      <MagnateRulesModal open={rulesOpen} onClose={() => setRulesOpen(false)} info={info} />
    </div>
  );
}
