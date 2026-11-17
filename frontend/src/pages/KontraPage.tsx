import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { autoKontraSquad, claimKontraLeague, fetchKontraHub, fetchKontraSquad, saveKontraSquad, setKontraTactic } from "@/api/kontra";
import { fetchMyProfile } from "@/api/profile";
import { IconCoin } from "@/components/icons";
import TacticPicker from "@/components/kontra/TacticPicker";
import { useAuthStore } from "@/store/authStore";
import { Skeleton } from "@/components/common/Skeleton";
import FighterCard from "@/components/kontra/FighterCard";
import { ROLE_FILTERS, TIER_LABELS } from "@/components/kontra/kontraMeta";
import GameHero from "@/components/common/GameHero";
import { formatGameError } from "@/lib/errors";
import { hapticNotify, hapticSelection } from "@/lib/telegram";
import type { KontraFighter, KontraSquad, KontraTacticCode } from "@/types";

/** «Контратака»: the squad (also the arena defence) as a stage of five
 *  with the leader in the middle, the collection below, and the two modes. */
export default function KontraPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [selected, setSelected] = useState<number | null>(null); // a squad card id
  const [role, setRole] = useState("all");
  const [error, setError] = useState<string | null>(null);
  const { data: hub } = useQuery({ queryKey: ["kontra-hub"], queryFn: fetchKontraHub });
  const { data: squad } = useQuery({ queryKey: ["kontra-squad"], queryFn: fetchKontraSquad });

  const apply = (s: KontraSquad) => {
    queryClient.setQueryData(["kontra-squad"], s);
    setError(null);
  };
  const save = useMutation({
    mutationFn: ({ cards, leader }: { cards: number[]; leader: number }) => saveKontraSquad(cards, leader),
    onSuccess: apply,
    onError: (err) => setError(formatGameError(err, "Не удалось сохранить отряд")),
  });
  const auto = useMutation({ mutationFn: autoKontraSquad, onSuccess: apply });
  const tactic = useMutation({
    mutationFn: (code: KontraTacticCode | null) => setKontraTactic(code),
    onSuccess: (sq) => { apply(sq); queryClient.invalidateQueries({ queryKey: ["kontra-arena"] }); },
  });
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const claim = useMutation({
    mutationFn: claimKontraLeague,
    onSuccess: (h) => {
      hapticNotify("success");
      queryClient.setQueryData(["kontra-hub"], h);
      fetchMyProfile().then((p) => updateBalance(p.balance)).catch(() => undefined);
    },
    onError: (err) => setError(formatGameError(err, "Не удалось забрать награду")),
  });

  if (!squad) {
    return (
      <div className="flex flex-col gap-3">
        <Skeleton className="h-7 w-40" />
        <Skeleton className="h-40 w-full rounded-3xl" />
        <div className="grid grid-cols-2 gap-2"><Skeleton className="h-16 rounded-2xl" /><Skeleton className="h-16 rounded-2xl" /></div>
        <div className="grid grid-cols-4 gap-1">{Array.from({ length: 8 }, (_, i) => <Skeleton key={i} className="aspect-[3/4] rounded-2xl" />)}</div>
      </div>
    );
  }
  const ids = squad.fighters.map((f) => f.card.card_id);
  const leader = squad.leader_id ?? ids[0];
  // Leader in the middle, the others stepping down on both sides.
  const others = squad.fighters.filter((f) => f.card.card_id !== leader);
  const lead = squad.fighters.find((f) => f.card.card_id === leader);
  const stage = [others[2], others[0], lead, others[1], others[3]].filter(Boolean) as KontraFighter[];
  const heights = ["pb-0", "pb-2", "pb-4", "pb-2", "pb-0"];
  const focus = squad.fighters.find((f) => f.card.card_id === selected) ?? null;
  const pool = squad.options.filter((o) => role === "all" || o.role === role);

  const swapIn = (cardId: number) => {
    hapticSelection();
    if (selected === null) {
      if (ids.length < squad.size) save.mutate({ cards: [...ids, cardId], leader });
      else setError("Сначала нажми карту в отряде, которую хочешь заменить");
      return;
    }
    const next = ids.map((id) => (id === selected ? cardId : id));
    save.mutate({ cards: next, leader: selected === leader ? cardId : leader });
    setSelected(null);
  };

  return (
    <div className="flex flex-col gap-3">
      <GameHero game="kontra" title="Контратака">
        <span className="rounded-full bg-black/35 px-2.5 py-1 font-mono text-sm font-bold text-ink-chalk">⚡ {squad.power.toLocaleString("ru-RU")}</span>
      </GameHero>
      {hub && !hub.enabled && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">Режим сейчас выключен.</p>}
      {hub?.league_reward && (
        <section className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-amber-500/25 to-fuchsia-500/20 p-3 ring-1 ring-amber-300/50">
          <span className="text-3xl">{hub.league_reward.icon}</span>
          <div className="min-w-0 flex-1">
            <p className="text-xs font-black text-ink-chalk">Итоги недели: лига «{hub.league_reward.name}»</p>
            <p className="text-micro text-ink-mist">Лучший рейтинг недели — {hub.league_reward.best}</p>
          </div>
          <button onClick={() => claim.mutate()} disabled={claim.isPending}
            className="flex shrink-0 items-center gap-1 rounded-xl bg-amber-400 px-3 py-2 text-xs font-black text-bg-base active:scale-95 disabled:opacity-50">
            +{hub.league_reward.coins} <IconCoin size={12} />
          </button>
        </section>
      )}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}

      <section className="rounded-3xl bg-gradient-to-b from-emerald-900/70 to-emerald-950 px-2 pb-3 pt-5 ring-1 ring-emerald-700/40">
        <div className="grid grid-cols-5 items-end gap-1">
          {stage.map((f, i) => (
            <div key={f.card.card_id} className={heights[i]}>
              <FighterCard
                card={f.card}
                leader={f.card.card_id === leader}
                active={selected === f.card.card_id}
                onTap={() => { hapticSelection(); setError(null); setSelected(selected === f.card.card_id ? null : f.card.card_id); }}
              />
            </div>
          ))}
          {Array.from({ length: squad.size - stage.length }, (_, i) => (
            <div key={`empty-${i}`} className="flex aspect-[3/4] items-center justify-center rounded-xl border border-dashed border-white/15 text-micro text-ink-mist-dim">
              пусто
            </div>
          ))}
        </div>
        <div className="mt-2 flex flex-wrap justify-center gap-1">
          {squad.leader_aura && <span className="rounded-full bg-white/10 px-2 py-0.5 text-micro text-ink-chalk">👑 {squad.leader_aura}</span>}
          {squad.chemistry_label && <span className="rounded-full bg-white/10 px-2 py-0.5 text-micro text-ink-chalk">Химия {squad.chemistry_label}: +{squad.chemistry_pct}% атаки</span>}
          {squad.leader_ult && (
            <span className="rounded-full bg-gradient-to-r from-amber-400/30 to-orange-500/30 px-2 py-0.5 text-micro text-amber-100" title={squad.leader_ult.description}>
              🔥 Суперудар лидера: {squad.leader_ult.name}
            </span>
          )}
        </div>
      </section>

      {focus ? (
        <section className="rounded-2xl bg-bg-surface p-3">
          <div className="flex items-center justify-between">
            <span className="font-display text-sm font-bold text-ink-chalk">{focus.card.display_name}</span>
            <span className="text-micro text-ink-mist">{focus.role_label} · {TIER_LABELS[focus.card.tier]}</span>
          </div>
          <p className="mt-0.5 font-mono text-micro text-ink-mist-dim">
            HP {focus.hp} · атака {focus.atk} · защита {focus.defence} · скорость {focus.spd}
            {focus.gear_count ? ` · комплект ×${focus.gear_count}` : ""}
          </p>
          <ul className="mt-2 flex flex-col gap-1 text-caption">
            {focus.abilities.map((a) => (
              <li key={a.code} className="text-ink-chalk">
                <b>{a.name}</b>{a.cooldown ? <span className="text-ink-mist-dim"> · перезарядка {a.cooldown}</span> : null}
                <span className="block text-ink-mist">{a.description}</span>
              </li>
            ))}
            {focus.passive && (
              <li className="text-amber-200"><b>Пассивка: {focus.passive.name}</b><span className="block text-ink-mist">{focus.passive.description}</span></li>
            )}
          </ul>
          <div className="mt-2 grid grid-cols-2 gap-2">
            <button
              onClick={() => save.mutate({ cards: ids, leader: focus.card.card_id })}
              disabled={focus.card.card_id === leader}
              className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-chalk active:scale-95 disabled:opacity-40"
            >
              👑 Сделать лидером
            </button>
            <button
              onClick={() => { save.mutate({ cards: ids.filter((id) => id !== focus.card.card_id), leader: focus.card.card_id === leader ? ids.find((id) => id !== leader)! : leader }); setSelected(null); }}
              disabled={ids.length <= 1}
              className="rounded-xl bg-white/5 py-2 text-xs font-semibold text-ink-mist active:scale-95 disabled:opacity-40"
            >
              Убрать из отряда
            </button>
          </div>
          <p className="mt-1.5 text-center text-micro text-ink-mist-dim">Или нажми карту ниже — она встанет на это место. Удержи карту, чтобы увидеть рейтинг и позицию</p>
        </section>
      ) : (
        <div className="grid grid-cols-2 gap-2">
          <button
            onClick={() => (hub?.active_battle_id ? navigate(`/play/kontra/battles/${hub.active_battle_id}`) : navigate("/play/kontra/arena"))}
            disabled={hub ? !hub.enabled : true}
            className="relative rounded-2xl bg-amber-400 px-3 py-3 text-left text-bg-base active:scale-95 disabled:opacity-50"
          >
            <span className="block font-display text-base font-black">{hub?.active_battle_id ? "Доиграть бой" : "Арена"}</span>
            <span className="block text-micro font-semibold">{hub?.league ? `${hub.league.icon} ${hub.league.name} · ` : ""}рейтинг {hub?.rating ?? "—"}</span>
            {hub?.defense_unread ? (
              <span className="absolute -right-1 -top-1 rounded-full bg-red-500 px-1.5 py-0.5 text-[10px] font-black text-white">🛡 {hub.defense_unread}</span>
            ) : null}
          </button>
          <button
            onClick={() => navigate("/play/kontra/boss")}
            disabled={hub ? !hub.enabled : true}
            className="rounded-2xl bg-red-600 px-3 py-3 text-left text-white active:scale-95 disabled:opacity-50"
          >
            <span className="block font-display text-base font-black">Босс недели</span>
            <span className="block truncate text-micro font-semibold">{hub?.boss_name} · попыток {hub?.boss_attempts_left ?? 0}</span>
          </button>
          <button
            onClick={() => navigate("/play/kontra/gear")}
            className="col-span-2 rounded-2xl bg-white/5 py-2.5 text-xs font-semibold text-ink-chalk active:scale-95"
          >
            🧤 Тактические комплекты{hub?.gear_count ? ` · ${hub.gear_count}` : ""}
          </button>
        </div>
      )}

      {!focus && (
        <TacticPicker tactics={squad.tactics} current={squad.tactic} edge={squad.tactic_edge_pct} busy={tactic.isPending} onPick={(code) => tactic.mutate(code)} />
      )}

      <div className="flex flex-wrap gap-1.5">
        {ROLE_FILTERS.map((f) => (
          <button
            key={f.id}
            onClick={() => setRole(f.id)}
            className={`rounded-full px-3 py-1.5 text-xs font-semibold active:scale-95 ${role === f.id ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {f.label}
          </button>
        ))}
        <button onClick={() => auto.mutate()} className="ml-auto rounded-full bg-white/5 px-3 py-1.5 text-xs font-semibold text-ink-chalk active:scale-95">
          Авто-подбор
        </button>
      </div>
      <div className="grid grid-cols-4 gap-1">
        {pool.slice(0, 40).map((o, i) => (
          <FighterCard key={o.card.card_id} card={o.card} onTap={() => swapIn(o.card.card_id)}
            edge={i % 4 === 0 ? "left" : i % 4 === 3 ? "right" : undefined} />
        ))}
        {!pool.length && <p className="col-span-4 py-4 text-center text-xs text-ink-mist">Других карт этой роли нет</p>}
        <p className="col-span-4 pt-1 text-center text-micro text-ink-mist-dim">Один футболист — одно место в отряде: копии и другие версии уже стоящего игрока скрыты</p>
      </div>
    </div>
  );
}
