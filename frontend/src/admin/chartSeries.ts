export type ChartPoint = { date: string; count: number };

/** The dashboard API only returns days that had at least one event, so a
 * quiet day would silently vanish from the chart and squeeze the remaining
 * bars together. Rebuild the full `days`-long window ending today (UTC
 * dates, matching the backend's `func.date(created_at)` grouping), filling
 * gaps with 0. */
export function fillDailySeries(points: ChartPoint[], days = 14, now: Date = new Date()): ChartPoint[] {
  const counts = new Map(points.map((p) => [p.date, p.count]));
  const todayUtc = Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), now.getUTCDate());
  return Array.from({ length: days }, (_, i) => {
    const date = new Date(todayUtc - (days - 1 - i) * 86_400_000).toISOString().slice(0, 10);
    return { date, count: counts.get(date) ?? 0 };
  });
}
