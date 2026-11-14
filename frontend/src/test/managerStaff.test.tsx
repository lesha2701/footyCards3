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
  roles: [{ code: "physio", name: "Физиотерапевт", emoji: "🩺", effects: { common: "−10%", rare: "−20%", epic: "−30% к шансу травмы", legendary: "−40%" } }],
  wages: 0,
  window: true,
  items: [SKIN, { code: "car_hatch", kind: "car", name: "Хэтчбек", about: "", art: {}, coins: 0, stars: 0, owned: true }],
  worn: { assistant: SKIN, analyst: null, car: null, room: null },
};
const OFFICE: ManagerAssistantOffice = {
  active: true, name: "Алиса", trial: false, press_rounds: [2, 5],
  rules: { limit: 500_000, sponsor: true, kit: true, fill: true, renew_min_rating: 60, renew_max_wage: 600, decline_below_pct: 80, events: "balanced", plan: "auto" },
  report: { entries: [{ at: new Date().toISOString(), icon: "🤝", text: "Подписала спонсора «Atlas»", eur: 300_000 }], unseen: 1, spent: 0, earned: 300_000 },
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
    fireEvent.click(await screen.findByText(/Физиотерапевт/));
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
