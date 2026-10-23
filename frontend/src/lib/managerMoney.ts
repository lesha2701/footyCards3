/** Club euros of «Менеджер»: €3,5 млн · €800 тыс · €950. */
export function eur(n: number): string {
  const abs = Math.abs(n);
  const sign = n < 0 ? "−" : "";
  if (abs >= 1_000_000) {
    const m = abs / 1_000_000;
    return `${sign}€${(m >= 100 ? Math.round(m).toString() : m.toFixed(m >= 10 ? 1 : 2).replace(/\.?0+$/, "")).replace(".", ",")} млн`;
  }
  if (abs >= 1_000) return `${sign}€${Math.round(abs / 1_000)} тыс`;
  return `${sign}€${abs}`;
}

/** «▲ +12%» / «▼ −4%» for a value trend; null (no history) or 0 → "". */
export function trend(pct: number | null | undefined): string {
  if (!pct) return "";
  return pct >= 0 ? `▲ +${pct}%` : `▼ −${Math.abs(pct)}%`;
}
