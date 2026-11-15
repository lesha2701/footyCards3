import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";

import type { ManagerAssistantOffice, ManagerStaffView } from "@/api/manager";
import { AwayReport, DeskOverlay } from "@/components/manager/OfficeDesk";
import StaffTab from "@/components/manager/StaffTab";

const api = vi.hoisted(() => ({
  fetchManagerStaff: vi.fn(),
  fetchManagerAssistant: vi.fn(),
  fetchManagerSummary: vi.fn(),
  hireManagerStaff: vi.fn(),
  startManagerAssistantTrial: vi.fn(),
  markManagerAssistantSeen: vi.fn(),
  fireManagerStaff: vi.fn(),
  renameManagerVip: vi.fn(),
  setManagerAssistantRules: vi.fn(),
  buyManagerStaffItem: vi.fn(),
  wearManagerStaffItem: vi.fn(),
  buyManagerFleet: vi.fn(),
  orderManagerStaff: vi.fn(),
  doManagerAdvice: vi.fn(),
  fetchManagerDecisions: vi.fn(),
  fetchManagerDirector: vi.fn(),
  setManagerDirectorBudget: vi.fn(),
  signManagerNpc: vi.fn(),
  setManagerBudget: vi.fn(),
  claimManagerAchievement: vi.fn(),
}));
vi.mock("@/api/manager", () => api);
vi.mock("@/lib/myPlayerStars", () => ({ payMyPlayerWithStars: vi.fn() }));

const SKIN = { code: "skin_assistant_classic", kind: "skin" as const, role: "assistant" as const, name: "Деловой костюм", about: "", art: { hair_style: "bun" as const }, coins: 0, stars: 0, owned: true };
const STAFF: ManagerStaffView = {
  vip: [
    { code: "assistant", role: "assistant", title: "Помощник", emoji: "🗂", about: "Делает за тебя", name: "Алиса", stars: 149, days: 30, active: false, until: null, skin: SKIN, trial: true },
    { code: "analytics", role: "analyst", title: "Аналитик", emoji: "📊", about: "Думает за тебя", name: "Марк", stars: 129, days: 30, active: false, until: null, skin: null, trial: false },
  ],
  bundle_stars: 229,
  staff: [],
  slots: 3,
  candidates: [{ resident_id: 7, name: "Доктор Айболит", title: null, icon: "🩺", image: null, rarity: "epic", wage: 90_000 }],
  roles: [
    { code: "transport", name: "Начальник транспорта", dept: "Транспортный департамент", emoji: "🚌", effects: { common: "+1%", rare: "+1%", epic: "+2% к силе в гостях", legendary: "+2%" } },
    { code: "physio", name: "Главный врач", dept: "Медицинский центр", emoji: "🩺", effects: { common: "−10%", rare: "−20%", epic: "−30% к шансу травмы", legendary: "−40%" } },
  ],
  wages: 0,
  window: true,
  items: [SKIN, { code: "car_hatch", kind: "car", name: "Хэтчбек", about: "", art: {}, coins: 0, stars: 0, owned: true }],
  worn: { assistant: SKIN, analyst: null, car: null, room: null },
  orders: {
    transport: { emoji: "🛫", title: "Чартер на выезд", about: "Без усталости", cost: 60_000, fans: 0, form_pct: 2, form_rounds: 1, season: true, done: false },
  },
  fleet: { kinds: [
    { kind: "bus", title: "Автобус", level: 1, items: [
      { code: "minibus", name: "Микроавтобус", emoji: "🚐", price: 100_000, upkeep: 20_000, away_pct: 1, injury_pct: 0 },
      { code: "coach_bus", name: "Клубный автобус", emoji: "🚌", price: 240_000, upkeep: 40_000, away_pct: 2, injury_pct: 0 },
    ] },
  ] },
};
const OFFICE: ManagerAssistantOffice = {
  active: true, name: "Алиса", trial: false, press_rounds: [2, 5],
  rules: { limit: 500_000, transfer_limit: 500_000, renew_limit: 500_000, min_sale: 0, keep: [], mode: "act", sponsor: true, kit: true, fill: true, renew_min_rating: 60, renew_max_wage: 600, decline_below_pct: 80, events: "balanced", plan: "auto" },
  report: { entries: [{ at: new Date().toISOString(), icon: "🤝", text: "Подписала спонсора «Atlas»", eur: 300_000 }], unseen: 1, spent: 0, earned: 300_000, todo: 0 },
  squad: [{ key: "npc:5", name: "Иванов", rating: 77, kind: "npc" }],
};

function wrap(ui: React.ReactNode) {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(<QueryClientProvider client={client}>{ui}</QueryClientProvider>);
}

beforeEach(() => {
  api.fetchManagerStaff.mockResolvedValue(STAFF);
  api.fetchManagerAssistant.mockResolvedValue(OFFICE);
  api.hireManagerStaff.mockResolvedValue(STAFF);
  api.startManagerAssistantTrial.mockResolvedValue(STAFF);
  api.markManagerAssistantSeen.mockResolvedValue({ ...OFFICE.report, unseen: 0 });
});

describe("StaffTab", () => {
  it("shows both VIP, the bundle and the free week", async () => {
    wrap(<StaffTab onError={() => {}} />);
    expect(await screen.findByTestId("vip-assistant")).toHaveTextContent("Алиса");
    expect(screen.getByTestId("vip-analyst")).toHaveTextContent("Марк");
    expect(screen.getByTestId("staff-bundle")).toHaveTextContent("229 ⭐");
    fireEvent.click(screen.getByTestId("assistant-trial"));
    await waitFor(() => expect(api.startManagerAssistantTrial).toHaveBeenCalled());
  });

  it("hires a town resident into a free role", async () => {
    wrap(<StaffTab onError={() => {}} />);
    fireEvent.click(await screen.findByTestId("desk-team"));
    expect(await screen.findByTestId("seat-president")).toBeInTheDocument();
    fireEvent.click(screen.getByTestId("seat-physio"));
    expect(screen.getByTestId("seat-sheet")).toHaveTextContent("Медицинский центр");
    expect(screen.getByTestId("hire-sheet")).toHaveTextContent("эпический · −30% к шансу травмы");
    fireEvent.click(screen.getByText("Доктор Айболит"));
    await waitFor(() => expect(api.hireManagerStaff).toHaveBeenCalledWith(7, "physio"));
  });
});

describe("Кабинет: the assistant at the desk", () => {
  it("greets with the count of things done and lists them", async () => {
    const onTab = vi.fn();
    wrap(<><DeskOverlay onTab={onTab} /><AwayReport onTab={onTab} /></>);
    expect(await screen.findByText(/пока вас не было: 1 дело/)).toBeInTheDocument();
    expect(await screen.findByText("Подписала спонсора «Atlas»")).toBeInTheDocument();
    fireEvent.click(screen.getByText("Понятно"));
    await waitFor(() => expect(api.markManagerAssistantSeen).toHaveBeenCalled());
    fireEvent.click(screen.getByTestId("desk-assistant"));
    expect(onTab).toHaveBeenCalledWith("staff");
  });
});

describe("«Помощница»: advice in one tap", () => {
  it("does what she advised and edits the fine rules", async () => {
    const active = { ...STAFF, vip: STAFF.vip.map((v) => (v.role === "assistant" ? { ...v, active: true, trial: false } : v)) };
    api.fetchManagerStaff.mockResolvedValue(active);
    api.fetchManagerAssistant.mockResolvedValue({
      ...OFFICE,
      rules: { ...OFFICE.rules, mode: "advise" },
      report: { ...OFFICE.report, todo: 1, entries: [{ id: "ab12", at: new Date().toISOString(), icon: "📋", text: "Советую взять в аренду Петрова", eur: -50_000, action: { kind: "loan", ref: "loan:1" } }] },
    });
    api.doManagerAdvice.mockResolvedValue(OFFICE);
    api.setManagerAssistantRules.mockResolvedValue(active);
    wrap(<StaffTab onError={() => {}} />);
    expect(await screen.findByTestId("assistant-desk")).toHaveTextContent("Советую взять в аренду Петрова");
    fireEvent.click(screen.getByTestId("advice-do"));
    await waitFor(() => expect(api.doManagerAdvice).toHaveBeenCalledWith("ab12", expect.anything()));
    fireEvent.click(await screen.findByText("Иванов 77"));
    await waitFor(() => expect(api.setManagerAssistantRules).toHaveBeenCalledWith({ keep: ["npc:5"] }));
  });
});

describe("«Штат»: the round table", () => {
  it("opens a hired head's sheet: the order and the fleet", async () => {
    const head = { id: 3, role: "transport" as const, role_name: "Начальник транспорта", dept: "Транспортный департамент", emoji: "🚌",
      resident_id: 9, name: "Валера", icon: "🚌", image: null, rarity: "epic" as const, effect: 2, effect_text: "+2% к силе в гостях", wage: 50_000 };
    api.fetchManagerStaff.mockResolvedValue({ ...STAFF, staff: [head] });
    api.orderManagerStaff.mockResolvedValue({ ...STAFF, staff: [head] });
    api.buyManagerFleet.mockResolvedValue({ ...STAFF, staff: [head] });
    wrap(<StaffTab onError={() => {}} />);
    fireEvent.click(await screen.findByTestId("desk-team"));
    fireEvent.click(await screen.findByTestId("seat-transport"));
    const sheet = screen.getByTestId("seat-sheet");
    expect(sheet).toHaveTextContent("Валера");
    expect(sheet).toHaveTextContent("+2% к силе в гостях");
    expect(screen.getByTestId("fleet")).toHaveTextContent("Автобус: Микроавтобус");
    fireEvent.click(screen.getByTestId("order-do"));
    await waitFor(() => expect(api.orderManagerStaff).toHaveBeenCalledWith("transport"));
  });
});
