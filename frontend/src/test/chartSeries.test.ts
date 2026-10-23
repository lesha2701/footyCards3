import { fillDailySeries } from "@/admin/chartSeries";

describe("fillDailySeries", () => {
  const now = new Date("2026-10-14T09:30:00Z");

  it("returns exactly `days` points ending today, oldest first", () => {
    const series = fillDailySeries([], 14, now);
    expect(series).toHaveLength(14);
    expect(series[0].date).toBe("2026-10-01");
    expect(series[13].date).toBe("2026-10-14");
    expect(series.every((p) => p.count === 0)).toBe(true);
  });

  it("keeps API counts and fills missing days with zero", () => {
    const series = fillDailySeries(
      [
        { date: "2026-10-03", count: 2 },
        { date: "2026-10-14", count: 6 },
      ],
      14,
      now,
    );
    expect(series.find((p) => p.date === "2026-10-03")?.count).toBe(2);
    expect(series.find((p) => p.date === "2026-10-14")?.count).toBe(6);
    expect(series.find((p) => p.date === "2026-10-04")?.count).toBe(0);
  });

  it("drops days outside the window and crosses month boundaries", () => {
    const series = fillDailySeries([{ date: "2026-09-20", count: 5 }], 14, new Date("2026-10-05T00:00:00Z"));
    expect(series[0].date).toBe("2026-09-22");
    expect(series.reduce((s, p) => s + p.count, 0)).toBe(0);
  });
});
