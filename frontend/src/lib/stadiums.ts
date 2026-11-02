/** «+10% к силе · −5 к рейтингу соперника» — what a stadium does. */
export function stadiumEffectText(s: { boost_pct: number; opp_malus?: number | null }): string {
  return [
    s.boost_pct > 0 ? `+${Math.round(s.boost_pct * 100)}% к силе` : null,
    s.opp_malus ? `−${s.opp_malus} к рейтингу соперника` : null,
  ].filter(Boolean).join(" · ") || "без бонусов";
}
