import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import { fetchGameConfig, fetchSuspiciousMatches, fetchSuspiciousMemorySessions, updateGameConfig } from "@/admin/api";
import type { GameConfig } from "@/admin/types";

export default function AdminGamesPage() {
  const queryClient = useQueryClient();
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });
  const { data: suspiciousMemory } = useQuery({ queryKey: ["admin-suspicious-memory"], queryFn: fetchSuspiciousMemorySessions });
  const { data: suspiciousMatches } = useQuery({ queryKey: ["admin-suspicious-matches"], queryFn: fetchSuspiciousMatches });

  const [form, setForm] = useState<GameConfig | null>(null);
  useEffect(() => { if (config) setForm(config); }, [config]);

  const updateMutation = useMutation({
    mutationFn: () => updateGameConfig(form!),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["admin-game-config"] }),
  });

  if (!form) return <p className="text-sm text-slate-400">Загрузка...</p>;

  const field = (key: keyof GameConfig, label: string) => (
    <label className="flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        type="number"
        value={form[key]}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Игры</h1>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Общие лимиты</p>
        <div className="grid grid-cols-2 gap-3">
          {field("hourly_game_limit", "Лимит игр в час (на каждую игру)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Бесплатный пак</p>
        <div className="grid grid-cols-2 gap-3">
          {field("free_pack_interval_hours", "Интервал, часы")}
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">Slug пака</span>
            <input
              value={form.free_pack_pack_slug}
              onChange={(e) => setForm({ ...form, free_pack_pack_slug: e.target.value })}
              className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
            />
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Memory Sequence</p>
        <div className="grid grid-cols-2 gap-3">
          {field("memory_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("memory_reward_cap", "Максимальная награда")}
          {field("suspicious_memory_score_threshold", "Порог подозрительного счёта")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Card Arena</p>
        <div className="grid grid-cols-2 gap-3">
          {field("match_daily_energy", "Энергия в день")}
          {field("match_reward_win", "Награда за победу")}
          {field("match_reward_draw", "Награда за ничью")}
          {field("match_reward_loss", "Награда за поражение")}
          {field("difficulty_easy_multiplier", "Множитель: лёгкий")}
          {field("difficulty_medium_multiplier", "Множитель: средний")}
          {field("difficulty_hard_multiplier", "Множитель: сложный")}
          {field("suspicious_score_margin", "Порог подозрительной разницы счёта")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Футбольный сапёр</p>
        <div className="grid grid-cols-2 gap-3">
          {field("saboteur_cell_reward", "Награда за ячейку")}
          {field("saboteur_daily_limit", "Лимит наградных попыток/день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Пенальти</p>
        <div className="grid grid-cols-2 gap-3">
          {field("penalty_reward_win", "Награда за победу")}
          {field("penalty_reward_draw", "Награда за ничью")}
          {field("penalty_reward_loss", "Награда за поражение")}
          {field("penalty_bot_miss_chance", "Шанс промаха бота (0-1)")}
          {field("penalty_daily_limit", "Лимит наградных попыток/день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Штрафной удар</p>
        <div className="grid grid-cols-2 gap-3">
          {field("free_kick_period_min_ms", "Мин. период шкалы, мс")}
          {field("free_kick_period_max_ms", "Макс. период шкалы, мс")}
          {field("free_kick_base_stake", "Базовая ставка")}
          {field("free_kick_daily_limit", "Лимит наградных попыток/день")}
        </div>
      </section>

      <button onClick={() => updateMutation.mutate()} className="self-start rounded-xl bg-accent px-5 py-2.5 text-sm font-bold text-bg-base">
        Сохранить настройки
      </button>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Подозрительные сессии Memory Sequence</p>
        <div className="flex flex-col gap-2 text-sm">
          {suspiciousMemory?.map((s) => (
            <div key={s.session_id} className="flex items-center justify-between text-xs">
              <span>{s.username ?? s.user_id}: счёт {s.score}</span>
              <span className="text-amber-300">+{s.reward_coins}</span>
            </div>
          ))}
          {!suspiciousMemory?.length && <p className="text-xs text-slate-500">Ничего подозрительного не найдено</p>}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Подозрительные матчи Card Arena</p>
        <div className="flex flex-col gap-2 text-sm">
          {suspiciousMatches?.map((m) => (
            <div key={m.match_id} className="flex items-center justify-between text-xs">
              <span>{m.username ?? m.user_id}: {m.user_score}:{m.opponent_score}</span>
              <span className="text-amber-300">+{m.reward_coins}</span>
            </div>
          ))}
          {!suspiciousMatches?.length && <p className="text-xs text-slate-500">Ничего подозрительного не найдено</p>}
        </div>
      </section>
    </div>
  );
}
