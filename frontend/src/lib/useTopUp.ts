import { useQuery } from "@tanstack/react-query";

import { fetchCoinPackages } from "@/api/wallet";

/** Stars price of the cheapest coin package that covers `need` coins (null
 * when none does) — for «Докупить N · от X ⭐». Informative only: the
 * server prices the invoice. */
export function useTopUpStars() {
  const { data: packages } = useQuery({ queryKey: ["coin-packages"], queryFn: fetchCoinPackages });
  return (need: number): number | null => {
    const fit = (packages ?? [])
      .filter((p) => p.is_active && p.coins_amount >= need)
      .sort((a, b) => a.stars_price - b.stars_price)[0];
    return fit ? fit.stars_price : null;
  };
}
