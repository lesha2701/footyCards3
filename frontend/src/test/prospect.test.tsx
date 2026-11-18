import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useLocation } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import {
  answerProspectStory, challengeProspectDuel, chooseProspectPosition, chooseProspectSpec, createProspect, fetchProspect, graduateProspect, trainProspect,
  type Prospect, type ProspectGraduate, type ProspectView,
} from "@/api/prospect";
import ProspectPage from "@/pages/ProspectPage";

vi.mock("@/api/prospect", () => ({
  fetchProspect: vi.fn(),
  createProspect: vi.fn(),
  updateProspect: vi.fn(),
  trainProspect: vi.fn(),
  answerProspectStory: vi.fn(),
  setProspectMentor: vi.fn(),
  buyProspectCosmetic: vi.fn(),
  equipProspectCosmetic: vi.fn(),
  createProspectInvoice: vi.fn(),
  fetchProspectInvoiceStatus: vi.fn(),
  chooseProspectSpec: vi.fn(),
  chooseProspectPosition: vi.fn(),
  graduateProspect: vi.fn(),
  challengeProspectDuel: vi.fn(),
}));

const LOOK = { skin: 1, hair: 1, hair_color: 1, beard: 0, eye_color: 0, kit: 3, kit_pattern: 0 };
const STAGES = [
  { code: "yard", name: "Двор", emoji: "⚽", about: "", from_age: 6, cap: 38 },
  { code: "school", name: "Детская школа", emoji: "🏫", about: "", from_age: 9, cap: 52 },
  { code: "youth", name: "Юноши", emoji: "🎽", about: "", from_age: 12, cap: 66 },
  { code: "u19", name: "U-19", emoji: "🔥", about: "", from_age: 15, cap: 78 },
  { code: "debut", name: "Дебют", emoji: "👑", about: "", from_age: 18, cap: null },
];

const kid = (over: Partial<Prospect> = {}): Prospect => ({
  name: "Лёва Мяч", number: 7, position: "ST", foot: "left", appearance: LOOK, age: 7, age_days: 10,
  days_to_birthday: 6, stage: 0, stage_code: "yard", rating: 30, stage_cap: 38, capped: false, banked_points: 0,
  xp: 2000, xp_in_point: 0, xp_per_point: 400, potential: null, peak: null, days_to_next_stage: 14,
  background: "bg_yard", accessory: null, owned_cosmetics: ["bg_yard"], stats: { matches: 3, goals: 2, wins: 1, trainings: 4 },
  memories: [{ day: "2026-11-01", code: "born", text: "⚽ Первый мяч в 6 лет" }], atk_def: [33, 27], generation: 1, specs: [],
  peak_bonus: { dynasty: 0, academy: 0 }, universal: true, line: "MID", deficit: null, ...over,
});

const view = (over: Partial<ProspectView> = {}): ProspectView => ({
  enabled: true, balance: 5000, stages: STAGES, positions: ["ST"], appearance_options: { skin: 6, hair: 14, hair_color: 7, beard: 5, eye_color: 6, kit: 10, kit_pattern: 4 },
  days_per_year: 8, start_age: 6, peak_range: [82, 90], prospect: kid(), xp_today: 40, daily_xp_cap: 320,
  otvetka_xp: { match: 40, goal: 15, win: 30 }, match_rating: 75, bonus: { academy: 4, mentor: 0, coach: 0 }, bonus_pct: 4,
  coach: { active: false, until: null, stars: 99, days: 7, pct: 25 }, scout: { stars: 25, revealed: false }, mentor: null,
  mentor_options: [],
  training: { free_available: true, extra_credits: 0, extra_bought_today: 0, extra_max: 3, extra_stars: 15, xp: 60, streak: 2,
    streak_days: 7, streak_bonus_xp: 200, drills: [{ code: "finish", title: "Удары по воротам", line: "FWD" }, { code: "dribble", title: "Дриблинг", line: "FWD" }, { code: "speed", title: "Рывки", line: "FWD" }],
    universal: false },
  story: { code: "rain", title: "Ливень", text: "За окном ливень.", options: [
    { label: "Всё равно пойти с мячом", xp: 50, coins: 0, chance: null, win_xp: null, trial: false },
    { label: "Смотреть футбол дома", xp: 25, coins: 0, chance: null, win_xp: null, trial: false },
  ] },
  rival: { name: "Марк Орлов", rating: 29, ahead: 1 },
  cohort: { key: "2026-W46", size: 2, place: 1, top: [{ place: 1, user_id: 1, name: "Лёва Мяч", owner: "Я", rating: 30, me: true }] },
  shop: [{ code: "bg_gym", kind: "background", name: "Спортзал школы", emoji: "🏫", coins: 3000, stars: 0, owned: false }],
  ...over,
});

function OtvetkaProbe() {
  const { search } = useLocation();
  return <p>otvetka page{search}</p>;
}

const GRAD: ProspectGraduate = {
  id: 5, user_id: 1, name: "Тимур Гол", number: 9, position: "ST", appearance: LOOK, rating: 84, potential: 4, generation: 1,
  status: "graduate", graduated_at: "2026-11-10T10:00:00Z", specs: [{ code: "finisher", name: "Бомбардир", emoji: "🎯", about: "" }],
  stats: { matches: 40, goals: 31, wins: 22 }, background: "bg_gold", owner: "Я",
};

function renderPage() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={["/academy/prospect"]}>
        <Routes>
          <Route path="/academy/prospect" element={<ProspectPage />} />
          <Route path="/play/otvetka" element={<OtvetkaProbe />} />
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProspectPage", () => {
  beforeEach(() => {
    vi.mocked(fetchProspect).mockReset();
    vi.mocked(trainProspect).mockReset();
    vi.mocked(answerProspectStory).mockReset();
    vi.mocked(createProspect).mockReset();
    vi.mocked(chooseProspectSpec).mockReset();
    vi.mocked(graduateProspect).mockReset();
    vi.mocked(challengeProspectDuel).mockReset();
  });

  it("offers the constructor when there is no prospect yet", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({ prospect: null }));
    vi.mocked(createProspect).mockResolvedValue(view());
    renderPage();
    expect(await screen.findByText("🌱 Новый воспитанник")).toBeInTheDocument();
    const start = screen.getByRole("button", { name: "Начать путь" });
    expect(start).toBeDisabled();
    fireEvent.change(screen.getByPlaceholderText("Например, Лёва Мячиков"), { target: { value: "Лёва Мяч" } });
    fireEvent.click(start);
    await waitFor(() => expect(createProspect).toHaveBeenCalledWith(expect.objectContaining({ name: "Лёва Мяч" })));
    expect(vi.mocked(createProspect).mock.calls[0][0]).not.toHaveProperty("position");
    expect(await screen.findByText("Воспитанник Академии")).toBeInTheDocument();
  });

  it("shows age, stage, hidden potential, the story and trains", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view());
    vi.mocked(trainProspect).mockResolvedValue({ drill: "Дриблинг", grade: 3, xp: 78, streak_bonus: 0, potential_up: false, view: view({ training: { ...view().training!, free_available: false } }) });
    renderPage();
    expect(await screen.findByText("Лёва Мяч")).toBeInTheDocument();
    expect(screen.getByText("7 лет")).toBeInTheDocument();
    expect(screen.getByText("★ ?")).toBeInTheDocument();
    expect(screen.getByText("Ливень")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Дриблинг" }));
    expect(await screen.findByText(/Дриблинг: ⭐⭐⭐ · \+78 опыта/)).toBeInTheDocument();
  });

  it("answers a story fork", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view());
    vi.mocked(answerProspectStory).mockResolvedValue({ won: null, xp: 52, potential_up: false, trial_credit: false, coins_spent: 0, view: view({ story: null }) });
    renderPage();
    fireEvent.click(await screen.findByText("Всё равно пойти с мячом"));
    await waitFor(() => expect(answerProspectStory).toHaveBeenCalledWith("rain", 0));
    expect(await screen.findByText("+52 опыта")).toBeInTheDocument();
    expect(screen.queryByText("Ливень")).not.toBeInTheDocument();
  });

  it("sends the prospect onto the pitch in «Ответка»", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view());
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "На поле" }));
    expect(await screen.findByText("otvetka page?prospect=1")).toBeInTheDocument();
  });

  it("growth tab shows the rival and the cohort", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view());
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Рост" }));
    expect(screen.getByText(/Ровесник-соперник: Марк Орлов/)).toBeInTheDocument();
    expect(screen.getByText("Набор 2026-W46")).toBeInTheDocument();
    expect(screen.getByText(/Тренировочная база Академии: \+4%/)).toBeInTheDocument();
  });

  it("picks a talent on a new stage", async () => {
    const options = [
      { code: "finisher", name: "Бомбардир", emoji: "🎯", about: "", effects: { goal_pct: 25, atk: 2 } },
      { code: "wall", name: "Стена", emoji: "🧱", about: "", effects: { match_pct: 15 } },
      { code: "engine", name: "Мотор", emoji: "⚡", about: "", effects: { train_pct: 20 } },
    ];
    vi.mocked(fetchProspect).mockResolvedValue(view({ spec_pick: { options, number: 1 } }));
    vi.mocked(chooseProspectSpec).mockResolvedValue(view({ spec_pick: null, prospect: kid({ specs: [options[0]] }) }));
    renderPage();
    expect(await screen.findByText("Кем он станет?")).toBeInTheDocument();
    expect(screen.getByText("+25% опыта за голы · +2 к атаке")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Бомбардир/ }));
    await waitFor(() => expect(chooseProspectSpec).toHaveBeenCalledWith("finisher"));
    expect(await screen.findByText("🎯 Талант: Бомбардир")).toBeInTheDocument();
    expect(screen.queryByText("Кем он станет?")).not.toBeInTheDocument();
  });

  it("graduates only after a second confirming tap", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({ graduation: { available: true, stage: "Дебют", coins: 3000 }, dynasty_bonus: 1 }));
    vi.mocked(graduateProspect).mockResolvedValue(view({ prospect: null, graduate: GRAD, generations: 1, hall: { mine: [GRAD], top: [GRAD] } }));
    renderPage();
    fireEvent.click(await screen.findByRole("button", { name: "Устроить выпускной" }));
    expect(graduateProspect).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: /Точно\?/ }));
    await waitFor(() => expect(graduateProspect).toHaveBeenCalled());
    expect(await screen.findByText("Новое поколение · II")).toBeInTheDocument();
    expect(screen.getAllByText("Тимур Гол").length).toBeGreaterThan(0);
  });

  it("starts the next generation from the graduate's home", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({ prospect: null, graduate: GRAD, generations: 1, dynasty_bonus: 1, next_dynasty_peak: 1, hall: { mine: [GRAD], top: [GRAD] } }));
    renderPage();
    expect(await screen.findByText("🏛 Зал выпускников")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Взять нового воспитанника" }));
    expect(await screen.findByText(/II поколение династии: \+1 к рейтингу на пике/)).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Отмена" })).toBeInTheDocument();
  });

  it("the coach offers positions at «Юноши» and the choice is sent", async () => {
    const options = [
      { position: "CB", line: "DEF" as const, line_name: "Защита", drills: 6, talents: ["Стена"], deficit: true, xp_pct: 10, value_pct: 15 },
      { position: "RB", line: "DEF" as const, line_name: "Защита", drills: 6, talents: ["Стена"], deficit: true, xp_pct: 10, value_pct: 15 },
      { position: "CM", line: "MID" as const, line_name: "Полузащита", drills: 2, talents: [], deficit: false, xp_pct: 0, value_pct: 0 },
    ];
    vi.mocked(fetchProspect).mockResolvedValue(view({ prospect: kid({ stage: 2, stage_code: "youth" }), position_pick: { options } }));
    vi.mocked(chooseProspectPosition).mockResolvedValue(view({
      prospect: kid({ stage: 2, stage_code: "youth", universal: false, position: "CB", line: "DEF", deficit: { line: "DEF", xp_pct: 10, value_pct: 15 } }),
      position_pick: null,
    }));
    renderPage();
    expect(await screen.findByText("Где ему играть?")).toBeInTheDocument();
    expect(screen.getAllByText("дефицит: +10% опыта, +15% цены")).toHaveLength(2);
    fireEvent.click(screen.getByRole("button", { name: /CB/ }));
    await waitFor(() => expect(chooseProspectPosition).toHaveBeenCalledWith("CB"));
    expect(await screen.findByText(/Теперь он CB/)).toBeInTheDocument();
  });

  it("the growth tab explains how the potential and the peak grow", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({
      growth: {
        potential_max: false,
        streak: { every: 14, current: 5, ups: 0, max: 2 },
        trial: { matches: 3, wins_needed: 2, stages: [
          { stage: 1, name: "Детская школа", played: 1, wins: 1, status: "active", story: false },
          { stage: 2, name: "Юноши", played: 0, wins: 0, status: "upcoming", story: false },
        ] },
        peak: { dynasty: 1, dynasty_per: 1, academy: 2, academy_level: 25, per_levels: 10, next_level: 30 },
      },
      position_change: null,
    }));
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Рост" }));
    expect(await screen.findByText("Как растёт потенциал")).toBeInTheDocument();
    expect(screen.getByText("Сейчас 5 дн. подряд · ещё 9 дн.")).toBeInTheDocument();
    expect(screen.getByText("1 поб. из 1/3")).toBeInTheDocument();
    expect(screen.getByText("📈 Бонус к рейтингу на пике: +3")).toBeInTheDocument();
    expect(screen.getByText("Универсал")).toBeInTheDocument();
  });

  it("an incoming duel opens «Ответка» with the duel", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({ duels: [{
      id: 12, status: "open", incoming: true, friend: "Ваня", friend_prospect: "Кирилл", mine: null, theirs: { for: 2, against: 1, won: true },
      can_play: true, won: null, expires_at: new Date(Date.now() + 5 * 3_600_000).toISOString(),
    }] }));
    renderPage();
    expect(await screen.findByText("Ваня вызывает на дуэль")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Принять" }));
    expect(await screen.findByText("otvetka page?duel=12")).toBeInTheDocument();
  });

  it("challenges a friend's prospect from «Друзья»", async () => {
    const friend = { user_id: 77, owner: "Ваня", name: "Кирилл", rating: 41, age: 9, number: 10, appearance: LOOK };
    vi.mocked(fetchProspect).mockResolvedValue(view({ friends: [friend], duels: [], duel_rules: { hours: 48, per_day: 3, win_xp: 80 }, gift_stars: { training: 15, coach: 99 } }));
    vi.mocked(challengeProspectDuel).mockResolvedValue({ duel_id: 31, view: view() });
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Друзья" }));
    expect(screen.getByText(/Победителю \+80 опыта/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "🎁 Подарить" }));
    expect(screen.getByRole("button", { name: "Личный тренер · ⭐ 99" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "⚔️ Вызвать" }));
    await waitFor(() => expect(challengeProspectDuel).toHaveBeenCalledWith(77));
    expect(await screen.findByText("otvetka page?duel=31")).toBeInTheDocument();
  });

  it("growth tab shows the week tournament with prizes", async () => {
    vi.mocked(fetchProspect).mockResolvedValue(view({ week: {
      key: "2026-W46", days_left: 3, prizes: [3000, 2000, 1000], my_xp: 420, place: 2, size: 5,
      top: [{ place: 1, name: "Марк Орлов", owner: "Петя", xp: 600, me: false }, { place: 2, name: "Лёва Мяч", owner: "Я", xp: 420, me: true }],
    } }));
    renderPage();
    fireEvent.click(await screen.findByRole("tab", { name: "Рост" }));
    expect(screen.getByText("🏆 Турнир набора")).toBeInTheDocument();
    expect(screen.getByText("2-й")).toBeInTheDocument();
    expect(screen.getByText("600")).toBeInTheDocument();
  });
});
