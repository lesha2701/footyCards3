import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import AdminCareerClubs from "@/admin/pages/AdminCareerClubs";

import { fetchGameConfig, fetchNewbieFunnel, fetchSuspiciousMatches, fetchSuspiciousMemorySessions, updateGameConfig } from "@/admin/api";
import AdminMagnateBoardEditor from "@/admin/pages/AdminMagnateBoardEditor";
import RewardBundleEditor from "@/admin/components/RewardBundleEditor";
import { EMPTY_BUNDLE, type GameConfig } from "@/admin/types";

// Codes from backend my_player_service.COSMETICS.
const MY_PLAYER_COSMETICS: [string, string][] = [
  ["headband", "Повязка на голову"],
  ["earring", "Серьга"],
  ["chain", "Цепочка"],
  ["goggles", "Спортивные очки"],
  ["captain", "Капитанская повязка"],
  ["headphones", "Наушники"],
  ["crown", "Корона"],
  ["bg_sunset", "Фон «Закат»"],
  ["bg_neon", "Фон «Неон»"],
  ["bg_gold", "Фон «Золотой стадион»"],
  ["bg_night", "Фон «Ночной матч»"],
  ["bg_galaxy", "Фон «Галактика»"],
  ["bg_champions", "Фон «Лига чемпионов»"],
  ["fx_sparkle", "Эффект «Искры»"],
  ["fx_fire", "Эффект «Пламя»"],
  ["fx_lightning", "Эффект «Молния»"],
  ["bg_goal", "Фон «Ворота»"],
  ["bg_national", "Фон «Флаг сборной»"],
  ["cel_siu", "Празднование «Сиу!»"],
  ["cel_plane", "Празднование «Самолётик»"],
  ["cel_heart", "Празднование «Сердечко»"],
  ["cel_dance", "Празднование «Танец у флажка»"],
];

const WEEKLY_TOP_METRICS: [string, string][] = [
  ["arena_rating", "Рейтинг Arena"], ["tactics_rating", "Рейтинг Тактико"], ["penalty_rating", "Рейтинг Пенальти"],
  ["stratego_rating", "Рейтинг Стратего"], ["stratego_puzzles", "Задачи Стратего"], ["mordoboi_rating", "Рейтинг Мордобоя"],
  ["kontra_rating", "Арена Контратаки"], ["league_rating", "Рейтинг лиги"], ["matches_won", "Победы"],
  ["cards_count", "Карт в коллекции"], ["unique_players", "Уникальных игроков"], ["referral_count", "Рефералов"],
  ["base_level", "Уровень базы"], ["academy_level", "Уровень Академии"], ["academy_prestige", "Престиж Академии"],
  ["games_week", "Игр за неделю"], ["stars_week", "Звёзд за неделю"], ["referrals_week", "Рефералов за неделю"],
];

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
        value={(form[key] as number | null) ?? 0}
        onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  const listField = (
    key:
      | "career_place_rewards"
      | "career_difficulty_reward_pct"
      | "career_difficulty_rating_offset"
      | "career_bot_counter_chance_pct"
      | "career_division_rating_offset"
      | "career_division_reward_pct"
      | "career_ambition_bonus_pct"
      | "career_ambition_rep_success"
      | "career_ambition_rep_fail"
      | "career_rep_levels"
      | "career_cup_rewards"
      | "my_player_tier_thresholds"
      | "player_career_place_rewards"
      | "player_career_level_ratings"
      | "player_career_level_salary"
      | "player_career_level_prestige"
      | "player_career_star_prestige"
      | "player_career_cl_rewards"
      | "player_career_national_rewards"
      | "player_career_weekly_coins"
      | "player_career_friends_rewards"
      | "manager_value_ratings"
      | "manager_value_eur"
      | "manager_division_budget"
      | "manager_division_income_pct"
      | "manager_division_wage_pct"
      | "manager_division_rating"
      | "manager_place_rewards"
      | "manager_place_budget"
      | "club_league_rewards"
      | "club_league_division_reward_pct"
      | "magnate_place_rewards"
      | "magnate_stadium_rents"
      | "arena_division_min_points"
      | "arena_division_reward_coins"
      | "arena_division_coin_pct"
      | "weekly_cup_prizes"
      | "match_day_leagues",
    label: string,
  ) => (
    <label className="col-span-2 flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        defaultValue={(form[key] ?? []).join(", ")}
        onBlur={(e) =>
          setForm({
            ...form,
            [key]: e.target.value.split(",").map((v) => Number(v.trim())).filter((v) => Number.isFinite(v)),
          })
        }
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  const textListField = (key: "career_division_bot_level" | "weekly_cup_games" | "newbie_first_pack_rarities", label: string) => (
    <label className="col-span-2 flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <input
        defaultValue={(form[key] ?? []).join(", ")}
        onBlur={(e) =>
          setForm({ ...form, [key]: e.target.value.split(",").map((v) => v.trim()).filter(Boolean) })
        }
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </label>
  );

  const jsonField = (
    key:
      | "manager_slots" | "manager_cosmetics" | "manager_merch" | "newbie_tasks" | "task_daily_chests" | "task_weekly_chests"
      | "card_values",
    label: string,
  ) => (
    <label className="col-span-2 flex flex-col gap-1">
      <span className="text-xs text-slate-400">{label}</span>
      <textarea
        rows={key === "manager_slots" ? 1 : 6}
        defaultValue={JSON.stringify(form[key] ?? [], null, key === "manager_slots" ? 0 : 1)}
        onBlur={(e) => {
          try {
            setForm({ ...form, [key]: JSON.parse(e.target.value || "[]") });
            e.target.classList.remove("ring-1", "ring-red-500");
          } catch {
            e.target.classList.add("ring-1", "ring-red-500");
          }
        }}
        className="rounded-lg bg-bg-surface px-3 py-2 font-mono text-xs outline-none"
      />
    </label>
  );

  const toggle = (
    key:
      | "matchmaking_enabled"
      | "wheel_enabled"
      | "trades_enabled"
      | "trade_coins_enabled"
      | "trade_cards_both_sides"
      | "club_war_enabled"
      | "blackjack_enabled"
      | "mordoboi_enabled"
      | "kontra_enabled"
      | "weekly_top_enabled"
      | "newbie_enabled"
      | "leagues_enabled"
      | "diamond_rating_cap_enabled"
      | "bot_daily_digest_enabled"
      | "bot_comeback_enabled"
      | "shop_daily_offer_enabled"
      | "club_league_enabled"
      | "career_enabled"
      | "career_reminders_enabled"
      | "career_cup_enabled"
      | "career_offseason_auto"
      | "career_live_enabled"
      | "career_digest_enabled"
      | "my_player_enabled"
      | "player_career_enabled"
      | "player_career_fast_season_enabled"
      | "manager_enabled"
      | "chemistry_enabled"
      | "card_stars_enabled"
      | "weekly_cup_enabled"
      | "match_day_enabled"
      | "match_day_auto_enabled"
      | "club_raid_enabled",
    label: string,
  ) => (
    <label className="flex items-center gap-2 text-sm">
      <input
        type="checkbox"
        checked={form[key]}
        onChange={(e) => setForm({ ...form, [key]: e.target.checked })}
      />
      {label}
    </label>
  );

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Игры</h1>

      <section className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
        <p className="mb-1 font-display text-base font-bold">Аварийное отключение</p>
        <p className="mb-3 text-xs text-slate-400">
          Быстро скрыть эти функции от игроков без деплоя, например если после запуска нашлись баги. Не жми
          «Сохранить» внизу отдельно — эта форма сохраняется той же кнопкой, что и остальные настройки на странице.
        </p>
        <div className="flex flex-col gap-2">
          {toggle("matchmaking_enabled", "Показывать кнопку «Играть» (подбор соперника) в Тактико и Пенальти")}
          {toggle("wheel_enabled", "Показывать раздел «Колесо фортуны» на главном экране")}
          {toggle("trades_enabled", "Обмены между игроками (выкл — нельзя создавать и принимать предложения)")}
          {toggle("blackjack_enabled", "Игра «21: Добавленное время» (новые партии и покупка попыток)")}
          {toggle("leagues_enabled", "Показывать баннер лиг на главном экране и в профиле")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Общие лимиты</p>
        <div className="grid grid-cols-2 gap-3">
          {field("hourly_game_limit", "Лимит игр в час (на каждую игру)")}
          {field("club_creation_cost_coins", "Стоимость создания клуба")}
          {field("club_daily_reward_coins", "Ежедневная награда клуба")}
          {field("club_tournament_cooldown_hours", "Кулдаун между заявками на турнир, часы")}
          {field("club_form_window_matches", "Окно формы клуба, матчей")}
          {field("club_form_bonus_per_result", "Бонус формы за результат (напр. 0.02)")}
          {field("club_tournament_budget_place_1", "Награда бюджетом за 1-е место")}
          {field("club_tournament_budget_place_2", "Награда бюджетом за 2-е место")}
          {field("club_tournament_budget_place_3", "Награда бюджетом за 3-е место")}
          {field("club_tournament_budget_place_4", "Награда бюджетом за 4-е место")}
          {field("club_tournament_budget_place_5", "Награда бюджетом за 5-е место")}
          {field("club_tournament_budget_place_6", "Награда бюджетом за 6-е место")}
          {field("club_tournament_budget_place_7", "Награда бюджетом за 7-е место")}
          {field("club_tournament_budget_place_8", "Награда бюджетом за 8-е место")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Награда за матч турнира</p>
        <p className="mb-3 text-xs text-slate-500">Начисляется в бюджет клуба за каждый сыгранный матч тура — отдельно от награды за итоговое место.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_match_reward_win", "Награда за победу")}
          {field("club_match_reward_draw", "Награда за ничью")}
          {field("club_match_reward_loss", "Награда за поражение")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Личная награда участникам за матч</p>
        <p className="mb-3 text-xs text-slate-500">Начисляется лично каждому участнику клуба (кроме тех, у кого капитан отключил эту награду) за каждый сыгранный матч тура.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_member_match_reward_win", "Награда за победу")}
          {field("club_member_match_reward_draw", "Награда за ничью")}
          {field("club_member_match_reward_loss", "Награда за поражение")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Красные карточки и травмы (клубный турнир)</p>
        <p className="mb-3 text-xs text-slate-500">Влияет только на клубные турнирные матчи — на Card Arena не распространяется.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_tactical_tackle_attempt_chance", "Шанс попытки подката (0-1)")}
          {field("club_tactical_injury_chance", "Шанс травмы при красной (0-1)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Тренировка состава (клубный турнир)</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_training_boost_pct", "Усиление состава (0-1, напр. 0.10 = +10%)")}
          {field("club_training_uses_per_tournament", "Число тренировок за турнир")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Диамантовые карты — апгрейд рейтинга</p>
        <p className="mb-3 text-xs text-slate-400">
          Мягкий потолок рейтинга при прокачке: карту нельзя докормить выше этого значения. Уже существующие карты с
          более высоким рейтингом не трогаются — просто больше не растут. Сними галочку, чтобы вернуть жёсткий
          технический потолок 99.
        </p>
        <div className="flex flex-wrap items-center gap-4">
          {field("diamond_rating_cap", "Потолок рейтинга")}
          {toggle("diamond_rating_cap_enabled", "Ограничение включено")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Клубные игры — общий лимит</p>
        <p className="mb-3 text-xs text-slate-500">
          Один пул попыток в час на участника, общий для всех трёх клубных игр ниже — можно потратить на любую их
          комбинацию (например, дважды сыграть в пенальти).
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_games_hourly_limit", "Игр в час (на участника, суммарно)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Клубная игра «Повтори порядок»</p>
        <p className="mb-3 text-xs text-slate-500">Награда за игру идёт в бюджет клуба, а не игроку лично.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_game_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("club_game_reward_cap", "Максимальная награда")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Пенальти (клубная игра)</p>
        <p className="mb-3 text-xs text-slate-500">Награда за игру идёт в бюджет клуба, а не игроку лично.</p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_penalty_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("club_penalty_reward_win", "Награда за победу")}
          {field("club_penalty_reward_loss", "Награда за поражение")}
          {field("club_penalty_bot_miss_chance", "Шанс промаха бота (0-1)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Своя позиция (клубная игра)</p>
        <p className="mb-3 text-xs text-slate-500">
          Награда за игру идёт в бюджет клуба. Награда = награда за идеальный раунд − ошибки × штраф за ошибку, но не
          ниже минимальной. После указанного числа ошибок раунд засчитывается как проигранный (награда 0).
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("club_position_match_daily_reward_limit", "Лимит наградных попыток/день")}
          {field("club_position_match_max_mistakes", "Ошибок до поражения")}
          {field("club_position_match_reward_perfect", "Награда за идеальный раунд")}
          {field("club_position_match_reward_min", "Минимальная награда")}
          {field("club_position_match_penalty_per_mistake", "Штраф за ошибку")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Химия карточек</p>
        <p className="mb-3 text-xs text-slate-400">
          Связи между соседями в схеме Card Arena, турниров игроков и клубных составов: один клуб и страна — сильная связь, клуб или
          страна — средняя. Выключено — старая формула (бонус за самый частый клуб/страну) без изменений. Уже начатые
          матчи Арены, турниры игроков и клубные турниры доигрываются по правилам, действовавшим на их старте. FUT Draft всегда считает
          химию по-своему (настройки в блоке FUT Draft).
        </p>
        <div className="mb-3">{toggle("chemistry_enabled", "Включить химию связей")}</div>
        <div className="grid grid-cols-2 gap-3">
          {field("chemistry_link_strong", "Сильная связь, очков")}
          {field("chemistry_link_medium", "Средняя связь, очков")}
          {field("chemistry_threshold_1", "Порог 1-го очка (сумма связей)")}
          {field("chemistry_threshold_2", "Порог 2-го очка")}
          {field("chemistry_threshold_3", "Порог 3-го очка")}
          {field("chemistry_player_max", "Максимум химии игрока (0–3)")}
          {field("chemistry_player_floor", "Пол химии для игрока на своей позиции")}
          {field("chemistry_rating_per_point", "+ рейтинга в матче за очко химии")}
          {field("chemistry_off_position_penalty", "Штраф рейтинга не на своей позиции")}
          {field("chemistry_coach_country_points", "+ химии игроку из страны тренера")}
          {field("chemistry_stadium_club_points", "+ химии игроку клуба стадиона (дома)")}
        </div>
        <p className="mt-2 text-caption text-slate-500">
          Подбор значений: <code>python -m scripts.compare_chemistry --synthetic 2000</code> в backend сравнивает силу
          существующих составов по старой и новой формуле.
        </p>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Звёзды карточек</p>
        <p className="mb-3 text-xs text-slate-400">
          Дубли того же игрока копятся в конкретной карточке; при достижении порога за монеты выдаётся звезда (+рейтинг).
          Бриллианты не участвуют. Выключено — нельзя вкладывать и забирать новые звёзды, полученные продолжают действовать.
          Бонус звезды фиксируется на карточке в момент получения.
        </p>
        <div className="mb-3">{toggle("card_stars_enabled", "Включить звёзды карточек")}</div>
        <div className="grid grid-cols-2 gap-3">
          {field("card_stars_max", "Максимум звёзд (0–5)")}
          {field("card_star_rating_per_star", "+ рейтинга за звезду")}
          {field("card_star_bonus_cap", "Потолок прибавки от звёзд")}
        </div>
        <p className="mb-2 mt-3 text-xs font-semibold text-slate-400">По редкостям: дубли / монеты за ★1, ★2, ★3 (через запятую)</p>
        <div className="grid grid-cols-[auto_1fr_1fr] items-center gap-2 text-xs">
          {(["common", "rare", "epic", "legendary"] as const).map((rarity) => (
            <StarLadderRow
              key={rarity}
              rarity={rarity}
              dupes={form.card_star_dupes_per_level?.[rarity] ?? []}
              coins={form.card_star_coin_cost?.[rarity] ?? []}
              onChange={(kind, values) =>
                setForm({ ...form, [kind]: { ...(form[kind] ?? {}), [rarity]: values } })
              }
            />
          ))}
        </div>
        <p className="mt-2 text-caption text-slate-500">
          Оценка до включения: <code>python -m scripts.estimate_card_stars</code> в backend — сколько звёзд игроки получили бы
          сразу и сколько дублей ушло бы из быстрой продажи.
        </p>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">FUT Draft</p>
        <p className="mb-3 text-xs text-slate-500">
          Шансы пяти уровней пика должны в сумме давать 100. Легендарки выпадают только в джекпот-пике — это то, что
          держит их редкими. Награда — по числу побед в серии из 4 матчей (0 побед = проиграл первый матч).
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("fut_draft_entry_cost", "Цена входа, монеты")}
        </div>
        <p className="mb-2 mt-3 text-xs font-semibold text-slate-400">Шансы пика (%, сумма = 100)</p>
        <div className="grid grid-cols-2 gap-3">
          {field("fut_draft_weak_chance", "Слабый")}
          {field("fut_draft_normal_chance", "Обычный")}
          {field("fut_draft_strong_chance", "Сильный")}
          {field("fut_draft_top_chance", "Топовый")}
          {field("fut_draft_jackpot_chance", "Джекпот")}
        </div>
        <p className="mb-2 mt-3 text-xs font-semibold text-slate-400">Награда по числу побед</p>
        <div className="grid grid-cols-2 gap-3">
          {field("fut_draft_reward_win_0", "0 побед")}
          {field("fut_draft_reward_win_1", "1 победа")}
          {field("fut_draft_reward_win_2", "2 победы")}
          {field("fut_draft_reward_win_3", "3 победы")}
          {field("fut_draft_reward_win_4", "4 победы (идеальный драфт)")}
        </div>
        <p className="mb-2 mt-3 text-xs font-semibold text-slate-400">Химия состава (бонус к силе за пик)</p>
        <div className="grid grid-cols-2 gap-3">
          {field("fut_draft_club_bonus_per_extra", "За доп. одноклубника")}
          {field("fut_draft_country_bonus_per_extra", "За доп. игрока из региона")}
        </div>
        <p className="mb-2 mt-3 text-xs font-semibold text-slate-400">Сложность ботов по раундам</p>
        <div className="grid grid-cols-2 gap-3">
          {field("fut_draft_round_bot_boost_pct", "Усиление бота к 4 матчу, % (0 = как раньше)")}
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
        <p className="mb-1 font-display text-base font-bold">Лига клубов</p>
        <p className="mb-3 text-xs text-slate-400">
          Неделя с понедельника по воскресенье. Очки клубу приносят участники: сыгранные игры и матчи, паки,
          купленные за монеты или звёзды, выполненные задания (только после вступления в клуб). Итоги — в
          понедельник, награды за места (через запятую, 1-е место первым) идут в бюджет клуба.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("club_league_enabled", "Лига включена")}
          {field("club_league_member_weekly_cap", "Максимум очков с игрока за неделю")}
          {field("club_league_points_game", "Очки за игру / матч")}
          {field("club_league_points_pack", "Очки за покупку пака")}
          {field("club_league_points_task", "Очки за задание")}
          {listField("club_league_rewards", "Награды за места, монеты в бюджет клуба")}
          {listField("club_league_division_reward_pct", "Множитель наград по лигам Бронза, Серебро, Золото, %")}
          {field("club_league_season_weeks", "Сезон, недель")}
          {field("club_league_promote_count", "Повышаются в конце сезона (топ-N)")}
          {field("club_league_relegate_count", "Вылетают в конце сезона (последние N)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Клубные войны</p>
        <p className="mb-3 text-xs text-slate-400">
          Раз в неделю клубы (от N участников) получают соперника с ближайшим рейтингом (Эло). В окне войны очки
          считаются как в лиге клубов (игры, паки, задания) с личным потолком. День недели: 0 — пн … 6 — вс, час — по
          времени сервера (часовой пояс приложения).
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("club_war_enabled", "Войны включены")}
          {field("club_war_start_weekday", "День старта (0 пн … 6 вс)")}
          {field("club_war_start_hour", "Час старта")}
          {field("club_war_duration_hours", "Длительность, ч")}
          {field("club_war_min_members", "Минимум участников в клубе")}
          {field("club_war_member_cap", "Максимум очков с игрока за войну")}
          {field("club_war_win_budget", "Победа: в бюджет клуба")}
          {field("club_war_draw_budget", "Ничья: в бюджет клуба")}
          {field("club_war_loss_budget", "Поражение: в бюджет клуба")}
          {field("club_war_win_member_coins", "Победа: монет каждому участнику")}
          {field("club_ring_win_points", "«Клубный ринг»: очков за победу в «Мордобое»")}
          {field("club_ring_member_cap", "«Клубный ринг»: максимум очков с игрока")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Неделя мини-игры</p>
        <p className="mb-3 text-xs text-slate-400">
          Каждую неделю — одна мини-игра по кругу из списка (penalty, free_kick, memory, saboteur, pairs). Очки игрока — сумма
          N лучших игр недели. Призы — монеты за 1, 2, 3… места; итоги подводятся в ночь на понедельник, приз игрок забирает сам.
          Игра недели фиксируется при первом заходе на неделе.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("weekly_cup_enabled", "Турнир включён")}
          {field("weekly_cup_best_of", "Лучших игр в зачёт")}
          {textListField("weekly_cup_games", "Игры по неделям, через запятую")}
          {listField("weekly_cup_prizes", "Призы за места, монет через запятую")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Матч дня</p>
        <p className="mb-3 text-xs text-slate-400">
          Матчи добавляются в разделе «Матч дня» вручную или автоматически: бот раз в полчаса берёт лучший матч сегодня/завтра по приоритету лиг и сам записывает счёт (основное время). Нужен ключ API_FOOTBALL_KEY на сервере. Награда — одна, самая высокая из угаданных.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("match_day_enabled", "Матч дня включён")}
          {field("match_day_exact_coins", "Точный счёт, монет")}
          {field("match_day_diff_coins", "Разница голов, монет")}
          {field("match_day_outcome_coins", "Исход, монет")}
          {toggle("match_day_auto_enabled", "Автоматически: матчи и счёт из API-Football")}
          {listField("match_day_leagues", "Лиги по приоритету (ID API-Football): 2 ЛЧ, 39 АПЛ, 140 Ла Лига, 235 РПЛ, 135 Серия А, 78 Бундеслига, 61 Лига 1, 3 ЛЕ, 848 ЛК, 1 ЧМ, 4 Евро")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Клубный рейд</p>
        <p className="mb-3 text-xs text-slate-400">
          Босс недели для каждого клуба. HP = «HP на участника» × участников (минимум 3), фиксируется при открытии рейда.
          Атака — серия ударов, шанс гола от силы 11 лучших карт игрока; урон = голы × «урон за гол» + сила состава. Лимит атак
          в день общий для всех клубов игрока. Победа: в казну клуба и награда каждому участнику (забирают в клубном магазине).
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("club_raid_enabled", "Рейды включены")}
          {field("club_raid_hp_per_member", "HP на участника")}
          {field("club_raid_attacks_per_day", "Атак в день")}
          {field("club_raid_shots", "Ударов в атаке")}
          {field("club_raid_damage_per_goal", "Урон за гол")}
          {field("club_raid_reward_budget", "Победа: в казну клуба")}
          {field("club_raid_reward_coins", "Победа: монет каждому")}
          {field("club_raid_reward_pack_id", "Победа: пак каждому (ID, 0 — нет)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Карьера тренера</p>
        <p className="mb-3 text-xs text-slate-400">
          Сезон на неделю: 8 команд, 14 туров (12:00 и 19:00), вход бесплатный. Списки — через запятую:
          награды за места 1→8, и по сложностям Любитель, Профи, Легенда.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("career_enabled", "Режим включён")}
          {listField("career_place_rewards", "Награда за места 1–8, монеты")}
          {listField("career_difficulty_reward_pct", "Множитель награды по сложности, % (сезоны до дивизионов)")}
          {listField("career_difficulty_rating_offset", "Сила ботов по сложности, ±рейтинг (сезоны до дивизионов)")}
          {field("career_match_reward_win", "За победу в туре")}
          {field("career_match_reward_draw", "За ничью в туре")}
          {field("career_bot_growth_tenths", "Рост ботов за тур, десятые рейтинга")}
          {field("career_fatigue_per_match", "Усталость за матч, %")}
          {field("career_fatigue_recovery", "Восстановление за тур отдыха, %")}
          {field("career_fatigue_penalty_pct", "Штраф рейтинга при 100% усталости, %")}
          {field("career_injury_chance_pct", "Шанс травмы за матч, %")}
          {field("career_yellow_chance_pct", "Шанс жёлтой за матч, %")}
          {field("career_red_chance_pct", "Шанс красной за матч, %")}
          {field("career_yellows_for_ban", "Жёлтых до дисквалификации")}
          {field("career_form_max", "Форма после победы, до +N рейтинга")}
          {toggle("career_reminders_enabled", "Напоминание ботом за 30 мин до тура")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">
            Дивизионы (новые сезоны; списки — от высшего дивизиона к низшему)
          </p>
          {field("career_division_count", "Число дивизионов")}
          {field("career_division_promote", "Мест на повышение")}
          {field("career_division_relegate", "Мест на вылет")}
          {listField("career_division_rating_offset", "Сила ботов по дивизионам, ±рейтинг")}
          {listField("career_division_reward_pct", "Множитель награды по дивизионам, %")}
          {textListField("career_division_bot_level", "Уровень ботов по дивизионам (amateur / pro / legend)")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">
            Тактика (новые сезоны): оси «направление / построение / после потери / после отбора / линия».
          </p>
          {field("career_squad_size", "Размер заявки на сезон")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">
            Задачи руководства и репутация (списки: Выживание, Середина, Выход)
          </p>
          {listField("career_ambition_bonus_pct", "Бонус к награде за выполненную задачу, %")}
          {listField("career_ambition_rep_success", "Репутация за выполненную задачу")}
          {listField("career_ambition_rep_fail", "Репутация за проваленную задачу")}
          {field("career_rep_title", "Репутация за чемпионство")}
          {field("career_rep_promotion", "Репутация за повышение")}
          {field("career_rep_relegation", "Репутация за вылет (отрицательная)")}
          {listField("career_rep_levels", "Пороги уровней репутации")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">Кубок</p>
          {toggle("career_cup_enabled", "Кубок в новых сезонах")}
          {listField("career_cup_rewards", "Призы кубка: победа, финал, полуфинал")}
          {field("career_rep_cup", "Репутация за кубок")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">Предсезонка и живая лига</p>
          {toggle("career_offseason_auto", "Новый сезон автоматически на следующий день")}
          {field("career_inactive_days", "Неактивен дней — без продления и вниз")}
          {field("career_core_min", "Ядро: минимум игроков")}
          {field("career_core_keep_pct", "Ядро: переносится сыгранности, %")}
          {field("career_camp_physical_pct", "Сборы «Физика»: меньше усталости, %")}
          {field("career_camp_physical_rounds", "Сборы «Физика»: туров")}
          {field("career_camp_tactical_tenths", "Сборы «Тактика»: сыгранность, десятые %")}
          {field("career_tenure_minutes_per_point", "Клубный стаж: минут за +1")}
          {field("career_tenure_max", "Клубный стаж: максимум")}
          {field("career_division_club_count", "Клубов в каталоге на дивизион")}
          <p className="col-span-2 mt-2 text-xs font-semibold text-slate-300">Live-матч, достижения, дайджест</p>
          {toggle("career_live_enabled", "Live-матч: перерыв для указаний")}
          {field("career_halftime_minutes", "Перерыв: минут до второго тайма")}
          {field("career_achievement_reward", "Награда за достижение, монет")}
          {toggle("career_digest_enabled", "Недельный дайджест в Telegram")}
          {field("career_familiarity_step_tenths", "Сыгранность за матч, десятые %")}
          {field("career_familiarity_max_tenths", "Потолок сыгранности, десятые %")}
          {field("career_familiarity_keep_pct", "Сохраняется при смене схемы, %")}
          {field("career_familiarity_axis_keep_pct", "Сохраняется за каждую изменённую ось, %")}
          <label className="col-span-2 flex flex-col gap-1">
            <span className="text-xs text-slate-400">
              Рычаги тактики, JSON поверх значений по умолчанию (пусто = по умолчанию). Например
              {" "}{'{"shift": {"press_vs_short": 0.2}}'}. После изменения силы взаимодействий перегенерируй таблицу
              скриптом simulate_career_tactics.py --write.
            </span>
            <textarea
              rows={3}
              defaultValue={JSON.stringify(form.career_tactics_tuning ?? {})}
              onBlur={(e) => {
                try {
                  setForm({ ...form, career_tactics_tuning: JSON.parse(e.target.value || "{}") });
                } catch {
                  e.target.classList.add("ring-1", "ring-red-500");
                }
              }}
              className="rounded-lg bg-bg-surface px-3 py-2 font-mono text-xs outline-none"
            />
          </label>
          {field("career_max_plan_rules", "Указаний на матч")}
          {field("career_max_substitutions", "Замен на матч")}
          {listField("career_bot_counter_chance_pct", "Шанс контр-стиля у ботов (Любитель, Профи, Легенда), %")}
        </div>
      </section>

      <AdminCareerClubs divisions={form.career_division_count ?? 5} />

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Мой игрок</p>
        <p className="mb-3 text-xs text-slate-400">
          Своя карточка игрока: опыт за любые награды в играх (с дневным лимитом), уровни дают очки характеристик.
          Переход L→L+1 стоит «база + шаг × (L−1)» опыта. Рамки — пороги рейтинга для Серебра, Золота и Легенды.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("my_player_enabled", "Режим включён")}
          {field("my_player_xp_per_reward", "Опыт за награду в игре")}
          {field("my_player_xp_daily_cap", "Лимит опыта в день")}
          {field("my_player_xp_career_match", "Бонус за матч в Карьере")}
          {field("my_player_xp_level_base", "Опыт на уровень: база")}
          {field("my_player_xp_level_step", "Опыт на уровень: шаг")}
          {field("my_player_points_per_level", "Очков за уровень")}
          {field("my_player_rating_cap", "Потолок рейтинга")}
          {listField("my_player_tier_thresholds", "Пороги рамок: Серебро, Золото, Легенда")}
          {field("my_player_training_xp_base", "Тренировка: опыт за участие")}
          {field("my_player_training_xp_per_hit", "Тренировка: опыт за попадание")}
          {field("my_player_extra_trainings_max", "Доп. тренировок в день (макс.)")}
          {field("my_player_extra_training_coins", "Доп. тренировка, монеты (0 — нет)")}
          {field("my_player_extra_training_stars", "Доп. тренировка, звёзды ⭐ (0 — нет)")}
          {field("my_player_streak_days", "Серия тренировок: дней для награды")}
          {field("my_player_streak_tokens", "Серия: жетонов навыка (0 — нет)")}
          {field("my_player_freshness_per_match", "Свежесть: −за матч Карьеры игрока")}
          {field("my_player_freshness_regen_per_hour", "Свежесть: +в час")}
          {field("my_player_freshness_training", "Свежесть: +за тренировку")}
          {field("my_player_fatigue_max_penalty", "Усталость: −рейтинга при 0% свежести")}
          {field("my_player_duels_per_day", "Дуэлей в день (0 — выкл.)")}
          {field("my_player_duel_reward_win", "Дуэль: монеты за победу")}
          {field("my_player_duel_reward_draw", "Дуэль: монеты за ничью")}
          {field("my_player_duel_xp", "Дуэль: опыт")}
          {field("my_player_role_change_coins", "Смена амплуа, монеты (0 — нет)")}
          {field("my_player_role_change_stars", "Смена амплуа, звёзды ⭐ (0 — нет)")}
        </div>
        <p className="mb-2 mt-4 text-xs text-slate-400">Цены косметики: монеты / звёзды ⭐ (0 — не продаётся за эту валюту)</p>
        <div className="grid grid-cols-1 gap-2">
          {MY_PLAYER_COSMETICS.map(([code, label]) => (
            <div key={code} className="grid grid-cols-[1fr_6rem_6rem] items-center gap-2">
              <span className="text-xs text-slate-300">{label}</span>
              {(["my_player_cosmetic_prices", "my_player_cosmetic_stars_prices"] as const).map((key) => (
                <input
                  key={key}
                  type="number"
                  min={0}
                  aria-label={`${label}: ${key === "my_player_cosmetic_prices" ? "монеты" : "звёзды"}`}
                  value={form[key]?.[code] ?? 0}
                  onChange={(e) => setForm({ ...form, [key]: { ...form[key], [code]: Number(e.target.value) } })}
                  className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
                />
              ))}
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Карьера игрока</p>
        <p className="mb-3 text-xs text-slate-400">
          Клубы и дивизионы — общие с «Карьерой тренера» (список клубов выше). Клуб открыт, если его рейтинг ≤ рейтинг игрока +
          запас и престиж игрока ≥ «престиж за звёзды клуба» + «престиж за дивизион». Зарплата = база дивизиона × (1 + % за
          каждую звезду сверх первой) × (1 + 1% за 10 престижа, до потолка). Списки — по дивизионам/звёздам от 1 до 5. Сезон — 8
          клубов дивизиона, 14 туров в слоты «Карьеры тренера».
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("player_career_enabled", "Режим включён")}
          {field("player_career_rating_margin", "Запас рейтинга для клуба")}
          {field("player_career_rep_per_goal", "Престиж за гол")}
          {field("player_career_rep_per_assist", "Престиж за передачу")}
          {field("player_career_rep_per_win", "Престиж за победу")}
          {field("player_career_rep_title", "Престиж за титул")}
          {field("player_career_match_reward_win", "Монеты за победу")}
          {field("player_career_match_reward_draw", "Монеты за ничью")}
          {field("player_career_goal_reward", "Монеты за гол игрока")}
          {field("player_career_match_xp", "Опыт за матч")}
          {field("player_career_objective_coins", "Цель клуба: монеты")}
          {field("player_career_objective_rep", "Цель клуба: престиж")}
          {listField("player_career_level_ratings", "Рейтинг клубов без карточек по дивизионам 1–5")}
          {listField("player_career_level_salary", "Базовая зарплата по дивизионам 1–5")}
          {listField("player_career_level_prestige", "Престиж за дивизион 1–5")}
          {listField("player_career_star_prestige", "Престиж за звёзды клуба 1–5")}
          {field("player_career_star_salary_pct", "Зарплата: +% за звезду клуба")}
          {field("player_career_prestige_salary_cap", "Зарплата: потолок % от престижа")}
          {field("player_career_contract_seasons", "Длина контракта, сезонов")}
          {field("player_career_free_agent_level", "Без контракта: дивизионы от N и ниже")}
          {field("player_career_offers_max", "Предложений в трансферное окно")}
          {field("player_career_haggle_base", "Торг: базовый шанс согласия, %")}
          {field("player_career_haggle_raise_penalty", "Торг: −% шанса за 1% прибавки")}
          {field("player_career_haggle_repeat_penalty", "Торг: −% шанса за повторный торг")}
          {field("player_career_cl_places", "ЛЧ: мест из высшего дивизиона")}
          {listField("player_career_cl_rewards", "ЛЧ: монеты за 1/4, 1/2, финал")}
          {field("player_career_cl_prestige", "ЛЧ: престиж за победу")}
          {field("player_career_national_prestige", "Сборная: престиж для вызова")}
          {listField("player_career_national_rewards", "Сборная: монеты за 1/4, 1/2, финал")}
          {field("player_career_national_win_prestige", "Сборная: престиж за победу")}
          {field("player_career_golden_ball_min_matches", "Золотой мяч: минимум матчей")}
          {field("player_career_golden_ball_coins", "Золотой мяч: монеты")}
          {field("player_career_golden_ball_prestige", "Золотой мяч: престиж")}
          {field("player_career_moments", "Ключевых моментов в матче")}
          {field("player_career_moment_hit_pct", "Момент: +% шанса за тайминг")}
          {field("player_career_moment_window_hours", "Момент: ждать решения, часов")}
          {field("player_career_bench_gap", "Скамейка: рейтинг ниже клуба больше чем на")}
          {field("player_career_bench_play_pct", "Запасной выходит в % матчей")}
          {field("player_career_trust_starter", "Доверие для основы")}
          {field("player_career_trust_captain", "Доверие для капитанства")}
          {field("player_career_captain_salary_pct", "Капитан: +% к зарплате")}
          {field("player_career_injury_freshness", "Травмы: ниже этой свежести")}
          {field("player_career_injury_max_pct", "Травмы: шанс при 0% свежести, %")}
          {field("player_career_heal_coins", "Лечение, монеты (0 — нет)")}
          {field("player_career_heal_stars", "Лечение, звёзды ⭐ (0 — нет)")}
          {field("player_career_refresh_coins", "Полная свежесть, монеты (0 — нет)")}
          {field("player_career_refresh_stars", "Полная свежесть, звёзды ⭐ (0 — нет)")}
          {field("player_career_event_every", "События: не чаще раза в N туров")}
          {field("player_career_event_coins", "События: базовые монеты")}
          {field("player_career_event_prestige", "События: базовый престиж")}
          {field("player_career_derby_multiplier", "Лига друзей: множитель дерби")}
          {field("player_career_pro_stars", "Карьера Pro, звёзды ⭐ (0 — нет)")}
          {field("player_career_pro_days", "Карьера Pro, дней")}
          {field("player_career_pro_xp_pct", "Карьера Pro: +% опыта")}
          {field("player_career_agent_stars", "Агент, звёзды ⭐ (0 — нет)")}
          {field("player_career_agent_haggle_bonus", "Агент: +% к шансу торга")}
          {field("player_career_save_offer_stars", "Вернуть клуб, звёзды ⭐ (0 — нет)")}
          {toggle("player_career_fast_season_enabled", "Ускоренный сезон в продаже")}
          {field("player_career_fast_season_stars", "Ускоренный сезон, звёзды ⭐ (0 — нет)")}
          {field("player_career_fast_round_minutes", "Ускоренный сезон: минут между турами")}
          {field("player_career_chest_coins_min", "Сундук дня: монет от")}
          {field("player_career_chest_coins_max", "Сундук дня: монет до")}
          {field("player_career_chest_token_pct", "Сундук дня: шанс жетона, %")}
          {field("player_career_weekly_goals", "Задание недели: голов")}
          {field("player_career_weekly_matches", "Задание недели: матчей")}
          {field("player_career_weekly_rating_x10", "Задание недели: оценка ×10 (70 = 7.0)")}
          {listField("player_career_weekly_coins", "Задания недели: монеты (голы, матчи, оценка)")}
          {listField("player_career_friends_rewards", "Лига друзей: монеты за 1–3 места")}
          {listField("player_career_place_rewards", "Награда за места 1–8, монеты")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">«Личный турнир»: тактика</p>
        <p className="mb-3 text-xs text-slate-400">
          Как в Card Arena: схема + один из 4 стилей по кругу (Атака › Оборона › Владение › Контратака › Атака).
          Стиль даёт % к рейтингам своих линий, схема — крен в атаку или защиту.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {field("ptour_style_edge_pct", "Бонус ко всем игрокам стилю, который бьёт стиль соперника, %")}
          {field("ptour_formation_effect_pct", "Сила крена схем в атаку/защиту, %")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">«Задания»: день, неделя, сундуки</p>
        <p className="mb-3 text-xs text-slate-400">
          Набор заданий дня обновляется в полночь, недели — в понедельник. Очки заданий наполняют шкалу
          активности; сундук открывается на своём пороге очков. Сундук: {"{"}"points", "coins", "card_rarity"
          (common/rare/epic/legendary), "pack_id"{"}"}.
        </p>
        <div className="grid grid-cols-3 items-end gap-3">
          {field("task_daily_slots", "Заданий в дне")}
          {field("task_weekly_slots", "Заданий в неделе")}
          {field("task_free_rerolls", "Бесплатных замен в день")}
        </div>
        <div className="mt-3 grid grid-cols-2 gap-3">
          {jsonField("task_daily_chests", "Сундуки дня")}
          {jsonField("task_weekly_chests", "Сундуки недели")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">«Менеджер»</p>
        <p className="mb-3 text-xs text-slate-400">
          Свой клуб у каждого: «Мой игрок» и игрок академии всегда в составе, до N «Моих игроков» других
          пользователей и футболисты каталога. Деньги клуба — евро, только внутри режима (в монеты не
          превращаются). Пирамида ×2 до 10 дивизионов, неделя = предсезонка + 15 туров. Бюджет: грант дивизиона
          + бонус «Клубной базы» (стадион, маркетинг, магазин, бухгалтерия) с потолком.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("manager_enabled", "Режим включён")}
          {field("manager_found_cost", "Основание клуба, монет")}
          {field("manager_min_level", "Мин. уровень «Моего игрока» (менеджер и игроки)")}
          {field("manager_max_live", "«Моих игроков» других пользователей в клубе, максимум")}
          {field("manager_squad_max", "Заявка: живые + футболисты, максимум")}
          {field("manager_league_size", "Клубов в лиге (чётное; туров = клубов − 1)")}
          {field("manager_divisions", "Дивизионов, максимум (пирамида ×2)")}
          {field("manager_promote", "Повышаются из лиги при заполненной пирамиде (вылетают вдвое больше)")}
          {field("manager_preseason_hours", "Предсезонка (трансферное окно): часов от понедельника 00:00 (72 = старт в четверг)")}
          {field("manager_style_edge_pct", "Тактика: бонус к рейтингам стилю, который бьёт стиль соперника, %")}
          {field("manager_formation_effect_pct", "Тактика: сила крена схем в атаку/защиту, %")}
          {field("manager_wage_pct", "Зарплата футболиста за сезон, % стоимости (база)")}
          {field("manager_loan_fee_pct", "Аренда футболиста на сезон, % стоимости")}
          {field("manager_sell_back_pct", "Продажа купленного футболиста системе, % стоимости")}
          {field("manager_live_wage_max", "Антифрод: зарплата живому игроку за сезон, максимум монет")}
          {field("manager_wage_eur_per_coin", "Сколько € бюджета стоит 1 монета зарплаты живому игроку")}
          {field("manager_form_bonus_pct", "Стоимость живого игрока: +% за гол или передачу в клубе")}
          {field("manager_form_bonus_cap", "…максимум, %")}
          {field("manager_income_win", "€ за победу (× % дивизиона)")}
          {field("manager_income_draw", "€ за ничью")}
          {field("manager_income_loss", "€ за поражение")}
          {field("manager_ticket_eur_per_level", "Билеты: € за домашний матч за уровень стадиона базы")}
          {field("manager_sponsor_eur_per_level", "Спонсоры: € за сезон за уровень отдела маркетинга")}
          {field("manager_merch_eur_per_level", "Мерч: € за сезон за уровень клубного магазина")}
          {field("manager_budget_per_base_level", "€ за сезон за каждый уровень «Клубной базы» (здания + академия)")}
          {field("manager_base_bonus_cap_pct", "Бонус базы за сезон не больше, % гранта дивизиона")}
          {field("manager_promotion_bonus_pct", "Бонус за повышение, % гранта нового дивизиона")}
          {field("manager_parachute_pct", "Компенсация за вылет, % разницы грантов")}
          {field("manager_match_xp", "Опыт «Моему игроку» за матч")}
          {field("manager_freshness_cost", "Свежесть «Моего игрока» за матч (0 = не устаёт)")}
          {field("manager_merch_cap_eur", "Мерч: € одному клубу за сезон, максимум")}
          {field("manager_pro_stars", "«Менеджер Pro»: цена, звёзды (0 = не продаётся)")}
          {field("manager_pro_days", "«Менеджер Pro»: дней")}
          {listField("manager_value_ratings", "Шкала стоимости: рейтинги")}
          {listField("manager_value_eur", "…стоимость при этих рейтингах, €")}
          {listField("manager_division_budget", "Грант на сезон по дивизионам, € (1, 2, 3…)")}
          {listField("manager_division_income_pct", "Доход матчей и призы по дивизионам, %")}
          {listField("manager_division_wage_pct", "Зарплаты футболистов по дивизионам, %")}
          {listField("manager_division_rating", "Ориентир рейтинга по дивизионам (автодокупка, боты без живых)")}
          {listField("manager_place_rewards", "Монеты менеджеру за 1–3 места (× % дивизиона)")}
          {listField("manager_place_budget", "€ в бюджет за 1–3 места (× % дивизиона)")}
          {jsonField("manager_slots", "Время туров (местное), по порядку")}
          {jsonField("manager_cosmetics", "Магазин стиля клуба: kind = shape | symbol | kit | frame | theme | stadium_name; coins / stars 0 = не продаётся за них, оба 0 = бесплатно")}
          {jsonField("manager_merch", "Мерч для болельщиков: coins сгорают, eur идут в бюджет клуба")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Магазин: предложение дня</p>
        <p className="mb-3 text-xs text-slate-400">
          Один пак за монеты в день со скидкой, не больше одной покупки на игрока в сутки. Цену считает сервер.
          ID пака 0 — каждый день другой пак из активных паков за монеты.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("shop_daily_offer_enabled", "Включено")}
          {field("shop_daily_offer_discount_pct", "Скидка, % (1–90)")}
          <label className="flex flex-col gap-1">
            <span className="text-xs text-slate-400">ID пака (0 = ротация)</span>
            <input
              type="number"
              min={0}
              value={form.shop_daily_offer_pack_id ?? 0}
              onChange={(e) => setForm({ ...form, shop_daily_offer_pack_id: Number(e.target.value) })}
              className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
            />
          </label>
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Напоминание ботом</p>
        <p className="mb-3 text-xs text-slate-400">
          Раз в день: «ждут награда дня и N выполненных заданий». Только тем, у кого что-то не забрано.
          Обмены, вызовы, «твой ход» и бесплатный пак бот присылает и так.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("bot_daily_digest_enabled", "Включено")}
          {field("bot_daily_digest_hour", "Час отправки (0–23, часовой пояс бота)")}
        </div>
        <p className="mb-3 mt-5 font-display text-sm font-bold">«Возвращайся»</p>
        <p className="mb-3 text-xs text-slate-400">
          Один раз тому, кто не заходил N дней (и пропал не больше 30 дней назад): «давно не виделись, тебя ждут бесплатный
          пак и награда дня». Повторно — только если игрок вернулся и снова пропал.
        </p>
        <div className="grid grid-cols-2 items-end gap-3">
          {toggle("bot_comeback_enabled", "Включено")}
          {field("bot_comeback_days", "Через сколько дней без захода")}
          {field("bot_comeback_hour", "Час отправки (0–23)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Колесо фортуны</p>
        <div className="grid grid-cols-2 gap-3">
          {field("wheel_free_spins_per_day", "Бесплатных прокруток в день")}
          {field("wheel_spin_cost_coins", "Платная прокрутка, монеты")}
          {field("wheel_spin_cost_stars", "Платная прокрутка, ⭐")}
          {field("wheel_duplicate_badge_coins", "Компенсация за повтор значка")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">«21: Добавленное время»</p>
        <p className="mb-3 text-xs text-slate-500">
          Призы победы и «Хет-трика» — Золотое и Джекпот-колесо на странице «Колесо фортуны». Лимит платных 0 = только
          бесплатные партии.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("blackjack_free_per_day", "Бесплатных партий в день")}
          {field("blackjack_stars_cost", "Платная попытка, ⭐")}
          {field("blackjack_paid_daily_limit", "Платных попыток в день (покупок)")}
          {field("blackjack_consolation_coins", "Утешительный приз за поражение, монеты")}
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
        <p className="mb-3 font-display text-base font-bold">Обмены: защита от фарма</p>
        <p className="mb-3 text-xs text-slate-500">
          Отдавать монеты или карточки в обмене (с любой стороны) можно только с аккаунта не младше указанного
          возраста и с нужным числом дней активности; получать можно всем. Лимит — монеты, полученные через обмены за
          текущие сутки (МСК). Налог списывается с получателя монет и сжигается. 0 — правило выключено. Последние два
          поля — пороги блока «Подозрительные обмены» на странице «Аналитика».
        </p>
        <div className="mb-3 flex flex-col gap-2">
          {toggle("trade_coins_enabled", "Монеты в обменах (выкл — только «карточка на карточку»)")}
          {toggle("trade_cards_both_sides", "Карточки обязательны с обеих сторон (без подарков в одну сторону)")}        </div>
        <div className="grid grid-cols-2 gap-3">
          {field("trade_send_min_account_age_days", "Мин. возраст аккаунта, дней")}
          {field("trade_send_min_active_days", "Мин. дней активности")}
          {field("trade_daily_coins_receive_cap", "Лимит получения монет в день")}
          {field("trade_coin_tax_pct", "Налог на монеты, %")}
          {field("trade_suspicious_young_days", "«Молодой» аккаунт — младше, дней")}
          {field("trade_suspicious_min_donors", "Мин. молодых доноров для флага")}
          {field("trade_finder_max_wants", "Поиск обменов: карточек в «Ищу»")}
          {field("trade_finder_max_gives", "Поиск обменов: карточек в «Отдаю»")}
          {field("trade_finder_active_days", "Поиск: партнёр заходил за N дней")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Ставки в вызовах через чат</p>
        <p className="mb-3 text-xs text-slate-500">
          Тактико, Стратего и Пенальти. Ставка — это перевод монет между игроками, поэтому для неё действуют те же
          возраст аккаунта и дни активности, что и для обменов. Лимит пары — сколько матчей на ставку двое игроков
          могут начать за сутки (во всех трёх играх вместе). Лимит выигрыша — сколько игрок может чисто выиграть на
          ставках за сутки. 0 в «Макс. ставке» отключает ставки, в остальных полях — снимает ограничение.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("stake_max_coins", "Макс. ставка с каждой стороны")}
          {field("stake_pair_daily_limit", "Матчей на ставку с одним игроком в день")}
          {field("stake_daily_profit_cap", "Лимит выигрыша на ставках в день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Ценные карточки в обменах</p>
        <p className="mb-3 text-xs text-slate-500">
          Ценные — легендарки, алмазы, «Академия» и лимитки (не выпадают из паков, тираж не больше limited_max_copies).
          Полученные бесплатно (награды, бесплатные паки, колесо, подарки) привязаны к аккаунту и в обмен не идут.
          Отдавать остальные может только «Проверенный аккаунт»: возраст аккаунта и сумма покупок за ⭐ (дни
          активности — по желанию: бот их просто выжидает, а покупки стоят ферме денег за каждый аккаунт). Равноценность: если дорогая сторона стоит не меньше порога, дешёвая должна стоить не меньше указанного
          процента от неё (0 — правило выключено). Ценность в монетах — по таблице ниже (у остальных карточек — цена
          продажи системе × sell_multiplier). Задания и бинго засчитывают не больше N обменов в день с одним игроком.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("trade_verified_min_age_days", "Проверенный: возраст аккаунта, дней")}
          {field("trade_verified_min_active_days", "Проверенный: дней активности (0 — не нужно)")}
          {field("trade_verified_min_stars", "Проверенный: потрачено ⭐ всего (0 — не нужно)")}
          {field("trade_min_value_ratio_pct", "Равноценность: мин. %")}
          {field("trade_value_check_min", "Равноценность: проверять от ценности")}
          {field("trade_progress_pair_daily", "Обменов с одним игроком в день для заданий")}
          {jsonField("card_values", "Таблица ценности (монеты): legendary, legendary_top (+ legendary_top_rating), limited_*, diamond, academy [по стадиям 0–4], sell_multiplier")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-3 font-display text-base font-bold">Магазин: ускорители продаж</p>
        <p className="mb-3 text-xs text-slate-500">
          0 — выключено. Гарант: платный пак за монеты с шансом на легендарку, который идёт после N−1 таких паков без
          легендарки, даёт легендарку; игрок видит «гарантирована через N паков». Скидка ×10 — на открытие 10+ одинаковых
          паков разом. Бонус первой покупки — процент сверху на первую покупку монет за Stars (раз на игрока).
          Рекомендуем начать с гаранта 40, скидки 10% и бонуса 100%.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("pity_packs", "Гарант легендарки: паков")}
          {field("bulk10_discount_pct", "Скидка на ×10, %")}
          {field("first_coin_purchase_bonus_pct", "Бонус первой покупки монет, %")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Рефералы</p>
        <p className="mb-3 text-xs text-slate-500">
          Друг засчитывается, когда поиграл указанное число разных дней (не за пак — паки бывают бесплатные).
          Тогда оба получают монеты, а пригласивший — награды лестницы, когда число друзей дойдёт до порога.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("referral_referred_reward", "Награда приглашённому")}
          {field("referral_referrer_reward", "Награда пригласившему")}
          {field("referral_active_days", "Дней игры, чтобы друг засчитался")}
        </div>
        <p className="mb-1 mt-4 text-xs text-slate-400">Лестница: награда за N засчитанных друзей</p>
        <div className="flex flex-col gap-3">
          {(form.referral_milestones ?? []).map((m, i) => (
            <div key={i} className="rounded-xl bg-bg-base/60 p-2">
              <div className="mb-1 flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-slate-300">
                  Друзей
                  <input
                    type="number"
                    value={m.count}
                    onChange={(e) => {
                      const rows = [...form.referral_milestones];
                      rows[i] = { ...m, count: Number(e.target.value) };
                      setForm({ ...form, referral_milestones: rows });
                    }}
                    className="w-20 rounded-lg bg-bg-surface px-2 py-1 outline-none"
                  />
                </label>
                <button
                  onClick={() => setForm({ ...form, referral_milestones: form.referral_milestones.filter((_, j) => j !== i) })}
                  className="ml-auto text-xs text-red-400"
                >
                  Убрать
                </button>
              </div>
              <RewardBundleEditor
                value={m}
                onChange={(next) => {
                  const rows = [...form.referral_milestones];
                  rows[i] = { ...next, count: m.count };
                  setForm({ ...form, referral_milestones: rows });
                }}
              />
            </div>
          ))}
          <button
            onClick={() => setForm({
              ...form,
              referral_milestones: [...(form.referral_milestones ?? []), { ...EMPTY_BUNDLE, count: 1 }],
            })}
            className="self-start rounded-lg bg-white/10 px-3 py-1.5 text-xs"
          >
            + Ступень
          </button>
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Награды за дни подряд</p>
        <p className="mb-3 text-xs text-slate-500">
          Памятный подарок за N дней подряд в игре: выдаётся автоматически один раз и показывается попапом с анимацией.
        </p>
        <div className="flex flex-col gap-3">
          {(form.streak_rewards ?? []).map((m, i) => (
            <div key={i} className="rounded-xl bg-bg-base/60 p-2">
              <div className="mb-1 flex items-center gap-2">
                <label className="flex items-center gap-1 text-xs text-slate-300">
                  Дней подряд
                  <input
                    type="number"
                    value={m.days}
                    onChange={(e) => {
                      const rows = [...form.streak_rewards];
                      rows[i] = { ...m, days: Number(e.target.value) };
                      setForm({ ...form, streak_rewards: rows });
                    }}
                    className="w-20 rounded-lg bg-bg-surface px-2 py-1 outline-none"
                  />
                </label>
                <button
                  onClick={() => setForm({ ...form, streak_rewards: form.streak_rewards.filter((_, j) => j !== i) })}
                  className="ml-auto text-xs text-red-400"
                >
                  Убрать
                </button>
              </div>
              <RewardBundleEditor
                value={m}
                onChange={(next) => {
                  const rows = [...form.streak_rewards];
                  rows[i] = { ...next, days: m.days };
                  setForm({ ...form, streak_rewards: rows });
                }}
              />
            </div>
          ))}
          <button
            onClick={() => setForm({ ...form, streak_rewards: [...(form.streak_rewards ?? []), { ...EMPTY_BUNDLE, days: 30 }] })}
            className="self-start rounded-lg bg-white/10 px-3 py-1.5 text-xs"
          >
            + Порог
          </button>
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
        <p className="mb-3 text-xs text-slate-500">
          Итоговая награда = (награда ниже × множитель сложности × множитель дивизиона) + 5 монет за каждый забитый
          гол — этот бонус за голы не настраивается отдельно. Игрок всегда играет на среднем множителе (выбора сложности в интерфейсе нет).
          Множители сложности общие с ботом Тактико (раздел ниже) — «сложный» там сейчас недостижим, так как в Тактико
          оставлены только лёгкий и продвинутый уровни.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("match_reward_win", "Награда за победу (без бонуса за голы)")}
          {field("match_reward_draw", "Награда за ничью (без бонуса за голы)")}
          {field("match_reward_loss", "Награда за поражение (без бонуса за голы)")}
          {field("difficulty_easy_multiplier", "Множитель: лёгкий")}
          {field("difficulty_medium_multiplier", "Множитель: средний (всегда применяется в Card Arena)")}
          {field("difficulty_hard_multiplier", "Множитель: сложный (только бот Тактико — недостижим)")}
          {field("suspicious_score_margin", "Порог подозрительной разницы счёта")}
          {field("match_max_diamond_cards", "Макс. диамантовых карт в составе")}
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
        <p className="mb-1 font-display text-base font-bold">Card Arena — дивизионы</p>
        <p className="mb-3 text-xs text-slate-500">
          Очки арены считаются как Эло: за победу над соперником с теми же очками +K/2, за поражение −K/2; против
          соперника выше по очкам победа дороже, против более слабого — поражение дороже. Дивизион N — N-е значение
          списков ниже (первый порог всегда 0). Награда за дивизион выдаётся один раз — при первом достижении.
          Рейтинг арены для общей «Лиги» (+3/+1/−1) не меняется.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {listField("arena_division_min_points", "Пороги очков по дивизионам (1, 2, 3, …)")}
          {listField("arena_division_reward_coins", "Награда за первое достижение дивизиона, монеты")}
          {listField("arena_division_coin_pct", "Множитель монет за матч по дивизионам, %")}
          {field("arena_points_k", "K — максимум очков за матч")}
          {field("arena_points_scale", "Шкала Эло (разница очков для 10:1)")}
          {field("arena_shield_matches", "Матчей защиты от вылета после повышения")}
          {field("arena_matchmaking_window", "Окно подбора соперника, ± очков")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Card Arena — баланс и стили</p>
        <p className="mb-3 text-xs text-slate-500">
          Насколько разница в силе решает исход. По умолчанию: перевес 30% ≈ 87% побед и ≈3% поражений, равные
          ≈ 46/27/27. Показатель «шанс на победу» перед матчем берётся из таблицы симуляции
          (backend/scripts/simulate_arena_balance.py --write) — после сильных изменений здесь её стоит пересчитать.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("arena_style_matchup_bonus_pct", "Бонус выигранного матчапа стилей, % к силе")}
          {field("arena_share_exponent", "Степень доли моментов (атака vs защита)")}
          {field("arena_shot_exponent", "Степень частоты опасных моментов")}
          {field("arena_edge_rating_per_10pct", "Очков рейтинга в каждом розыгрыше за +10% силы")}
          {field("arena_edge_rating_max", "Максимум этих очков")}
          {field("arena_formation_effect_pct", "Влияние схемы на атаку/защиту, % (100 — 3-4-3 даёт +4%/−4%, 0 — выкл.)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Футбольный фанат</p>
        <p className="mb-3 text-xs text-slate-500">
          Награда за уровень = базовая награда × число стюардов на линии × (рост ^ (уровень − 1)), т.е. растёт с каждым
          пройденным уровнем.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("saboteur_line_base_reward", "Базовая награда за уровень")}
          {field("saboteur_line_growth", "Рост награды за уровень (напр. 1.15)")}
          {field("saboteur_max_steward_count", "Макс. число стюардов на линии")}
          {field("saboteur_daily_limit", "Лимит наградных попыток/день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Пенальти</p>
        <p className="mb-3 text-xs text-slate-500">
          Серия пенальти продолжается до победителя (доп. удары при ничьей), поэтому «Награда за ничью» никогда не
          выплачивается — оставлена про запас на случай, если формат матча изменится.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("penalty_reward_win", "Награда за победу")}
          {field("penalty_reward_draw", "Награда за ничью (сейчас недостижима)")}
          {field("penalty_reward_loss", "Награда за поражение")}
          {field("penalty_bot_miss_chance", "Шанс промаха бота (0-1)")}
          {field("penalty_placement_max_pct", "Гол, даже если вратарь угадал: % у карты 99 (у 58 — 0)")}
          {field("penalty_daily_limit", "Лимит наградных попыток/день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Штрафной удар (3D)</p>
        <p className="mb-3 text-xs text-slate-500">
          Серия ударов с разных позиций; каждый удар сервер пересчитывает сам. «В угол» — гол у штанги или под
          перекладиной, «с закруткой» — гол заметно закрученным ударом.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("free_kick_hourly_limit", "Серий в час")}
          {field("free_kick_3d_kicks", "Ударов в серии")}
          {field("free_kick_daily_limit", "Наградных серий в день")}
          {field("free_kick_3d_goal_coins", "Монет за гол")}
          {field("free_kick_3d_corner_bonus", "Бонус «в угол»")}
          {field("free_kick_3d_curl_bonus", "Бонус «с закруткой»")}
          {field("free_kick_3d_near_coins", "За сейв или штангу")}
          {field("free_kick_refill_daily_limit", "Платных обновлений серии в день")}
          {field("free_kick_refill_coins", "Первое обновление за день, монет")}
          {field("free_kick_refill_stars", "Следующие обновления, звёзд")}
        </div>
        <p className="mb-2 mt-4 text-xs text-slate-500">Классическая версия (шкала) — сохранена, в меню не показывается</p>
        <div className="grid grid-cols-2 gap-3">
          {field("free_kick_period_min_ms", "Мин. период шкалы, мс")}
          {field("free_kick_period_max_ms", "Макс. период шкалы, мс")}
          {field("free_kick_base_stake", "Базовая ставка")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Тактико</p>
        <p className="mb-3 text-xs text-slate-500">
          Награда за бот-матч = награда ниже × множитель сложности из раздела «Card Arena» выше (свои множители тут не
          настраиваются). В Тактико сейчас доступны только лёгкий и продвинутый (средний множитель) уровни — «сложный»
          отключён.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("tactico_challenge_expiry_hours", "Срок жизни вызова, часы")}
          {field("tactico_round_timeout_hours", "Тайм-аут на раунд, часы")}
          {field("tactico_phase_bonus_pct", "Бонус за фазу (0-1)")}
          {field("tactico_reward_win", "Награда за победу (бот)")}
          {field("tactico_reward_draw", "Награда за ничью (бот)")}
          {field("tactico_reward_loss", "Награда за поражение (бот)")}
          {field("tactico_bot_optimal_pick_chance_easy", "Точность бота: лёгкий (0-1)")}
          {field("tactico_bot_optimal_pick_chance_medium", "Точность бота: продвинутый (0-1)")}
          {field("tactico_bot_optimal_pick_chance_hard", "Точность бота: сложный (0-1, недостижим)")}
          {field("tactico_max_legendary_cards", "Макс. легендарных карт в составе")}
          {field("tactico_max_epic_cards", "Макс. эпических карт в составе")}
          {field("tactico_max_diamond_cards", "Макс. диамантовых карт в составе")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Футбольное Стратего</p>
        <p className="mb-3 text-xs text-slate-500">
          Фишки: Кубок + стенки + Звезда + Провокатор + подкатчики + скорости + обычные игроки — все должны помещаться в
          два ряда поля. На поле 8×8 и больше в центре две лужи 1×2. Размер поля, состав и лимит ходов применяются к новым матчам; идущие матчи доигрываются по старым
          настройкам. Награда (и с ботом, и с соперником) — в пределах дневного лимита каждого игрока; сдавшийся или
          пропустивший ходы получает 0.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("stratego_board_size", "Размер поля (5-10; лужи с 8)")}
          {field("stratego_wall_count", "Число стенок")}
          {field("stratego_tackler_count", "Подкатчиков")}
          {field("stratego_speedster_count", "Скоростей")}
          {field("stratego_regular_count", "Обычных игроков")}
          {field("stratego_move_limit", "Лимит ходов (обоих)")}
          {field("stratego_max_legendary_cards", "Макс. легендарных в составе")}
          {field("stratego_max_diamond_cards", "Макс. диамантовых в составе")}
          {field("stratego_min_rare_cards", "Мин. редких в составе")}
          {field("stratego_min_common_cards", "Мин. обычных в составе")}
          {field("stratego_my_player_xp", "Опыт «Моему игроку» за матч")}
          {field("stratego_bot_easy_reward_pct", "Лёгкий бот: % от награды")}
          {field("stratego_live_move_seconds", "Онлайн: секунд на ход")}
          {field("stratego_skill_bonus_per_level", "Навык карты: +сила за уровень")}
          {field("stratego_puzzle_reward", "Награда за «Задачу дня»")}
          {(
            [
              ["stratego_tackler_max_rarity", "Макс. редкость Подкатчика"],
              ["stratego_provocateur_max_rarity", "Макс. редкость Провокатора"],
              ["stratego_speedster_max_rarity", "Макс. редкость Скорости"],
            ] as const
          ).map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{label}</span>
              <select
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value as GameConfig[typeof key] })}
                className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
              >
                <option value="common">Обычная</option>
                <option value="rare">Редкая</option>
                <option value="epic">Эпическая</option>
                <option value="legendary">Легендарная</option>
                <option value="diamond">Диамантовая (без ограничения)</option>
              </select>
            </label>
          ))}
          {field("stratego_challenge_expiry_hours", "Срок жизни вызова, часы")}
          {field("stratego_move_timeout_hours", "Тайм-аут на ход, часы")}
          {field("stratego_max_auto_moves", "Автоходов подряд до поражения")}
          {field("stratego_reward_win", "Награда за победу")}
          {field("stratego_reward_draw", "Награда за ничью")}
          {field("stratego_reward_loss", "Награда за поражение")}
          {field("stratego_daily_limit", "Лимит наградных матчей/день")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Путь дебютанта</p>
        <p className="mb-3 text-xs text-slate-500">
          Для игроков, зарегистрированных после включения: первым экраном — пак с гарантированной картой, затем пак
          «Твоя команда» (11 игроков под 4-3-3, состав собирается сам), карта за первый матч Арены, задания «попробуй
          режим», подарок 2-го и 3-го дня. Стартовое предложение для них открывается со 2-го дня. Все подарочные карты
          закреплены: играть можно, продать/обменять/сжечь — только через указанное число дней.
        </p>
        <div className="mb-3">{toggle("newbie_enabled", "Путь дебютанта включён")}</div>
        <div className="grid grid-cols-2 gap-3">
          {textListField("newbie_first_pack_rarities", "Первый пак: редкости карт (через запятую)")}
          {(["newbie_squad_rarity", "newbie_arena_rarity", "newbie_day3_rarity"] as const).map((key) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">
                {key === "newbie_squad_rarity" ? "Редкость команды" : key === "newbie_arena_rarity" ? "Карта за 1-й матч Арены" : "Карта 3-го дня"}
              </span>
              <select
                value={form[key]}
                onChange={(e) => setForm({ ...form, [key]: e.target.value })}
                className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
              >
                <option value="common">Обычная</option>
                <option value="rare">Редкая</option>
                <option value="epic">Эпическая</option>
                <option value="legendary">Легендарная</option>
              </select>
            </label>
          ))}
          {field("newbie_day2_coins", "Монет на 2-й день")}
          {field("newbie_bound_days", "Дней без продажи/обмена подарков")}
          {field("newbie_reminder_hour", "Бот: час напоминания о подарке дня")}
          {field("newbie_finale_coins", "Финал «Путь пройден»: монет")}
          {field("newbie_finale_pack_id", "Финал: id пака (0 — нет)")}
          {field("newbie_finale_badge_id", "Финал: id значка (0 — нет)")}
          {jsonField("newbie_tasks", "Задания «попробуй режим» (code, label, mode, path, coins, pack_id)")}
        </div>
        <NewbieFunnelView />
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Топ недели</p>
        <p className="mb-3 text-xs text-slate-500">
          В понедельник ночью лучшие места каждого отмеченного рейтинга получают награду своего места (монеты, пак,
          карточка, значок, рамка) и видят попап. Рейтинги-«очки» награждают только тех, кто поднялся выше стартового
          значения. «Игр / звёзд / рефералов за неделю» считаются за прошедшую неделю.
        </p>
        <div className="mb-3">{toggle("weekly_top_enabled", "Награды топа недели включены")}</div>
        <div className="mb-3 grid grid-cols-2 gap-3">{field("weekly_top_size", "Сколько мест награждать")}</div>
        <p className="mb-1 text-xs text-slate-400">Рейтинги с наградами (ничего не отмечено — все)</p>
        <div className="mb-3 grid grid-cols-2 gap-1 sm:grid-cols-3">
          {WEEKLY_TOP_METRICS.map(([code, label]) => (
            <label key={code} className="flex items-center gap-2 text-xs">
              <input
                type="checkbox"
                checked={(form.weekly_top_metrics ?? []).includes(code)}
                onChange={(e) => setForm({
                  ...form,
                  weekly_top_metrics: e.target.checked
                    ? [...(form.weekly_top_metrics ?? []), code]
                    : (form.weekly_top_metrics ?? []).filter((m) => m !== code),
                })}
              />
              {label}
            </label>
          ))}
        </div>
        <div className="flex flex-col gap-3">
          {Array.from({ length: form.weekly_top_size || 0 }, (_, i) => (
            <div key={i}>
              <p className="mb-1 text-xs font-semibold text-slate-300">{i + 1}-е место</p>
              <RewardBundleEditor
                value={(form.weekly_top_rewards ?? [])[i] ?? EMPTY_BUNDLE}
                onChange={(next) => {
                  const ladder = [...(form.weekly_top_rewards ?? [])];
                  while (ladder.length < i) ladder.push(EMPTY_BUNDLE);
                  ladder[i] = next;
                  setForm({ ...form, weekly_top_rewards: ladder });
                }}
              />
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Контратака</p>
        <p className="mb-3 text-xs text-slate-500">
          Отряд из 5 карт: арена против защиты других игроков (или ботов) и босс недели. Награды арены — в пределах
          дневного лимита; у босса — по порогам урона за попытку. Шанс выпадения комплекта — в процентах.
        </p>
        <div className="mb-3">{toggle("kontra_enabled", "Режим включён (выкл — нельзя начинать бои, плитка скрыта)")}</div>
        <div className="grid grid-cols-2 gap-3">
          {field("kontra_arena_reward_win", "Арена: монет за победу")}
          {field("kontra_arena_reward_loss", "Арена: монет за поражение")}
          {field("kontra_daily_limit", "Арена: наградных боёв в день")}
          {field("kontra_rating_win", "Арена: рейтинг за победу")}
          {field("kontra_rating_loss", "Арена: рейтинг за поражение")}
          {field("kontra_arena_max_rounds", "Арена: максимум ходов соперника")}
          {field("kontra_boss_daily_attempts", "Босс: попыток в день")}
          {field("kontra_boss_max_rounds", "Босс: ходов босса за попытку")}
          {field("kontra_boss_week_hp", "Босс: HP за неделю (фазы)")}
          {field("kontra_gear_drop_boss_pct", "Комплект с босса, %")}
          {field("kontra_gear_drop_arena_pct", "Комплект за победу на арене, %")}
          {field("kontra_chest_coins", "Сундук комплекта, монет (0 — нет)")}
          {field("kontra_chest_stars", "Сундук комплекта, ⭐ (0 — нет)")}
        </div>
        <label className="mt-3 flex flex-col gap-1">
          <span className="text-xs text-slate-400">Босс: награда за урон попытки — строки «урон монеты»</span>
          <textarea
            rows={5}
            value={(form.kontra_boss_reward_tiers ?? []).map(([d, c]) => `${d} ${c}`).join("\n")}
            onChange={(e) => setForm({
              ...form,
              kontra_boss_reward_tiers: e.target.value.split("\n").map((l) => l.trim().split(/\s+/).map(Number))
                .filter((p) => p.length === 2 && p.every(Number.isFinite)) as [number, number][],
            })}
            className="rounded-lg bg-bg-surface px-3 py-2 font-mono text-xs outline-none"
          />
        </label>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Мордобой</p>
        <p className="mb-3 text-xs text-slate-500">
          Боксёрский поединок на одной карточке: раунды из обменов, в каждом оба тайно выбирают действие. Число раундов,
          обменов и HP применяются к новым боям. Награда — в пределах дневного лимита игрока; за нокаут победитель
          получает бонус; сдавшийся или пропустивший удары получает 0. Бой с другом рейтинг не двигает, онлайн — ×2.
        </p>
        <div className="mb-3">{toggle("mordoboi_enabled", "Режим включён (выкл — нельзя начинать новые бои, плитка скрыта)")}</div>
        <div className="grid grid-cols-2 gap-3">
          {field("mordoboi_rounds", "Раундов")}
          {field("mordoboi_exchanges_per_round", "Обменов в раунде")}
          {field("mordoboi_base_hp", "HP боксёра")}
          {field("mordoboi_reward_win", "Награда за победу")}
          {field("mordoboi_reward_draw", "Награда за ничью")}
          {field("mordoboi_reward_loss", "Награда за поражение")}
          {field("mordoboi_reward_ko_bonus", "Бонус за нокаут")}
          {field("mordoboi_daily_limit", "Лимит наградных боёв/день")}
          {field("mordoboi_bot_easy_reward_pct", "Лёгкий бот: % от награды")}
          {field("mordoboi_challenge_expiry_hours", "Срок жизни вызова, часы")}
          {field("mordoboi_move_timeout_hours", "С другом: часов на удар")}
          {field("mordoboi_live_move_seconds", "Онлайн: секунд на удар")}
          {field("mordoboi_max_auto_moves", "Автоударов подряд до поражения")}
          {field("mordoboi_legend_rating", "«Легенда ринга»: рейтинг босса")}
          {field("mordoboi_legend_reward", "«Легенда ринга»: награда (раз в день)")}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Футбольный магнат</p>
        <p className="mb-3 text-xs text-slate-500">
          Деньги партии («М») — отдельная валюта, не монеты. Правила, поле и карточки фиксируются в партии при её старте —
          идущие партии доигрываются по старым настройкам; награды и лимиты считаются при завершении. Круг — каждый игрок
          ходит по разу. Партия с одним человеком (против ботов или лобби, куда никто не пришёл) платит указанный %
          от наград. Ушедший или замененный ботом игрок награды не получает.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {field("magnate_start_money", "Стартовый бюджет, М")}
          {field("magnate_pass_start_bonus", "За проход старта, М")}
          {field("magnate_fine_amount", "Штраф федерации, М")}
          {field("magnate_jail_fine", "Штраф за выход из дисквалификации, М")}
          {field("magnate_max_jail_turns", "Бросков в дисквалификации до штрафа")}
          {field("magnate_building_sell_pct", "Возврат за постройку при долге, %")}
          {field("magnate_max_rounds", "Кругов в партии")}
          {field("magnate_time_limit_minutes", "Лимит времени партии, мин")}
          {field("magnate_turn_seconds", "Время на решение, с")}
          {field("magnate_max_missed_turns", "Пропусков подряд до замены ботом")}
          {field("magnate_lobby_wait_seconds", "Ожидание лобби до ботов, с")}
          {field("magnate_room_wait_minutes", "Ожидание комнаты друзей, мин")}
          {field("magnate_bot_buy_reserve", "Бот покупает, если остаётся ≥ М")}
          {field("magnate_bot_build_reserve", "Бот строит, если остаётся ≥ М")}
          {field("magnate_bot_reward_pct", "Награда за стол с ботами, %")}
          {field("magnate_daily_limit", "Лимит наградных партий/день")}
          {listField("magnate_place_rewards", "Монеты по месту (1-е, 2-е, 3-е, 4-е)")}
          {listField("magnate_stadium_rents", "Аренда стадиона при 1, 2, 3, 4 стадионах, М")}
        </div>
        <AdminMagnateBoardEditor
          board={form.magnate_board}
          cards={form.magnate_cards}
          onChange={(board, cards) => setForm({ ...form, magnate_board: board, magnate_cards: cards })}
        />
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

const STAR_RARITY_LABELS: Record<string, string> = { common: "Обычная", rare: "Редкая", epic: "Эпическая", legendary: "Легендарная" };

function StarLadderRow({
  rarity, dupes, coins, onChange,
}: {
  rarity: string;
  dupes: number[];
  coins: number[];
  onChange: (kind: "card_star_dupes_per_level" | "card_star_coin_cost", values: number[]) => void;
}) {
  const parse = (value: string) => value.split(",").map((v) => Number(v.trim())).filter((v) => Number.isFinite(v) && v >= 0);
  return (
    <>
      <span className="text-slate-400">{STAR_RARITY_LABELS[rarity]}</span>
      <input
        key={`d-${dupes.join(",")}`}
        defaultValue={dupes.join(", ")}
        onBlur={(e) => onChange("card_star_dupes_per_level", parse(e.target.value))}
        aria-label={`Дубли за звёзды: ${STAR_RARITY_LABELS[rarity]}`}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
      <input
        key={`c-${coins.join(",")}`}
        defaultValue={coins.join(", ")}
        onBlur={(e) => onChange("card_star_coin_cost", parse(e.target.value))}
        aria-label={`Монеты за звёзды: ${STAR_RARITY_LABELS[rarity]}`}
        className="rounded-lg bg-bg-surface px-3 py-2 outline-none"
      />
    </>
  );
}

function NewbieFunnelView() {
  const [days, setDays] = useState(7);
  const { data } = useQuery({ queryKey: ["admin", "newbie-funnel", days], queryFn: () => fetchNewbieFunnel(days) });
  return (
    <div className="mt-4 rounded-xl bg-bg-base/60 p-3">
      <div className="mb-2 flex items-center justify-between gap-2">
        <p className="text-sm font-semibold">Воронка дебютантов</p>
        <select value={days} onChange={(e) => setDays(Number(e.target.value))} className="rounded-lg bg-bg-surface px-2 py-1 text-xs">
          <option value={1}>1 день</option>
          <option value={7}>7 дней</option>
          <option value={30}>30 дней</option>
        </select>
      </div>
      {!data ? (
        <p className="text-xs text-slate-500">Загрузка…</p>
      ) : (
        <div className="flex flex-col gap-1 text-xs">
          <p className="text-slate-400">
            Начали: <b className="text-slate-200">{data.started}</b> · прошли полностью: <b className="text-slate-200">{data.completed}</b>
          </p>
          {data.steps.map((s) => {
            const pct = data.started ? Math.round((s.players / data.started) * 100) : 0;
            return (
              <div key={s.code} className="flex items-center gap-2">
                <span className="w-1/2 min-w-0 truncate text-slate-300">{s.label}</span>
                <span className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/10">
                  <span className="block h-full rounded-full bg-accent-lime" style={{ width: `${pct}%` }} />
                </span>
                <span className="w-16 shrink-0 text-right font-mono tabular-nums text-slate-300">
                  {s.players} · {pct}%
                </span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}
