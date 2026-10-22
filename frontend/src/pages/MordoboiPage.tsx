import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchFeatureFlags } from "@/api/featureFlags";
import {
  createMordoboiBotMatch,
  createMordoboiChallenge,
  fetchMordoboiBoxer,
  fetchMordoboiInfo,
  fetchMordoboiMatches,
  fetchMordoboiStats,
  saveMordoboiBoxer,
} from "@/api/mordoboi";
import { searchUsers } from "@/api/profile";
import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconBoxingGlove, IconHelp, IconPlay, IconTrophy, IconUsers } from "@/components/icons";
import { ACTION_META, ACTION_ORDER } from "@/components/mordoboi/mordoboiMeta";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { RARITY_GRADIENTS } from "@/lib/rarity";
import type { MordoboiBoxerOption, MordoboiInfo, MordoboiMatch, Rarity, UserPublic } from "@/types";

type Tab = "pending" | "active" | "history";

const STATUS_LABELS: Record<string, string> = {
  pending_accept: "Ожидает ответа", in_progress: "Идёт", finished: "Завершён",
  declined: "Отклонён", cancelled: "Отменён", expired: "Истёк",
};
const OPPONENT_LABELS: Record<string, string> = { bot: "Против бота", friend: "Против друга", online: "Онлайн" };
const RESULT_LABELS: Record<string, string> = { win: "Победа", draw: "Ничья", loss: "Поражение" };

export default function MordoboiPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [tab, setTab] = useState<Tab>("active");
  const [error, setError] = useState<string | null>(null);
  const [sheet, setSheet] = useState<null | "bot" | "friend" | "boxer" | "rules">(null);

  const { data: info } = useQuery({ queryKey: ["mordoboi-info"], queryFn: fetchMordoboiInfo });
  const { data: stats } = useQuery({ queryKey: ["mordoboi-stats"], queryFn: fetchMordoboiStats });
  const { data: boxer } = useQuery({ queryKey: ["mordoboi-boxer"], queryFn: fetchMordoboiBoxer });
  const { data: matches, isLoading } = useQuery({ queryKey: ["mordoboi-matches"], queryFn: fetchMordoboiMatches });
  const { data: flags } = useQuery({ queryKey: ["feature-flags"], queryFn: fetchFeatureFlags, refetchInterval: 30000 });
  const activeMatch = matches?.find((m) => m.status === "in_progress");

  const onCreated = (match: MordoboiMatch) => {
    queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    queryClient.invalidateQueries({ queryKey: ["mordoboi-matches"] });
    navigate(`/play/mordoboi/matches/${match.id}`);
  };
  const bot = useMutation({
    mutationFn: (difficulty: "easy" | "hard") => createMordoboiBotMatch(difficulty),
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось начать бой")),
  });
  const challenge = useMutation({
    mutationFn: (receiverId: number) => createMordoboiChallenge(receiverId),
    onSuccess: onCreated,
    onError: (err) => setError(formatGameError(err, "Не удалось отправить вызов")),
  });
  const chooseBoxer = useMutation({
    mutationFn: (cardId: number) => saveMordoboiBoxer(cardId),
    onSuccess: (b) => { queryClient.setQueryData(["mordoboi-boxer"], b); setSheet(null); },
    onError: (err) => setError(formatGameError(err, "Не удалось выбрать боксёра")),
  });

  const filtered = (matches ?? []).filter((m) => {
    if (tab === "pending") return m.status === "pending_accept";
    if (tab === "active") return m.status === "in_progress";
    return ["finished", "declined", "cancelled", "expired"].includes(m.status);
  });
  const disabled = info && !info.enabled;

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="flex items-center gap-2 font-display text-xl font-bold text-ink-chalk">
          <IconBoxingGlove size={20} className="text-yellow-400" />
          Мордобой
        </h1>
        <button
          onClick={() => setSheet("rules")}
          aria-label="Правила"
          className="flex h-8 w-8 items-center justify-center rounded-full bg-white/5 text-ink-mist active:scale-95"
        >
          <IconHelp size={15} />
        </button>
      </div>

      {disabled && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Режим сейчас выключен — новые бои недоступны.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      {boxer?.selected ? (
        <button onClick={() => setSheet("boxer")} className="rounded-3xl bg-gradient-to-br from-yellow-500/20 to-bg-surface p-3 text-left active:scale-[0.99]">
          <span className="mb-2 block font-mono text-micro uppercase tracking-wider text-yellow-300">Твой боксёр · сменить</span>
          <BoxerRow option={boxer.selected} />
        </button>
      ) : boxer ? (
        <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Нужна хотя бы одна карточка в коллекции.</p>
      ) : null}

      {stats && (
        <button onClick={() => navigate("/ranking?metric=mordoboi_rating")} className="flex items-center justify-between rounded-2xl bg-bg-surface px-4 py-3 text-left active:scale-[0.98]">
          <span className="flex items-center gap-2 text-xs text-ink-mist">
            <IconTrophy size={14} className="text-yellow-400" />
            Рейтинг Мордобоя
          </span>
          <span className="font-mono text-sm font-bold text-ink-chalk">
            {stats.mordoboi_rating}
            {stats.mordoboi_rank ? <span className="ml-1.5 text-caption font-normal text-ink-mist">#{stats.mordoboi_rank}</span> : null}
          </span>
        </button>
      )}
      {info && (
        <p className="text-caption text-ink-mist-dim">
          Наградных боёв сегодня: {info.rewarded_today}/{info.daily_limit} · победа {info.reward_win} монет, нокаут +{info.reward_ko_bonus}
        </p>
      )}

      {activeMatch ? (
        <button
          onClick={() => navigate(`/play/mordoboi/matches/${activeMatch.id}`)}
          className="flex items-center justify-center gap-2 rounded-2xl bg-accent-green py-4 text-base font-bold text-bg-base active:scale-95"
        >
          <IconPlay size={19} />
          {activeMatch.can_pick ? "Твой удар — на ринг" : "Вернуться на ринг"}
        </button>
      ) : (
        <>
          {flags?.matchmaking_enabled !== false && (
            <button
              onClick={() => navigate("/play/mordoboi/search")}
              disabled={disabled || !boxer?.selected}
              className="flex items-center justify-center gap-2 rounded-2xl bg-yellow-500 py-5 text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
            >
              <IconPlay size={20} />
              Найти соперника
            </button>
          )}
          <div className="flex gap-2">
            <button
              onClick={() => setSheet("bot")}
              disabled={disabled || bot.isPending || !boxer?.selected}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95 disabled:opacity-50"
            >
              <IconPlay size={14} />
              С ботом
            </button>
            <button
              onClick={() => setSheet("friend")}
              disabled={disabled || !boxer?.selected}
              className="flex flex-1 items-center justify-center gap-1.5 rounded-2xl bg-white/5 py-3 text-xs font-semibold text-ink-mist active:scale-95 disabled:opacity-50"
            >
              <IconUsers size={14} />
              Вызвать друга
            </button>
          </div>
          <p className="-mt-1 text-center text-caption text-ink-mist-dim">Онлайн-бой даёт рейтинг ×2, бой с другом — без рейтинга</p>
        </>
      )}

      <div className="flex gap-2">
        {(["pending", "active", "history"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`flex-1 rounded-xl py-2 text-xs font-semibold ${tab === t ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
          >
            {{ pending: "Вызовы", active: "Идут", history: "История" }[t]}
          </button>
        ))}
      </div>
      {isLoading && <ListSkeleton />}
      {!isLoading && !filtered.length && (
        <EmptyState icon={IconBoxingGlove} title="Боёв нет" description="Сразись с ботом или вызови друга" />
      )}
      <div className="flex flex-col gap-2.5">
        {filtered.map((m) => (
          <button
            key={m.id}
            onClick={() => navigate(`/play/mordoboi/matches/${m.id}`)}
            className="flex items-center justify-between rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.98]"
          >
            <div className="min-w-0">
              <p className="truncate font-display text-sm font-bold text-ink-chalk">{m.opponent_name}</p>
              <p className="mt-0.5 text-caption text-ink-mist">
                {OPPONENT_LABELS[m.opponent_type]} · {STATUS_LABELS[m.status]}
                {m.status === "in_progress" && (m.can_pick ? " · твой удар" : " · ждём соперника")}
              </p>
            </div>
            {m.result && <span className="text-xs font-bold text-ink-chalk">{RESULT_LABELS[m.result]}</span>}
          </button>
        ))}
      </div>

      {sheet === "bot" && (
        <Sheet onClose={() => setSheet(null)} title="Выбери соперника">
          <button onClick={() => { setSheet(null); bot.mutate("easy"); }} className="rounded-2xl bg-white/5 p-3 text-left active:scale-[0.98]">
            <span className="block text-sm font-bold text-ink-chalk">Лёгкий бот</span>
            <span className="block text-caption text-ink-mist">
              Машет наугад · {info ? `${Math.round((info.reward_win * info.easy_reward_pct) / 100)} монет за победу · ` : ""}рейтинг максимум +1
            </span>
          </button>
          <button onClick={() => { setSheet(null); bot.mutate("hard"); }} className="rounded-2xl border border-yellow-400/30 bg-yellow-500/10 p-3 text-left active:scale-[0.98]">
            <span className="block text-sm font-bold text-ink-chalk">Сильный бот</span>
            <span className="block text-caption text-ink-mist">
              Читает твои привычки и добивает уставших · {info ? `${info.reward_win} монет за победу` : "полная награда"}
            </span>
          </button>
        </Sheet>
      )}
      {sheet === "friend" && (
        <ChallengeSheet onClose={() => setSheet(null)} onPick={(u) => { setSheet(null); challenge.mutate(u.id); }} />
      )}
      {sheet === "boxer" && boxer && (
        <Sheet onClose={() => setSheet(null)} title="Выбери боксёра">
          <p className="-mt-1 text-caption text-ink-mist">
            Атака и «силовая» позиция — мощь хука и апперкота, рейтинг и фланг — скорость джеба и уклонов, защита — меньше урона, рейтинг — выносливость.
          </p>
          <div className="flex max-h-[55vh] flex-col gap-2 overflow-y-auto">
            {boxer.options.map((o) => (
              <button
                key={o.card.user_card_id}
                onClick={() => o.card.user_card_id && chooseBoxer.mutate(o.card.user_card_id)}
                className={`rounded-2xl p-2 text-left active:scale-[0.98] ${o.card.user_card_id === boxer.selected?.card.user_card_id ? "bg-yellow-500/15 ring-1 ring-yellow-400/40" : "bg-white/5"}`}
              >
                <BoxerRow option={o} />
              </button>
            ))}
          </div>
        </Sheet>
      )}
      {sheet === "rules" && <RulesSheet info={info} onClose={() => setSheet(null)} />}
    </div>
  );
}

function BoxerRow({ option }: { option: MordoboiBoxerOption }) {
  const { card, stats } = option;
  return (
    <div className="flex items-center gap-3">
      <span className={`h-14 w-11 shrink-0 overflow-hidden rounded-xl bg-gradient-to-b p-[2px] ${RARITY_GRADIENTS[card.rarity as Rarity] ?? ""}`}>
        <span className="flex h-full w-full items-center justify-center overflow-hidden rounded-[10px] bg-bg-base">
          {card.image_path ? (
            <img src={staticUrl(card.image_path)} alt="" className="h-full w-full object-cover object-top" />
          ) : (
            <span className="text-xs font-bold text-ink-mist">{card.display_name.slice(0, 2)}</span>
          )}
        </span>
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate font-display text-sm font-bold text-ink-chalk">{card.display_name}</span>
        <span className="block text-caption text-ink-mist">{card.position} · {card.rating}</span>
        <span className="mt-0.5 flex gap-3 font-mono text-micro text-ink-mist-dim">
          <span>💪 {stats.power}</span>
          <span>⚡ {stats.speed}</span>
          <span>🛡 {stats.guard}</span>
          <span>🔋 {stats.max_stamina}</span>
        </span>
      </span>
    </div>
  );
}

function Sheet({ title, onClose, children }: { title: string; onClose: () => void; children: React.ReactNode }) {
  return (
    <div className="fixed inset-0 z-50 flex items-end bg-black/60" onClick={onClose}>
      <div className="safe-bottom flex w-full flex-col gap-2 rounded-t-3xl bg-bg-base p-5" onClick={(e) => e.stopPropagation()}>
        <p className="mb-1 font-display text-base font-bold text-ink-chalk">{title}</p>
        {children}
      </div>
    </div>
  );
}

function ChallengeSheet({ onClose, onPick }: { onClose: () => void; onPick: (user: UserPublic) => void }) {
  const [query, setQuery] = useState("");
  const { data: results } = useQuery({
    queryKey: ["user-search-mordoboi", query],
    queryFn: () => searchUsers(query),
    enabled: query.length >= 2,
  });
  return (
    <Sheet onClose={onClose} title="Вызвать друга">
      <input
        value={query}
        onChange={(e) => setQuery(e.target.value)}
        placeholder="Введи имя пользователя..."
        className="w-full rounded-xl bg-bg-surface px-4 py-2.5 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
      />
      <div className="flex max-h-64 flex-col gap-2 overflow-y-auto">
        {results?.map((u) => (
          <button
            key={u.id}
            onClick={() => onPick(u)}
            className="flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2 text-left text-sm text-ink-chalk active:scale-[0.98]"
          >
            <IconUsers size={14} className="text-ink-mist-dim" />
            {u.username ?? u.first_name ?? `#${u.id}`}
          </button>
        ))}
        {query.length >= 2 && !results?.length && <p className="text-xs text-ink-mist-dim">Никого не найдено</p>}
      </div>
    </Sheet>
  );
}

/** Every number comes from /mordoboi/info (GameConfig + engine). */
function RulesSheet({ info, onClose }: { info?: MordoboiInfo; onClose: () => void }) {
  return (
    <Sheet onClose={onClose} title="Правила Мордобоя">
      <div className="flex max-h-[65vh] flex-col gap-3 overflow-y-auto text-xs text-ink-mist">
        <p>
          {info?.rounds ?? 3} раунда по {info?.exchanges_per_round ?? 4} обмена. В каждом обмене вы с соперником тайно выбираете
          действие — открываются они одновременно. HP {info?.base_hp ?? 100}: кто упал до нуля — нокаут. Иначе после последнего
          раунда судьи ставят 10:9 за раунд тому, кто нанёс больше урона.
        </p>
        <div className="flex flex-col gap-1.5">
          {ACTION_ORDER.map((a) => (
            <div key={a} className="flex items-center gap-2 rounded-xl bg-white/5 px-3 py-2">
              <span className="text-xl">{ACTION_META[a].emoji}</span>
              <span className="min-w-0 flex-1">
                <span className="block font-bold text-ink-chalk">{ACTION_META[a].label}</span>
                <span className="block">{ACTION_META[a].hint}</span>
              </span>
              <span className="text-right font-mono text-micro">
                {info?.damage[a] ? <span className="block">урон {info.damage[a]}</span> : null}
                <span className="block">🔋 {info?.stamina_cost[a] ?? "—"}</span>
              </span>
            </div>
          ))}
        </div>
        <p>Хук бьёт джеб, апперкот бьёт хук, джеб опережает апперкот. Одинаковые удары — размен. Без выносливости тяжёлые удары недоступны, а уставший бьёт слабее — блок всегда доступен и восстанавливает силы. Между раундами угол возвращает часть выносливости.</p>
        {info && (
          <p>
            Награда: победа {info.reward_win}, ничья {info.reward_draw}, поражение {info.reward_loss} монет, за нокаут +{info.reward_ko_bonus}.
            Наградных боёв в день: {info.daily_limit}. С другом на удар {info.move_timeout_hours} ч, онлайн — {info.live_move_seconds} с;
            пропустил — бьёт автопилот, после {info.max_auto_moves} пропусков подряд — поражение.
          </p>
        )}
      </div>
    </Sheet>
  );
}
