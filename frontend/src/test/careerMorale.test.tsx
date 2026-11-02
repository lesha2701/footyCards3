import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import type { ReactNode } from "react";
import { describe, expect, it, vi } from "vitest";

import type { CareerMorale, CareerSeason, CoachSpecs } from "@/api/career";
import { CoachSpecCard, HalftimeTalk, MatchMorale, MoraleCard, TraitBadge } from "@/components/career/Morale";

const { setCareerSpeech, chooseCoachSpec } = vi.hoisted(() => ({
  setCareerSpeech: vi.fn(async () => ({})), chooseCoachSpec: vi.fn(async () => ({})),
}));
vi.mock("@/api/career", () => ({ setCareerSpeech, chooseCoachSpec }));

const wrap = (node: ReactNode) => render(<QueryClientProvider client={new QueryClient()}>{node}</QueryClientProvider>);
const handlers = { onView: vi.fn(), onError: vi.fn() };

const morale: CareerMorale = {
  value: 34, level: -1, label: "Не в духе", rating: -1,
  log: [{ round: 2, before: 48, after: 34, reasons: ["поражение -12", "проиграли дуэли -2"] }],
  speech: null,
  speeches: [
    { code: "inspire", label: "Вдохновить", hint: "+1 к рейтингу, если команда не на подъёме." },
    { code: "calm", label: "Снять давление", hint: "Плохое настроение не мешает в этом матче." },
    { code: "demand", label: "Потребовать", hint: "Фаворитом: +1." },
  ],
  talks: [
    { code: "praise", label: "Похвалить", hint: "Ведём: +1." },
    { code: "rouse", label: "Встряхнуть", hint: "Проигрываем: +1." },
    { code: "calm", label: "Успокоить", hint: "Ничья: +1." },
  ],
  team_building: 6,
};

describe("Мораль команды", () => {
  it("shows the mood, its effect and the last change, and picks the speech for the round", async () => {
    const season = { rounds_played: 3, morale } as unknown as CareerSeason;
    wrap(<MoraleCard season={season} {...handlers} />);
    expect(screen.getByText("Мораль команды")).toBeInTheDocument();
    expect(screen.getByText(/Не в духе · -1 к рейтингу игроков/)).toBeInTheDocument();
    expect(screen.getByText(/Тур 3: 48 → 34 · поражение -12, проиграли дуэли -2/)).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Снять давление/ }));
    await waitFor(() => expect(setCareerSpeech).toHaveBeenCalledWith("calm", 3));
    await waitFor(() => expect(handlers.onView).toHaveBeenCalled());
  });

  it("hides without morale (an old season)", () => {
    const { container } = wrap(<MoraleCard season={{ rounds_played: 0 } as unknown as CareerSeason} {...handlers} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("half-time talk: picks and unpicks", () => {
    const onChange = vi.fn();
    const { rerender } = render(<HalftimeTalk talks={morale.talks} value={null} onChange={onChange} />);
    fireEvent.click(screen.getByRole("radio", { name: /Встряхнуть/ }));
    expect(onChange).toHaveBeenCalledWith("rouse");
    rerender(<HalftimeTalk talks={morale.talks} value="rouse" onChange={onChange} />);
    expect(screen.getByText("Проигрываем: +1.")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("radio", { name: /Встряхнуть/ }));
    expect(onChange).toHaveBeenLastCalledWith(null);
  });

  it("after the match: before → after with the reasons", () => {
    render(<MatchMorale morale={{ before: 60, after: 70, match: ["речь «Вдохновить»: +1"], reasons: ["речь «Вдохновить»: +1", "победа +8"] }} />);
    expect(screen.getByText("60 → 70")).toHaveClass("text-accent-lime");
    expect(screen.getByText(/В матче: речь «Вдохновить»/)).toBeInTheDocument();
    expect(screen.getByText("После: победа +8")).toBeInTheDocument();
  });

  const spec = (code: string, label: string, level: number, xp: number, next: number | null) => ({
    code, label, icon: "•", about: `${label}: о чём`, xp, level, level_xp: 0, next_xp: next,
    levels: Array.from({ length: 10 }, (_, i) => `${label} ${i + 1}`),
  });
  const coach = (over: Partial<CoachSpecs> = {}): CoachSpecs => ({
    spec: null, max_level: 10, switch_at: null, switch_days: 30, xp_win: 3, xp_draw: 2, xp_loss: 1, xp_season: [15, 10, 5],
    specs: [spec("motivator", "Мотиватор", 0, 0, 15), spec("analyst", "Аналитик", 0, 0, 15)],
    ...over,
  });

  it("coach specialization: the first choice goes straight away", async () => {
    wrap(<CoachSpecCard coach={coach()} {...handlers} />);
    expect(screen.getByText(/Выбери одну — работает только она/)).toBeInTheDocument();
    expect(screen.getAllByText("не изучена")).toHaveLength(2);
    fireEvent.click(screen.getByRole("tab", { name: /Аналитик/ }));
    expect(screen.getByText("Аналитик 10")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Выбрать «Аналитик»" }));
    await waitFor(() => expect(chooseCoachSpec).toHaveBeenCalledWith("analyst"));
  });

  it("coach specialization: progress of the chosen one, switching asks and can be locked", async () => {
    chooseCoachSpec.mockClear();
    const c = coach({ spec: "motivator", specs: [spec("motivator", "Мотиватор", 3, 40, 60), spec("analyst", "Аналитик", 2, 20, 35)] });
    c.specs[0].level_xp = 35;
    const { unmount } = wrap(<CoachSpecCard coach={c} {...handlers} />);
    expect(screen.getByText(/Мотиватор · уровень 3 из 10/)).toBeInTheDocument();
    expect(screen.getByText("Опыт 40 · до уровня 4 — ещё 20")).toBeInTheDocument();
    expect(screen.getByText("ур. 2 · отложена")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("tab", { name: /Аналитик/ }));
    fireEvent.click(screen.getByRole("button", { name: "Сменить на «Аналитик»" }));
    expect(chooseCoachSpec).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Сменить" }));
    await waitFor(() => expect(chooseCoachSpec).toHaveBeenCalledWith("analyst"));
    unmount();
    wrap(<CoachSpecCard coach={{ ...c, switch_at: "2026-12-01T10:00:00+00:00" }} {...handlers} />);
    fireEvent.click(screen.getByRole("tab", { name: /Аналитик/ }));
    expect(screen.getByRole("button", { name: /Сменить можно с 1 декабря/ })).toBeDisabled();
  });

  it("trait badge", () => {
    render(<TraitBadge trait="stoic" />);
    expect(screen.getByLabelText("Характер: Стоик")).toHaveTextContent("🗿");
  });
});
