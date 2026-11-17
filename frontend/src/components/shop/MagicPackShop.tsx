import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchMagicHub } from "@/api/magic";
import { MagicPackOffer } from "@/components/magic/MagicPack";

/** «Магазин» → «Паки»: the creature pack of «Мяч и Магия», bought right here. Hidden while the mode is off. */
export default function MagicPackShop() {
  const navigate = useNavigate();
  const { data: hub } = useQuery({ queryKey: ["magic-hub"], queryFn: fetchMagicHub, retry: false });
  if (!hub?.enabled || !hub.creature_pack) return null;
  return (
    <section className="flex flex-col gap-1.5">
      <div className="flex items-center justify-between">
        <h2 className="font-display text-base font-bold text-ink-chalk">Мяч и Магия</h2>
        <button onClick={() => navigate("/play/magic")} className="text-caption text-ink-mist active:opacity-70">В режим →</button>
      </div>
      <MagicPackOffer hub={hub} note={`${hub.creature_pack.size} карт существ для армии героя в режиме «Мяч и Магия».`} />
    </section>
  );
}
