import { useMutation, useQueryClient } from "@tanstack/react-query";
import { motion } from "framer-motion";
import { useState, type CSSProperties, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import { claimFanRewards, joinFanSide } from "@/api/fanBattle";
import RewardModal, { RewardCard, RewardCoins, RewardPack } from "@/components/common/RewardModal";
import { UserBadge } from "@/components/common/UserBadge";
import FanTug from "@/components/fans/FanTug";
import { IconChevronLeft, IconClock } from "@/components/icons";
import { skillByCode, useSkillCatalog } from "@/lib/cardSkills";
import { formatGameError } from "@/lib/errors";
import { FAN_BATTLE_QUERY_KEY, fanArt, pointsWord, sideByCode, useFanBattle } from "@/lib/fanBattle";
import { timeLeft, useMinuteTick } from "@/lib/halloween";
import type { FanBattleState, FanClaimResult, FanDay, FanMilestone, FanSide } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const MILESTONE_EMOJI: Record<FanMilestone["kind"], string> = { coins: "💰", skill_tokens: "🔮", pack: "🎴", badge: "📣" };

interface Reward {
  title: string;
  subtitle?: string;
  items: ReactNode[];
}

/** «⚔️ Битва фанатов»: pick a side, bring it points, win the days and the final. */
export default function FanBattlePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const now = useMinuteTick();
  const { data, isLoading } = useFanBattle({ poll: true });
  const [error, setError] = useState<string | null>(null);
  const [picked, setPicked] = useState<string | null>(null);
  const [reward, setReward] = useState<Reward | null>(null);
  const { data: skills } = useSkillCatalog();

  const join = useMutation({
    mutationFn: (side: string) => joinFanSide(side),
    onMutate: () => setError(null),
    onSuccess: (state) => {
      queryClient.setQueryData(FAN_BATTLE_QUERY_KEY, state);
      const side = sideByCode(state.sides, state.my_side);
      setPicked(null);
      if (side)
        setReward({
          title: `Ты за ${side.name}!`,
          subtitle: "Каждая игра, задание и сундук теперь приносят очки твоей стороне",
          items: [<span key="e" className="text-6xl">{side.emoji}</span>],
        });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось выбрать сторону")),
  });

  const claim = useMutation({
    mutationFn: claimFanRewards,
    onMutate: () => setError(null),
    onSuccess: (result) => {
      setReward(claimReward(result, (code) => skillByCode(skills?.skills, code)?.name ?? code));
      queryClient.invalidateQueries({ queryKey: FAN_BATTLE_QUERY_KEY });
      queryClient.invalidateQueries({ queryKey: ["profile", "me"] });
    },
    onError: (err) => setError(formatGameError(err, "Не удалось забрать награды")),
  });

  if (isLoading) return null;
  if (!data?.enabled || data.sides.length !== 2) {
    return (
      <div className="flex flex-col items-center gap-3 py-16 text-center">
        <span className="text-5xl">⚔️</span>
        <p className="font-display text-base font-bold text-ink-chalk">Битва фанатов ещё не началась</p>
        <button onClick={() => navigate("/")} className="text-sm text-accent-lime">На главную</button>
      </div>
    );
  }
  const mine = sideByCode(data.sides, data.my_side);
  const [a, b] = data.sides;
  const before = !data.active && !data.finished;
  const skyStyle = { "--fan-a": a.color, "--fan-b": b.color } as CSSProperties;

  return (
    <div className="flex flex-col gap-4 pb-24">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-xs text-ink-mist">
        <IconChevronLeft size={16} /> Назад
      </button>

      {/* Header: the whole event's tug-of-war */}
      <section className="fans-sky relative overflow-hidden rounded-3xl p-4 ring-1 ring-white/10" style={skyStyle}>
        {fanArt("banner") && (
          <img src={fanArt("banner")} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-50" />
        )}
        <div className="relative flex flex-col gap-4">
          <div>
            <h1 className="font-display text-2xl font-black uppercase leading-none tracking-wide text-white drop-shadow">⚔️ Битва фанатов</h1>
            <p className="mt-1 flex items-center gap-1 font-mono text-caption text-white/75">
              <IconClock size={12} />
              {before ? `старт через ${timeLeft(data.starts_at, now)}` : data.active ? `до финала ${timeLeft(data.ends_at, now)}` : "битва окончена"}
            </p>
          </div>
          <FanTug sides={data.sides} mine={data.my_side} />
          <div className="flex justify-between text-micro text-white/70">
            <span>{fmt(a.members)} фанатов</span>
            <span>{fmt(b.members)} фанатов</span>
          </div>
        </div>
      </section>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-300">{error}</p>}

      {/* Pick a side */}
      {!mine && data.can_join && (
        <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
          <div>
            <h2 className="font-display text-base font-bold text-ink-chalk">За кого болеешь?</h2>
            <p className="text-xs text-ink-mist">Сторону выбирают один раз — до конца битвы. Слабой стороне — бонус к очкам.</p>
          </div>
          <div className="grid grid-cols-2 gap-3">
            {data.sides.map((side) => (
              <SidePick key={side.code} side={side} selected={picked === side.code} onClick={() => setPicked(side.code)} />
            ))}
          </div>
          <button
            disabled={!picked || join.isPending}
            onClick={() => picked && join.mutate(picked)}
            className="rounded-2xl py-3 font-display text-sm font-black uppercase text-black disabled:bg-white/10 disabled:text-ink-mist"
            style={picked ? { background: sideByCode(data.sides, picked)?.color } : undefined}
          >
            {join.isPending ? "…" : picked ? `Я за ${sideByCode(data.sides, picked)?.name}!` : "Выбери сторону"}
          </button>
        </section>
      )}

      {/* Me */}
      {mine && (
        <section
          className="relative overflow-hidden rounded-3xl p-4 ring-1"
          style={{ background: `linear-gradient(135deg, ${mine.color}40, transparent 70%)`, borderColor: mine.color, boxShadow: `inset 0 0 0 1px ${mine.color}66` }}
        >
          <div className="flex items-center gap-3">
            <SideEmblem side={mine} size="lg" />
            <div className="min-w-0 flex-1">
              <p className="text-micro uppercase tracking-wide text-ink-mist">Ты за {mine.name}</p>
              <p className="font-display text-3xl font-black leading-none text-white">{fmt(data.my_points)}</p>
              <p className="text-xs text-ink-mist">
                {pointsWord(data.my_points)} твоей стороне{data.my_rank ? ` · #${data.my_rank} среди фанатов` : ""}
              </p>
            </div>
          </div>
          {mine.underdog_bonus_pct > 0 && data.active && (
            <p className="mt-3 rounded-xl bg-black/30 px-3 py-2 text-xs text-white">
              🛡️ Вас меньше — каждое очко засчитывается с бонусом +{mine.underdog_bonus_pct}%
            </p>
          )}
        </section>
      )}

      {/* Today's battle */}
      {data.active && (
        <section className="flex flex-col gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
          <div className="flex items-baseline justify-between gap-2">
            <h2 className="font-display text-base font-bold text-ink-chalk">Битва дня</h2>
            <span className="font-mono text-micro text-ink-mist">итог через {timeLeft(data.day_resets_at, now)}</span>
          </div>
          <FanTug sides={data.sides} mine={data.my_side} field="today_points" compact />
          <p className="text-xs text-ink-mist">
            Принеси за день {data.daily_min_points} {pointsWord(data.daily_min_points)} — и получишь{" "}
            <b className="text-ink-chalk">{fmt(data.daily_win_coins)}</b> монет за победу или{" "}
            <b className="text-ink-chalk">{fmt(data.daily_lose_coins)}</b> за бой.
          </p>
          {mine && (
            <Progress
              value={data.my_today_points}
              max={Math.max(1, data.daily_min_points)}
              color={mine.color}
              label={
                data.my_today_points >= data.daily_min_points
                  ? `✅ Сегодня ты в деле: ${fmt(data.my_today_points)} ${pointsWord(data.my_today_points)}`
                  : `Сегодня ${fmt(data.my_today_points)} из ${data.daily_min_points}`
              }
            />
          )}
        </section>
      )}

      {/* How to earn */}
      {!data.finished && (
        <section className="grid grid-cols-2 gap-2">
          <EarnChip
            emoji="🎮"
            title={`+${data.points_per_game} за игру`}
            text={data.games_daily_cap > 0 ? `сегодня ${data.games_points_today}/${data.games_daily_cap}` : "в любом режиме"}
            onClick={() => navigate("/play")}
          />
          <EarnChip emoji="📜" title={`+${data.points_per_task} за задание`} text={`сундук +${data.points_per_daily_chest} / +${data.points_per_weekly_chest}`} onClick={() => navigate("/tasks")} />
          {data.boss_name && (
            <EarnChip
              emoji="🕵️"
              wide
              title={`${data.boss_name}: очки ×${data.boss_multiplier}`}
              text="Выстой до свистка против босса «Контратаки» — и очки за игру умножатся"
              onClick={() => navigate("/play/kontra/boss")}
            />
          )}
        </section>
      )}

      {/* Milestones */}
      {data.milestones.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="px-1 font-display text-base font-bold text-ink-chalk">Награды за очки</h2>
          <div className="flex flex-col gap-2 rounded-3xl bg-bg-surface p-3 ring-1 ring-white/10">
            {data.milestones.map((m) => (
              <MilestoneRow key={m.points} m={m} mine={data.my_points} color={mine?.color ?? "#a3e635"} />
            ))}
          </div>
        </section>
      )}

      {/* Days */}
      {data.days.length > 0 && (
        <section className="flex flex-col gap-2">
          <h2 className="px-1 font-display text-base font-bold text-ink-chalk">Дни битвы</h2>
          <div className="grid grid-cols-7 gap-1.5">
            {data.days.map((d) => (
              <DayTile key={d.day} d={d} sides={data.sides} />
            ))}
          </div>
          <p className="px-1 text-micro text-ink-mist-dim">Цвет — кто выиграл день. 🎁 — награда ждёт, ✓ — забрана.</p>
        </section>
      )}

      {/* The final */}
      <FinalBlock data={data} />

      {/* Top fans */}
      {data.sides.some((s) => (data.top[s.code] ?? []).length > 0) && (
        <section className="flex flex-col gap-2">
          <h2 className="px-1 font-display text-base font-bold text-ink-chalk">Лучшие фанаты</h2>
          <div className="grid grid-cols-2 gap-2">
            {data.sides.map((side) => (
              <div key={side.code} className="flex flex-col gap-1 rounded-2xl bg-bg-surface p-3" style={{ boxShadow: `inset 0 2px 0 ${side.color}` }}>
                <span className="font-display text-xs font-black uppercase" style={{ color: side.color }}>
                  {side.emoji} {side.name}
                </span>
                {(data.top[side.code] ?? []).map((t, i) => (
                  <span key={t.user_id} className="flex items-center gap-1.5 text-xs">
                    <span className="w-4 font-mono text-ink-mist">{i + 1}</span>
                    <span className="min-w-0 flex-1 truncate text-ink-chalk">{t.name}</span>
                    <span className="font-mono text-ink-mist">{fmt(t.points)}</span>
                  </span>
                ))}
                {(data.top[side.code] ?? []).length === 0 && <span className="text-micro text-ink-mist-dim">пока пусто</span>}
              </div>
            ))}
          </div>
        </section>
      )}

      {/* «Капитаны» */}
      {data.collection && data.collection.total > 0 && (
        <section className="flex items-center gap-3 rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
          <span
            className="flex h-16 w-12 shrink-0 items-center justify-center rounded-xl text-2xl"
            style={{ background: `linear-gradient(180deg, ${mine?.color ?? a.color}, #111)` }}
          >
            👑
          </span>
          <div className="min-w-0 flex-1">
            <p className="font-display text-sm font-bold text-ink-chalk">«{data.collection.name}»</p>
            <p className="text-xs text-ink-mist">
              {data.collection.completed
                ? "Коллекция собрана — награда твоя!"
                : `Собрано ${data.collection.owned} из ${data.collection.total} · рамка в цветах твоей стороны`}
            </p>
          </div>
          <button onClick={() => navigate("/collection")} className="rounded-xl bg-white/10 px-3 py-2 text-xs font-semibold text-ink-chalk">
            Альбом
          </button>
        </section>
      )}

      {/* Claim */}
      {data.claimable > 0 && (
        <div className="fixed inset-x-0 bottom-20 z-30 mx-auto flex max-w-lg px-4">
          <button
            onClick={() => claim.mutate()}
            disabled={claim.isPending}
            className="fans-pulse w-full rounded-2xl bg-accent-lime py-3.5 font-display text-sm font-black uppercase text-black shadow-lg disabled:opacity-60"
          >
            {claim.isPending ? "…" : `🎁 Забрать награды (${data.claimable})`}
          </button>
        </div>
      )}

      {reward && (
        <RewardModal title={reward.title} subtitle={reward.subtitle} items={reward.items} buttonLabel="Вперёд!" onClose={() => setReward(null)} />
      )}
    </div>
  );
}

function claimReward(result: FanClaimResult, skillName: (code: string) => string): Reward {
  const items: ReactNode[] = [];
  if (result.coins) items.push(<RewardCoins key="c" amount={result.coins} />);
  result.skill_tokens.forEach((t, i) =>
    items.push(
      <p key={`t${i}`} className="text-sm font-semibold text-violet-200">
        🔮 Жетоны «{skillName(t.code)}» × {t.amount}
      </p>,
    ),
  );
  result.badges.forEach((badge) =>
    items.push(
      <p key={`b${badge.id}`} className="flex items-center gap-1.5 text-sm font-semibold text-amber-200">
        <UserBadge badge={badge} /> Значок «{badge.name}»
      </p>,
    ),
  );
  result.pack_names.forEach((name, i) => items.push(<RewardPack key={`p${i}`} name={name} />));
  result.cards.forEach((c) => items.push(<RewardCard key={`card-${c.id}`} card={c} />));
  return { title: "Награды твои!", subtitle: result.titles.join(" · "), items };
}

function SideEmblem({ side, size = "md" }: { side: FanSide; size?: "md" | "lg" }) {
  const art = fanArt(`side-${side.code}`);
  const box = size === "lg" ? "h-16 w-16 text-4xl" : "h-20 w-20 text-5xl";
  return art ? (
    <img src={art} alt="" className={`${box} shrink-0 rounded-2xl object-cover`} />
  ) : (
    <span
      className={`${box} flex shrink-0 items-center justify-center rounded-2xl`}
      style={{ background: `radial-gradient(circle at 30% 25%, ${side.color}, #0b0b0f 85%)`, boxShadow: `0 0 22px ${side.color}66` }}
    >
      {side.emoji}
    </span>
  );
}

function SidePick({ side, selected, onClick }: { side: FanSide; selected: boolean; onClick: () => void }) {
  return (
    <motion.button
      whileTap={{ scale: 0.96 }}
      onClick={onClick}
      className="flex flex-col items-center gap-2 rounded-2xl bg-black/30 p-3 text-center transition-shadow"
      style={{ boxShadow: selected ? `0 0 0 2px ${side.color}, 0 0 24px ${side.color}88` : `inset 0 0 0 1px ${side.color}55` }}
    >
      <SideEmblem side={side} />
      <span className="font-display text-base font-black uppercase" style={{ color: side.color }}>
        {side.name}
      </span>
      <span className="text-micro text-ink-mist">{fmt(side.members)} фанатов</span>
      {side.underdog_bonus_pct > 0 && (
        <span className="rounded-full bg-white/10 px-2 py-0.5 text-micro font-bold text-white">+{side.underdog_bonus_pct}% к очкам</span>
      )}
    </motion.button>
  );
}

function Progress({ value, max, color, label }: { value: number; max: number; color: string; label: string }) {
  return (
    <div className="flex flex-col gap-1">
      <span className="block h-2 overflow-hidden rounded-full bg-white/10">
        <span className="block h-full rounded-full" style={{ width: `${Math.min(100, (value * 100) / max)}%`, background: color }} />
      </span>
      <span className="text-micro text-ink-mist">{label}</span>
    </div>
  );
}

function EarnChip({ emoji, title, text, onClick, wide }: { emoji: string; title: string; text: string; onClick: () => void; wide?: boolean }) {
  return (
    <button
      onClick={onClick}
      className={`flex items-center gap-2 rounded-2xl bg-bg-surface px-3 py-2.5 text-left ring-1 ring-white/10 active:scale-[0.98] ${wide ? "col-span-2" : ""}`}
    >
      <span className="text-xl">{emoji}</span>
      <span className="min-w-0">
        <span className="block font-display text-xs font-bold leading-tight text-ink-chalk">{title}</span>
        <span className="block text-micro text-ink-mist">{text}</span>
      </span>
    </button>
  );
}

function MilestoneRow({ m, mine, color }: { m: FanMilestone; mine: number; color: string }) {
  const art = m.kind === "badge" ? fanArt("badge-fan") : undefined;
  return (
    <div className={`flex items-center gap-3 rounded-2xl px-2 py-1.5 ${m.reached ? "bg-white/5" : ""}`}>
      {art ? (
        <img src={art} alt="" className="h-10 w-10 rounded-xl object-cover" />
      ) : (
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-white/5 text-xl">
          {m.badge ? m.badge.icon : MILESTONE_EMOJI[m.kind]}
        </span>
      )}
      <div className="min-w-0 flex-1">
        <p className="line-clamp-2 font-display text-xs font-bold leading-tight text-ink-chalk">{m.title}</p>
        <span className="mt-1 block h-1.5 overflow-hidden rounded-full bg-white/10">
          <span className="block h-full rounded-full" style={{ width: `${Math.min(100, (mine * 100) / m.points)}%`, background: color }} />
        </span>
      </div>
      <span className="w-16 shrink-0 text-right font-mono text-micro text-ink-mist">
        {m.claimed ? "✓ твоё" : m.reached ? "🎁" : `${fmt(m.points)}`}
      </span>
    </div>
  );
}

function DayTile({ d, sides }: { d: FanDay; sides: FanSide[] }) {
  const winner = d.winner === "draw" ? null : sideByCode(sides, d.winner);
  const day = new Date(`${d.day}T12:00:00`);
  const label = `${String(day.getDate()).padStart(2, "0")}.${String(day.getMonth() + 1).padStart(2, "0")}`;
  const background = !d.finished
    ? "rgba(255,255,255,0.08)"
    : d.winner === "draw"
      ? `linear-gradient(135deg, ${sides[0].color} 50%, ${sides[1].color} 50%)`
      : winner?.color ?? "rgba(255,255,255,0.08)";
  return (
    <div
      className={`relative flex aspect-square flex-col items-center justify-center rounded-xl text-center ${d.finished ? "" : "border border-dashed border-white/30"}`}
      style={{ background }}
      title={sides.map((s) => `${s.name}: ${d.points[s.code] ?? 0}`).join(" · ")}
    >
      <span className={`font-mono text-[10px] font-bold ${d.finished ? "text-black/80" : "text-ink-mist"}`}>{label}</span>
      <span className="text-xs leading-none">
        {!d.finished ? "⏳" : d.reward_coins > 0 ? (d.claimed ? "✓" : "🎁") : winner ? winner.emoji : "🤝"}
      </span>
    </div>
  );
}

function FinalBlock({ data }: { data: FanBattleState }) {
  const final = data.final;
  if (!final) {
    return (
      <section className="flex flex-col gap-2 rounded-3xl bg-gradient-to-br from-amber-500/20 via-bg-surface to-bg-surface p-4 ring-1 ring-amber-400/30">
        <h2 className="font-display text-base font-bold text-amber-200">🏆 Финал</h2>
        <p className="text-xs text-ink-mist">
          Побеждает сторона, набравшая больше очков за всю битву. Фанаты с {data.final_min_points}+ очками получат{" "}
          <b className="text-ink-chalk">{fmt(data.final_win_coins)}</b> монет и значок чемпиона за победу или{" "}
          <b className="text-ink-chalk">{fmt(data.final_lose_coins)}</b> за поражение.
          {data.top_n > 0 && data.top_bonus_coins > 0 && ` Топ-${data.top_n} фанатов каждой стороны — ещё +${fmt(data.top_bonus_coins)}.`}
        </p>
      </section>
    );
  }
  const winner = final.winner === "draw" ? null : sideByCode(data.sides, final.winner);
  return (
    <section
      className="flex flex-col items-center gap-2 rounded-3xl p-5 text-center ring-1 ring-amber-400/40"
      style={{ background: `radial-gradient(circle at 50% 0%, ${winner?.color ?? "#f59e0b"}66, #0b0b0f 75%)` }}
    >
      <span className="text-5xl">{winner ? winner.emoji : "🤝"}</span>
      <h2 className="font-display text-xl font-black uppercase text-white">{winner ? `Победа: ${winner.name}!` : "Ничья!"}</h2>
      {final.eligible ? (
        <p className="text-xs text-white/80">
          Твоя награда: {fmt(final.coins)} монет{final.badge ? ` и значок «${final.badge.name}»` : ""}
          {final.pack_name ? ` и пак «${final.pack_name}»` : ""}
          {final.my_rank ? ` · ты #${final.my_rank} среди фанатов!` : ""}
          {final.claimed ? " — забрана ✓" : ""}
        </p>
      ) : (
        <p className="text-xs text-white/70">Для награды финала нужно было набрать {data.final_min_points} очков.</p>
      )}
    </section>
  );
}
