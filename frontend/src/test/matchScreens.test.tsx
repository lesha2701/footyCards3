import { fireEvent, render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { CareerSeason, CareerSquadCard } from "@/api/career";
import { AwaySummaryCard, PostMatchCard, PreMatchCard } from "@/components/career/MatchScreens";
import { FansCard, HotSeatBanner, LegendsCard, NewsFeed } from "@/components/career/CareerClub";
import { FoldCard } from "@/components/career/FoldCard";
import { PrepTabs } from "@/components/career/PrepTabs";

const entry = (card_id: number, name: string, fatigue: number, out = 0): CareerSquadCard => ({
  card: { player: { display_name: `Имя ${name}`, position: "CM", rating: 80 } } as never,
  card_id, fatigue, injured_rounds: out, suspended_rounds: 0, yellows: 0, form: 0, owned: true,
});

const report = (over = {}) => ({ yellow: [], red: [], suspended: [], injured: [], form_up: [], form_down: [], ...over });

const season = {
  id: 7, rounds_played: 2, my_team_index: 0,
  table: [{ team_index: 2 }, { team_index: 1 }, { team_index: 0 }],
  teams: [{ index: 0, name: "Мы" }, { index: 1, name: "Сокол" }, { index: 2, name: "Сатурн" }],
  rounds: [
    { index: 0, at: null, matches: [{ home: 1, away: 0, hs: 1, as: 1, has_events: true }], report: report({ coins: 10, place: 5 }) },
    {
      index: 1, at: null, matches: [{ home: 0, away: 2, hs: 3, as: 1, has_events: true }],
      report: report({ coins: 55, place: 3, injured: ["Петров"], yellow: ["Сидоров"] }),
    },
    { index: 2, at: null, matches: [{ home: 1, away: 0, hs: null, as: null, has_events: false }], report: null },
  ],
  squad: [entry(1, "Иванов", 85), entry(2, "Петров", 10, 2), entry(3, "Кузнецов", 20), entry(4, "Смирнов", 75)],
  lineup: { MID1: 1, MID2: 2, MID3: 3, MID4: 4 },
  squad_warnings: [],
  scouting: {
    round_index: 2, opponent_index: 1, opponent_name: "Сокол", is_bot: true, strength: 74, form: ["W", "L"],
    win_pct: 41.6, head_to_head: { w: 1, d: 0, l: 0, meetings: 1 },
  },
} as unknown as CareerSeason;

const wrap = (node: React.ReactNode) => render(<MemoryRouter>{node}</MemoryRouter>);

describe("before the match", () => {
  it("the opponent, his form, my tired and missing starters, and a jump to the squad", () => {
    const onSquad = vi.fn();
    wrap(<PreMatchCard league="Лига" season={season} when="завтра в 19:00" onSquad={onSquad} />);
    const card = screen.getByRole("region", { name: "Следующий матч" });
    expect(card).toHaveTextContent("В гостях: Сокол");
    expect(card).toHaveTextContent("завтра в 19:00");
    expect(card).toHaveTextContent("42%");
    expect(card).toHaveTextContent("Не сыграют 1 игрок из стартового состава: Петров");
    expect(card).toHaveTextContent("У тебя 2 уставших в старте");
    // Most tired first.
    expect(screen.getAllByRole("listitem").map((li) => li.textContent?.split(/\d/)[0].replace("Энергия", "").trim()))
      .toEqual(["Иванов", "Смирнов"]);
    fireEvent.click(screen.getByRole("button", { name: "Поправить состав" }));
    expect(onSquad).toHaveBeenCalled();
  });

  it("all fresh: the squad is ready", () => {
    wrap(<PreMatchCard league="Лига" season={{ ...season, squad: [entry(1, "Иванов", 0)], lineup: { MID1: 1 } }} when="" onSquad={vi.fn()} />);
    expect(screen.getByText("Состав готов: все свежие и здоровы")).toBeInTheDocument();
  });
});

describe("after the match", () => {
  beforeEach(() => localStorage.clear());

  it("the result, the coins, the place and its move, the news; closed once seen", () => {
    const { unmount } = wrap(<PostMatchCard season={season} />);
    const card = screen.getByRole("region", { name: "Итог тура" });
    expect(card).toHaveTextContent("Итог тура 2");
    expect(card).toHaveTextContent("Победа");
    expect(card).toHaveTextContent("3:1");
    expect(card).toHaveTextContent("+55");
    expect(card).toHaveTextContent("3▲2");
    expect(card).toHaveTextContent("Петров — травма");
    expect(card).toHaveTextContent("Сидоров — жёлтая");
    expect(screen.getByRole("button", { name: "Смотреть матч" })).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Понятно" }));
    expect(screen.queryByRole("region", { name: "Итог тура" })).toBeNull();
    unmount();
    wrap(<PostMatchCard season={season} />);
    expect(screen.queryByRole("region", { name: "Итог тура" })).toBeNull();
  });

  it("rounds from before the coins and the place were recorded: the place from the table, no reward box", () => {
    const old = { ...season, rounds: season.rounds.map((r) => ({ ...r, report: r.report && report() })) };
    wrap(<PostMatchCard season={old as CareerSeason} />);
    const card = screen.getByRole("region", { name: "Итог тура" });
    expect(card).toHaveTextContent("Место в таблице3");
    expect(card).not.toHaveTextContent("Награда");
  });

  it("nothing before the first round", () => {
    wrap(<PostMatchCard season={{ ...season, rounds_played: 0 }} />);
    expect(screen.queryByRole("region", { name: "Итог тура" })).toBeNull();
  });
});

describe("while the coach was away", () => {
  it("sums up the rounds, the coins and the place", () => {
    wrap(<AwaySummaryCard season={season} from={0} onClose={vi.fn()} />);
    const card = screen.getByRole("region", { name: "Пока тебя не было" });
    expect(card).toHaveTextContent("2 тура: В1 Н1 П0");
    expect(card).toHaveTextContent("+65");
    expect(card).toHaveTextContent("Петров — травма");
  });
});

describe("the club", () => {
  const club = {
    ...season,
    news: [{ round: 4, icon: "👑", text: "Мы возглавили таблицу!", tone: "good" }],
    fans: { mood: 70, label: "Болельщики довольны", attendance: 5000, capacity: 6000, income_pct: 108 },
    legends: { players: [{ name: "Смит", apps: 20, goals: 9, assists: 3, seasons: 2 }], biggest_win: { score: "5:0", opponent: "Сокол" }, best_streak: 4 },
    hot_seat: { level: 2, text: "Руководство недовольно." },
  } as unknown as CareerSeason;

  it("shows the feed, the stands, the legends and the hot seat", () => {
    render(<><NewsFeed season={club} /><FansCard season={club} /><LegendsCard season={club} /><HotSeatBanner season={club} /></>);
    expect(screen.getByText("Мы возглавили таблицу!")).toHaveClass("text-accent-lime");
    expect(screen.getByRole("meter", { name: "Настроение трибун" })).toHaveAttribute("aria-valuenow", "70");
    expect(screen.getByRole("region", { name: "Легенды клуба" })).toHaveTextContent("5:0");
    expect(screen.getByRole("region", { name: "Горячее кресло" })).toHaveTextContent("уровень 2");
  });

  it("hides what has no data yet", () => {
    const { container } = render(<><FansCard season={season} /><LegendsCard season={season} /><HotSeatBanner season={season} /></>);
    expect(container).toBeEmptyDOMElement();
  });
});

describe("folded settings", () => {
  it("open on tap and keep their card mounted", () => {
    render(<FoldCard title="Опека" status="Не назначена"><p>внутри</p></FoldCard>);
    expect(screen.queryByText("внутри")).toBeNull();
    const toggle = screen.getByRole("button", { name: /Опека/ });
    fireEvent.click(toggle);
    expect(screen.getByText("внутри")).toBeVisible();
    fireEvent.click(toggle);
    expect(screen.getByText("внутри")).not.toBeVisible();
  });
});

describe("preparation tiles", () => {
  it("say what stands behind each section and switch it", () => {
    const onChange = vi.fn();
    render(<PrepTabs season={{ ...season, slots: [{ code: "MID1" }], training: null } as unknown as CareerSeason} value="tactic" onChange={onChange} />);
    expect(screen.getByRole("tab", { name: /Тактика/ })).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tab", { name: /Тренировка/ })).toHaveTextContent("Не выбрана");
    fireEvent.click(screen.getByRole("tab", { name: /Состав/ }));
    expect(onChange).toHaveBeenCalledWith("squad");
  });
});
