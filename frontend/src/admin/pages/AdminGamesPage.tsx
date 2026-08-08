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
        <p className="mb-3 font-display text-base font-bold">Пак в чате (команда «вкарта»)</p>
        <p className="mb-3 text-xs text-slate-500">
          Использует тот же пак, что и бесплатный (Slug пака выше), но на собственном кулдауне.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("chat_pack_interval_hours", "Интервал, часы")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Рефералы</p>
        <div className="grid grid-cols-2 gap-3">
          {field("referral_referred_reward", "Награда приглашённому")}
          {field("referral_referrer_reward", "Награда пригласившему")}
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
        <p className="mb-3 font-display text-base font-bold">Card Arena — удары</p>
        <div className="grid grid-cols-2 gap-3">
          {field("match_shot_miss_chance_min", "Шанс промаха, мин (0-1)")}
          {field("match_shot_miss_chance_max", "Шанс промаха, макс (0-1)")}
          {field("match_defender_block_chance_min", "Шанс блока защитником, мин (0-1)")}
          {field("match_defender_block_chance_max", "Шанс блока защитником, макс (0-1)")}
          {field("match_shot_type_in_box_weight", "Вес: удар в штрафной")}
          {field("match_shot_type_long_range_weight", "Вес: дальний удар")}
          {field("match_shot_type_empty_net_weight", "Вес: пустые ворота")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Card Arena — атака и защита</p>
        <div className="grid grid-cols-2 gap-3">
          {field("match_attack_shoot_miss_chance_min", "Промах при ударе, мин (0-1)")}
          {field("match_attack_shoot_miss_chance_max", "Промах при ударе, макс (0-1)")}
          {field("match_pass_fail_chance_min", "Неточный пас, мин (0-1)")}
          {field("match_pass_fail_chance_max", "Неточный пас, макс (0-1)")}
          {field("match_receiver_shot_miss_chance_min", "Промах после паса, мин (0-1)")}
          {field("match_receiver_shot_miss_chance_max", "Промах после паса, макс (0-1)")}
          {field("match_tackle_foul_chance_min", "Грязный подкат, мин (0-1)")}
          {field("match_tackle_foul_chance_max", "Грязный подкат, макс (0-1)")}
          {field("match_tackle_red_chance_min", "Красная вместо жёлтой, мин (0-1)")}
          {field("match_tackle_red_chance_max", "Красная вместо жёлтой, макс (0-1)")}
          {field("match_block_fail_chance_min", "Неудачный блок, мин (0-1)")}
          {field("match_block_fail_chance_max", "Неудачный блок, макс (0-1)")}
          {field("match_keeper_save_chance_min", "Сейв вратаря, мин (0-1)")}
          {field("match_keeper_save_chance_max", "Сейв вратаря, макс (0-1)")}
          {field("match_red_card_strength_penalty_pct", "Штраф к обороне за красную (0-1)")}
          {field("match_penalty_gk_rating_penalty", "Штраф к рейтингу вратаря на пенальти")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Футбольный фанат</p>
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

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Тактико</p>
        <div className="grid grid-cols-2 gap-3">
          {field("tactico_challenge_expiry_hours", "Срок жизни вызова, часы")}
          {field("tactico_round_timeout_hours", "Тайм-аут на раунд, часы")}
          {field("tactico_phase_bonus_pct", "Бонус за фазу (0-1)")}
          {field("tactico_reward_win", "Награда за победу (бот)")}
          {field("tactico_reward_draw", "Награда за ничью (бот)")}
          {field("tactico_reward_loss", "Награда за поражение (бот)")}
          {field("tactico_bot_optimal_pick_chance_easy", "Точность бота: лёгкий (0-1)")}
          {field("tactico_bot_optimal_pick_chance_medium", "Точность бота: средний (0-1)")}
          {field("tactico_bot_optimal_pick_chance_hard", "Точность бота: сложный (0-1)")}
          {field("tactico_max_legendary_cards", "Макс. легендарных карт в составе")}
          {field("tactico_max_epic_cards", "Макс. эпических карт в составе")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Футбольные буквы</p>
        <div className="grid grid-cols-2 gap-3">
          {field("hangman_daily_limit", "Лимит наградных попыток/день")}
          {field("hangman_reward_correct", "Награда за угаданное слово")}
          {field("hangman_max_wrong", "Число ошибок до поражения")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Найди пару</p>
        <p className="mb-3 text-xs text-slate-500">
          Награда падает по группам ошибок: с настройками по умолчанию 0-10 ошибок = 40 монет, 11-20 = 30, 21-30 = 20
          и т.д., но не ниже минимальной награды.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("pairs_daily_limit", "Лимит наградных попыток/день")}
          {field("pairs_reward_perfect", "Награда в топ-группе (0 ошибок)")}
          {field("pairs_reward_min", "Минимальная награда")}
          {field("pairs_error_bracket_size", "Ошибок в одной группе")}
          {field("pairs_bracket_penalty", "Штраф за группу ошибок")}
          {field("pairs_bonus_coins", "Бонус за особую карту")}
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
