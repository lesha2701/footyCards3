import { useQuery } from "@tanstack/react-query";

import { fetchCardPassport } from "@/api/collection";
import cardBack from "@/assets/cards/back.webp";
import { specialSerial } from "@/lib/serials";

const SOURCE_LABELS: Record<string, string> = {
  pack: "из пака",
  free_pack: "из бесплатного пака",
  stars_purchase: "из пака за звёзды",
  daily_reward: "в ежедневной награде",
  trade: "по обмену",
  admin_grant: "в подарок от клуба",
  achievement: "за достижение",
  game_reward: "за игру",
  task: "за задание",
  newbie: "в паке дебютанта",
  card_upgrade: "апгрейдом",
  collection_reward: "за коллекцию",
  chat_pack: "в чате",
  gift: "в подарок",
  wheel: "в колесе фортуны",
  league_reward: "за лигу",
  club_reward: "в клубе",
};

function day(iso: string): string {
  return new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric", timeZone: "Europe/Moscow" });
}

/** The back of the card: the emerald back art with the club's V and this
 * copy's number in the ring; `width` in px sizes the lettering with it. */
export function CardBack({ serial, total, width, className = "" }: { serial: number; total?: number | null; width: number; className?: string }) {
  return (
    <div
      className={`relative aspect-[3/4] shrink-0 overflow-hidden rounded-xl shadow-[0_8px_20px_rgba(0,0,0,0.5)] ${className}`}
      style={{ width, backgroundImage: `url(${cardBack})`, backgroundSize: "100% 100%" }}
      data-testid="card-back"
    >
      <div className="absolute left-1/2 top-[36%] flex aspect-square w-[44%] -translate-x-1/2 -translate-y-1/2 flex-col items-center justify-center">
        <svg viewBox="0 0 100 100" aria-hidden="true" style={{ width: width * 0.15 }}>
          <defs>
            <linearGradient id="back-v" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0" stopColor="#22d3ee" />
              <stop offset="1" stopColor="#d9f25a" />
            </linearGradient>
          </defs>
          <line x1="30" y1="28" x2="54" y2="74" stroke="url(#back-v)" strokeWidth="24" strokeLinecap="round" />
          <circle cx="74" cy="30" r="13" fill="url(#back-v)" />
        </svg>
        <span className="mt-0.5 whitespace-nowrap font-mono font-black leading-none text-amber-200" style={{ fontSize: width * 0.1 }}>
          №{serial}
        </span>
        {total != null && (
          <span className="whitespace-nowrap font-mono leading-tight text-amber-100/60" style={{ fontSize: width * 0.065 }}>
            из {total}
          </span>
        )}
      </div>
      <span
        className="absolute inset-x-0 bottom-[20%] whitespace-nowrap text-center font-display font-bold text-amber-200/80"
        style={{ fontSize: width * 0.075, letterSpacing: "0.2em" }}
      >
        VICTOR FC
      </span>
    </div>
  );
}

/** «Паспорт карты»: its number, where it came from, who held it before and
 * what it did in Card Arena — shown on the card's back. */
export default function CardPassport({ cardId }: { cardId: number }) {
  const { data } = useQuery({ queryKey: ["card-passport", cardId], queryFn: () => fetchCardPassport(cardId) });
  if (!data) return <div className="h-32 animate-pulse rounded-2xl bg-white/5" />;

  const total = data.edition_size ?? data.printed;
  const special = specialSerial(data.serial_number, data.edition_size);
  const arena = data.arena_goals + data.arena_assists + data.arena_mvps;
  const previous = data.owners.slice(0, -1);

  return (
    <section className="rounded-2xl border border-amber-200/15 bg-gradient-to-b from-emerald-950/50 to-transparent p-3" data-testid="card-passport">
      <p className="text-micro font-bold uppercase tracking-[0.2em] text-amber-200/80">Паспорт карты</p>
      <div className="mt-2 flex gap-3">
        <CardBack serial={data.serial_number} total={total} width={104} />
        <div className="min-w-0 flex-1 space-y-1.5 text-xs text-ink-mist">
          <p>
            Экземпляр <b className="font-mono text-ink-chalk">№{data.serial_number}</b>{" "}
            {data.edition_size != null ? <>из тиража <b className="text-ink-chalk">{data.edition_size}</b></> : <>из <b className="text-ink-chalk">{data.printed}</b> выпущенных</>}
          </p>
          {special && (
            <p className="inline-block rounded-full bg-amber-300/15 px-2 py-0.5 text-caption font-bold text-amber-200">✦ {special}</p>
          )}
          <p>
            У тебя с <b className="text-ink-chalk">{day(data.acquired_at)}</b>
            {SOURCE_LABELS[data.source] ? `, ${SOURCE_LABELS[data.source]}` : ""}
          </p>
          {previous.length > 0 ? (
            <p>
              Владельцы до тебя: <b className="text-ink-chalk">{previous.map((o) => o.name).join(" → ")}</b>
            </p>
          ) : (
            <p>Ты — первый владелец этой карты</p>
          )}
          {arena > 0 && (
            <p>
              В Арене: <b className="text-ink-chalk">{data.arena_goals}</b> гол. · <b className="text-ink-chalk">{data.arena_assists}</b> пас. ·{" "}
              <b className="text-ink-chalk">{data.arena_mvps}</b> MVP
            </p>
          )}
          {data.number_one_owner && data.serial_number !== 1 && (
            <p>
              №1 этого игрока {data.number_one_is_you ? <b className="text-amber-200">у тебя</b> : <>у <b className="text-ink-chalk">{data.number_one_owner}</b></>}
            </p>
          )}
        </div>
      </div>
    </section>
  );
}
