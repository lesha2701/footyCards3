import CardSkillBadge from "@/components/cards/CardSkillBadge";
import PlayerCard from "@/components/cards/PlayerCard";
import { IconClock, IconCoin } from "@/components/icons";
import { formatTimeLeft, serverOffsetMs, type AuctionLot } from "@/api/auction";

/** Market grid tile: the card itself, with the price on top of it — plus the
 * countdown and bid state for auctions («Купить сразу» shows the price only). */
export default function LotTile({ lot, now, onOpen }: { lot: AuctionLot; now: number; onOpen: () => void }) {
  const card = lot.card;
  const fixed = lot.kind === "fixed";
  const price = fixed ? lot.buy_now_price ?? lot.start_price : lot.current_bid ?? lot.start_price;
  const left = new Date(lot.ends_at).getTime() - (now + serverOffsetMs(lot.server_now));
  const ringClass = lot.i_am_leading
    ? "ring-2 ring-accent-green"
    : !fixed && lot.my_max_bid && !lot.i_am_leading
      ? "ring-2 ring-red-400/70"
      : "";

  return (
    <div className={`relative rounded-2xl ${ringClass}`}>
      <PlayerCard
        player={card.player}
        stars={card.stars}
        pathStage={card.path_stage}
        prestige={card.prestige}
        talentOverride={card.talent_override}
        badge={<CardSkillBadge code={card.skill_code} level={card.skill_level} />}
        onClick={onOpen}
      />
      <div className="pointer-events-none absolute inset-x-1 bottom-[30%] flex flex-col items-center gap-0.5">
        {!fixed && (
          <span
            className={`flex items-center gap-0.5 rounded-full bg-black/70 px-1.5 py-0.5 font-mono text-micro font-semibold backdrop-blur ${
              left < 120_000 ? "text-red-300" : "text-ink-chalk"
            }`}
          >
            <IconClock size={9} />
            {formatTimeLeft(left)}
          </span>
        )}
        <span className="flex items-center gap-0.5 rounded-full bg-black/80 px-2 py-0.5 font-mono text-caption font-bold text-accent-lime shadow backdrop-blur">
          {price.toLocaleString("ru-RU")}
          <IconCoin size={10} />
        </span>
        {fixed ? (
          <span className="rounded-full bg-accent-green/80 px-1.5 text-micro font-bold text-bg-base">купить</span>
        ) : lot.i_am_leading ? (
          <span className="rounded-full bg-accent-green/80 px-1.5 text-micro font-bold text-bg-base">ты лидер</span>
        ) : lot.bid_count > 0 ? (
          <span className="rounded-full bg-black/60 px-1.5 text-micro text-ink-mist">ставок: {lot.bid_count}</span>
        ) : null}
      </div>
    </div>
  );
}
