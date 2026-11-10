import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Link, useNavigate, useParams } from "react-router-dom";

import {
  buyTownDecor, buyTownHotel, buyTownHouse, claimTownIncome, createTownRenameInvoice, fetchTown, fetchTownInvoiceStatus,
  fetchTownResidents, settleTownResident, unlockTown, type TownDistrictState, type TownState,
} from "@/api/town";
import GameHero from "@/components/common/GameHero";
import { IconClose, IconCoin } from "@/components/icons";
import TownScene from "@/components/town/TownScene";
import hotelArt from "@/assets/town/hotel.webp";
import housesArt from "@/assets/town/houses.webp";
import residentsArt from "@/assets/town/residents.webp";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { useMarkSeen } from "@/lib/seenSections";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import {
  DECOR_ZONES, DISTRICTS, FIREWORKS_BOX, MAP_ZONES, SCENE_H, SCENE_W, TOWN_MAP, districtOf, type DecorZone, type District,
  type TownBuilding,
} from "@/lib/town";
import { useAuthStore } from "@/store/authStore";
import type { StarsInvoiceCreate } from "@/types";

const fmt = (n: number) => n.toLocaleString("ru-RU");
const pct = (v: number, of: number) => `${(v / of) * 100}%`;
const DECOR_ART = import.meta.glob<string>("@/assets/town/decor/*.webp", { eager: true, import: "default" });
const decorArt = (code: string): string | undefined => DECOR_ART[`/src/assets/town/decor/${code}.webp`];

/** Opens a Telegram Stars invoice and waits until the bot delivered it.
 * null — the player closed the invoice. */
async function payWithStars(create: () => Promise<StarsInvoiceCreate>): Promise<TownState | null> {
  const invoice = await create();
  const status = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
  if (status === "cancelled") return null;
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let i = 0; i < 20; i++) {
    if ((await fetchTownInvoiceStatus(invoice.payload_token)).status === "completed") return fetchTown();
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

/** «Город»: the overview map (/town) and one district (/town/:district).
 * The town opens for coins (unlock_coins, free when 0) and can be renamed
 * for Stars. Houses and the hotel are bought for coins (backend
 * town_service — prices, rent and the cap come from there) and pay rent
 * every day; the hotel pays for the cards the player holds. A bought house
 * shows in full colour, the rest are dimmed. */
export default function TownPage() {
  useMarkSeen("town");
  const { district: code } = useParams();
  const district = districtOf(code);
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const { data: state } = useQuery({ queryKey: ["town"], queryFn: fetchTown, refetchInterval: 60_000 });

  const apply = (next: TownState) => {
    hapticNotify("success");
    setError(null);
    if (next.new_balance != null) updateBalance(next.new_balance);
    queryClient.setQueryData(["town"], next);
  };
  const fail = (err: unknown) => {
    hapticNotify("error");
    setNotice(null);
    setError(formatGameError(err, "Не получилось"));
  };
  const claim = useMutation({
    mutationFn: () => claimTownIncome(crypto.randomUUID()),
    onSuccess: (data) => { apply(data); setNotice(`Жильцы заплатили ренту: +${fmt(data.claimed ?? 0)} монет 🏘️`); },
    onError: fail,
  });
  const buy = useMutation({
    mutationFn: ({ district: d, code: c }: { district: string; code: string }) => buyTownHouse(d, c, crypto.randomUUID()),
    onSuccess: (data, house) => {
      apply(data);
      const name = districtOf(house.district)?.buildings.find((b) => b.code === house.code)?.name;
      setNotice(`${name ?? "Дом"} теперь твой — рента уже капает 🔑`);
    },
    onError: fail,
  });
  const settle = useMutation({
    mutationFn: ({ id, district: d }: { id: number; district: string | null }) => settleTownResident(id, d),
    onSuccess: (data, v) => {
      apply(data);
      void queryClient.invalidateQueries({ queryKey: ["town-residents"] });
      setNotice(v.district ? "Житель переехал — району стало веселее 🎉" : "Житель выписан из района");
    },
    onError: fail,
  });
  const hotel = useMutation({
    mutationFn: () => buyTownHotel(crypto.randomUUID()),
    onSuccess: (data) => { apply(data); setNotice("Отель открыт — твои карты заселились 🏨"); },
    onError: fail,
  });
  const decor = useMutation({
    mutationFn: (code: string) => buyTownDecor(code, crypto.randomUUID()),
    onSuccess: (data, code) => {
      apply(data);
      const place = data.decor.find((d) => d.code === code);
      setNotice(`${place?.name ?? "Место"} открыто — +${place?.rent_pct ?? 0}% к ренте домов ✨`);
    },
    onError: fail,
  });
  const unlock = useMutation({
    mutationFn: () => unlockTown(crypto.randomUUID()),
    onSuccess: (data) => { apply(data); setNotice("Город твой! Покупай первые дома 🏙️"); },
    onError: fail,
  });
  const rename = useMutation({
    mutationFn: (name: string) => payWithStars(() => createTownRenameInvoice(name)),
    onSuccess: (data) => { if (data) { apply(data); setNotice(`Теперь это «${data.name}» ✨`); } },
    onError: fail,
  });

  const locked = !!state && state.enabled && !state.unlocked;
  const messages = (
    <>
      {state && !state.enabled && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-xs text-legend">Город временно закрыт.</p>}
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{error}</p>}
      {notice && <p className="rounded-xl bg-accent-lime/10 px-3 py-2 text-xs text-accent-lime">{notice}</p>}
      {locked && <UnlockCard coins={state.unlock_coins} busy={unlock.isPending} onUnlock={() => unlock.mutate()} />}
    </>
  );

  return district ? (
    <DistrictView
      key={district.code}
      district={district}
      state={state}
      messages={<>{messages}{!locked && <RentBar state={state} busy={claim.isPending} onClaim={() => claim.mutate()} />}</>}
      settling={settle.isPending}
      onSettle={(id, d) => settle.mutateAsync({ id, district: d })}
      buying={buy.isPending}
      onBuy={(c) => buy.mutateAsync({ district: district.code, code: c })}
    />
  ) : (
    <TownMap
      state={state}
      messages={messages}
      claimBusy={claim.isPending}
      onClaim={() => claim.mutate()}
      hotelBusy={hotel.isPending}
      onHotel={() => hotel.mutate()}
      renameBusy={rename.isPending}
      onRename={(name) => rename.mutateAsync(name)}
      decorBusy={decor.isPending}
      onDecor={(code) => decor.mutateAsync(code)}
    />
  );
}

function UnlockCard({ coins, busy, onUnlock }: { coins: number; busy: boolean; onUnlock: () => void }) {
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const short = Math.max(0, coins - balance);
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-legend/40 bg-legend/10 p-3" aria-label="Открыть город">
      <p className="font-display text-base font-bold text-ink-chalk">🏙️ Свой город у моря</p>
      <p className="text-xs text-ink-mist">
        Покупай дома в пяти районах, открой отель для своих карт и забирай ренту каждый день. Город открывается один раз — навсегда.
      </p>
      <button
        type="button"
        disabled={busy || short > 0}
        onClick={onUnlock}
        className="min-h-[44px] rounded-xl bg-floodlight px-4 text-sm font-bold text-bg-base disabled:opacity-40"
      >
        {short > 0 ? `Открыть город: не хватает ${fmt(short)} монет` : `Открыть город за ${fmt(coins)} монет`}
      </button>
    </section>
  );
}

function RentBar({ state, busy, onClaim }: { state?: TownState; busy: boolean; onClaim: () => void }) {
  const income = state?.income;
  return (
    <section className="flex items-center gap-3 rounded-2xl border border-legend/25 bg-legend/5 p-3" aria-label="Рента города">
      <img src={housesArt} alt="" className="h-12 w-12 shrink-0 object-contain drop-shadow-[0_4px_10px_rgba(0,0,0,0.5)]" draggable={false} />
      <div className="min-w-0 flex-1 text-xs">
        <p className="font-semibold text-ink-chalk">
          Рента города{state ? ` · домов ${state.owned_total} из ${state.total_houses}` : ""}
        </p>
        {income && income.rate_per_day > 0 ? (
          <p className="text-ink-mist">
            +{fmt(income.rate_per_day)} в день · накоплено <b className="text-legend">{fmt(income.pending)}</b> из {fmt(income.cap)}
          </p>
        ) : (
          <p className="text-ink-mist">Купи первый дом или собери жителей — и рента пойдёт каждый день</p>
        )}
      </div>
      <button
        type="button"
        disabled={!state?.enabled || !income || income.pending <= 0 || busy}
        onClick={onClaim}
        className="min-h-[40px] shrink-0 rounded-xl bg-floodlight px-3 text-xs font-bold text-bg-base disabled:opacity-40"
      >
        Забрать
      </button>
    </section>
  );
}

/** Rent, hotel and residents in one row of three tiles, so the map stays in view. */
function TownStrip({ state, claimBusy, onClaim, hotelBusy, onHotel }: {
  state: TownState; claimBusy: boolean; onClaim: () => void; hotelBusy: boolean; onHotel: () => void;
}) {
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const { income, hotel, residents } = state;
  const tile = "flex min-h-[92px] flex-col items-center justify-between gap-1 rounded-2xl border p-2 text-center";
  const art = "h-8 w-8 object-contain drop-shadow-[0_3px_8px_rgba(0,0,0,0.5)]";
  const hotelShort = Math.max(0, hotel.price - balance);
  return (
    <div className="grid grid-cols-3 gap-2" data-testid="town-strip">
      <button
        type="button"
        aria-label="Рента города"
        disabled={!state.enabled || income.pending <= 0 || claimBusy}
        onClick={onClaim}
        className={`${tile} border-legend/30 bg-legend/5 disabled:opacity-100`}
      >
        <img src={housesArt} alt="" className={art} draggable={false} />
        <span className="text-[11px] leading-tight text-ink-mist">
          Рента · +{fmt(income.rate_per_day)}/д
        </span>
        <span className={`w-full rounded-lg px-1 py-1 text-[11px] font-bold ${income.pending > 0 ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}>
          {income.pending > 0 ? `Забрать ${fmt(income.pending)}` : `0 из ${fmt(income.cap)}`}
        </span>
      </button>
      {hotel.owned ? (
        <div className={`${tile} border-white/10 bg-bg-surface`} aria-label="Отель">
          <img src={hotelArt} alt="" className={art} draggable={false} />
          <span className="text-[11px] leading-tight text-ink-mist">Отель · гостей {fmt(Math.min(hotel.cards, hotel.max_cards))}</span>
          <span className="w-full rounded-lg bg-white/5 px-1 py-1 text-[11px] font-bold text-ink-chalk">+{fmt(hotel.rent)}/д</span>
        </div>
      ) : (
        <button
          type="button"
          aria-label="Отель"
          disabled={!state.enabled || !state.unlocked || hotelBusy || hotelShort > 0}
          onClick={onHotel}
          className={`${tile} border-white/10 bg-bg-surface`}
        >
          <img src={hotelArt} alt="" className={art} draggable={false} />
          <span className="text-[11px] leading-tight text-ink-mist">Отель · +{fmt(hotel.rent)}/д</span>
          <span className={`flex w-full items-center justify-center gap-0.5 rounded-lg px-1 py-1 text-[11px] font-bold ${hotelShort > 0 ? "bg-white/5 text-ink-mist" : "bg-floodlight text-bg-base"}`}>
            <IconCoin size={11} /> {fmt(hotel.price)}
          </span>
        </button>
      )}
      {residents.enabled ? (
        <Link to="/town/residents" className={`${tile} border-cyan-300/25 bg-cyan-400/5`} aria-label="Жители города">
          <img src={residentsArt} alt="" className={art} draggable={false} />
          <span className="text-[11px] leading-tight text-ink-mist">Жители · {fmt(residents.population)}</span>
          <span className="w-full rounded-lg bg-white/5 px-1 py-1 text-[11px] font-bold text-ink-chalk">+{fmt(residents.rent)}/д ›</span>
        </Link>
      ) : <span />}
    </div>
  );
}

function TownMap({
  state, messages, claimBusy, onClaim, hotelBusy, onHotel, renameBusy, onRename, decorBusy, onDecor,
}: {
  state?: TownState; messages: ReactNode; claimBusy: boolean; onClaim: () => void; hotelBusy: boolean; onHotel: () => void;
  renameBusy: boolean; onRename: (name: string) => Promise<unknown>;
  decorBusy: boolean; onDecor: (code: string) => Promise<unknown>;
}) {
  const navigate = useNavigate();
  const [renaming, setRenaming] = useState(false);
  const [place, setPlace] = useState<DecorZone | null>(null);
  const decorOf = (code: string) => state?.decor.find((d) => d.code === code);
  const allLit = !!state && state.decor.length > 0 && state.decor.every((d) => d.owned);
  const owned = (code: string) => state?.districts.find((d) => d.code === code);
  const canRename = !!state?.unlocked && state.enabled && state.rename_stars > 0;
  return (
    <div className="flex flex-col gap-4">
      <GameHero game="home-town" title={state?.name ?? "Город"} subtitle="Шесть районов, дома и жители — всё твоё" />
      {canRename && (
        <button
          type="button"
          onClick={() => setRenaming(true)}
          className="-mt-2 self-center rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist"
        >
          ✏️ {state?.name ? "Переименовать" : "Дать городу имя"} · ⭐ {fmt(state?.rename_stars ?? 0)}
        </button>
      )}
      {messages}
      {state && !(state.enabled && !state.unlocked) && (
        <TownStrip state={state} claimBusy={claimBusy} onClaim={onClaim} hotelBusy={hotelBusy} onHotel={onHotel} />
      )}
      <section className="rounded-3xl border border-white/10 bg-bg-surface p-2">
        <TownScene
          art={TOWN_MAP}
          label="Карта города"
          onPick={(c) => {
            const picked = DECOR_ZONES.find((d) => `decor:${d.code}` === c);
            if (picked) setPlace(picked);
            else navigate(c === "base" ? "/base" : `/town/${c}`);
          }}
          overlay={allLit ? <Fireworks /> : null}
          zones={[...MAP_ZONES.map((z) => {
            const d = owned(z.code);
            return {
              code: z.code,
              label: z.name,
              zone: z.zone,
              badge: (
                <span className="absolute left-1/2 top-1/2 flex -translate-x-1/2 -translate-y-1/2 flex-col items-center whitespace-nowrap rounded-2xl bg-black/65 px-2.5 py-1 font-display text-xs font-bold text-white shadow-lg ring-1 ring-white/25 backdrop-blur-sm group-hover:scale-105">
                  <span><span aria-hidden>{z.emoji}</span> {z.name}</span>
                  {d && (
                    <span className="text-[10px] font-semibold text-white/70">
                      🏠 {d.owned}/{d.total} · {moodEmoji(d.mood)} {d.mood}
                    </span>
                  )}
                </span>
              ),
            };
          }), ...DECOR_ZONES.map((z) => {
            const d = decorOf(z.code);
            return {
              code: `decor:${z.code}`,
              label: d?.owned ? `${z.name} · твоё` : d ? `${z.name} · ${fmt(d.price)} монет` : z.name,
              zone: z.zone,
              badge: <DecorBadge place={z} owned={!!d?.owned} />,
            };
          })]}
        />
      </section>
      <p className="px-1 text-center text-xs text-ink-mist">
        Жители приезжают из паков «Жители» и из магазина. Скоро — профессии и обмен жителями.
      </p>
      <DecorSheet
        place={place}
        state={state}
        busy={decorBusy}
        onBuy={(code) => onDecor(code).then(() => setPlace(null), () => setPlace(null))}
        onClose={() => setPlace(null)}
      />
      <RenameSheet
        open={renaming}
        current={state?.name ?? ""}
        stars={state?.rename_stars ?? 0}
        busy={renameBusy}
        onClose={() => setRenaming(false)}
        onSave={(name) => onRename(name).then(() => setRenaming(false), () => setRenaming(false))}
      />
    </div>
  );
}

/** A closed place on the map: dimmed with a lock, or lit up once bought. */
function DecorBadge({ place, owned }: { place: DecorZone; owned: boolean }) {
  const art = decorArt(place.code);
  if (!owned) {
    return (
      <span className="absolute inset-0 flex flex-col items-center justify-center gap-0.5 rounded-xl border-2 border-dashed border-white/50 bg-black/70 shadow-[inset_0_0_18px_rgba(0,0,0,0.8)]" aria-hidden>
        <span className="text-2xl opacity-40 grayscale">{place.emoji}</span>
        <span className="whitespace-nowrap rounded-full bg-black/75 px-1.5 text-[10px] font-bold leading-4 text-white/85">🔒 {place.name.split(" ")[0]}</span>
      </span>
    );
  }
  return (
    <span className="absolute inset-0" aria-hidden>
      {art ? (
        <img src={art} alt="" className="town-decor-glow absolute inset-0 h-full w-full object-contain" draggable={false} />
      ) : (
        <span className="town-decor-glow absolute inset-0 grid place-items-center text-4xl">{place.emoji}</span>
      )}
      <span className="town-twinkle pointer-events-none absolute -inset-2" />
    </span>
  );
}

const FIREWORK_BURSTS: { x: number; y: number; size: number; color: string; delay: number }[] = [
  { x: 22, y: 34, size: 44, color: "rgb(255 220 110)", delay: 0 },
  { x: 64, y: 22, size: 52, color: "rgb(255 120 190)", delay: 0.7 },
  { x: 44, y: 66, size: 40, color: "rgb(110 235 255)", delay: 1.4 },
  { x: 82, y: 62, size: 36, color: "rgb(200 255 110)", delay: 2 },
];

/** Fireworks over the stadium once every closed place is open. */
function Fireworks() {
  const [x0, y0, x1, y1] = FIREWORKS_BOX;
  return (
    <span
      className="pointer-events-none absolute"
      style={{ left: pct(x0, SCENE_W), top: pct(y0, SCENE_H), width: pct(x1 - x0, SCENE_W), height: pct(y1 - y0, SCENE_H) }}
      aria-hidden
      data-testid="town-fireworks"
    >
      {FIREWORK_BURSTS.map((b, i) => (
        <span
          key={i}
          className="town-firework"
          style={{
            left: `${b.x - b.size / 2}%`, top: `${b.y - b.size / 2}%`, width: `${b.size}%`,
            ["--fw" as string]: b.color, animationDelay: `${b.delay}s`,
          }}
        />
      ))}
    </span>
  );
}

function DecorSheet({
  place, state, busy, onBuy, onClose,
}: {
  place: DecorZone | null; state?: TownState; busy: boolean; onBuy: (code: string) => void; onClose: () => void;
}) {
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const info = place ? state?.decor.find((d) => d.code === place.code) : undefined;
  const short = Math.max(0, (info?.price ?? 0) - balance);
  return createPortal(
    <AnimatePresence>
      {place && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        >
          <motion.div
            role="dialog" aria-label={place.name}
            className="safe-bottom w-full max-w-lg rounded-t-3xl border border-white/10 bg-bg-surface p-4 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }} onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white/5 text-2xl" aria-hidden>{place.emoji}</span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-bold text-ink-chalk">{place.name}</p>
                <p className="text-xs text-ink-mist">{place.about}</p>
              </div>
              <button type="button" onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 place-items-center rounded-full bg-white/5">
                <IconClose size={16} />
              </button>
            </div>
            {!info ? (
              <div className="mt-4 h-16 animate-pulse rounded-2xl bg-white/5" aria-busy />
            ) : info.owned ? (
              <p className="mt-4 rounded-2xl bg-accent-lime/10 px-3 py-2.5 text-sm text-accent-lime">
                ✨ Это место твоё и светится на карте: +{info.rent_pct}% к ренте всех домов.
              </p>
            ) : (
              <div className="mt-4 flex flex-col gap-2">
                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="rounded-2xl bg-white/5 px-3 py-2">
                    <p className="text-[11px] text-ink-mist">Цена</p>
                    <p className="flex items-center justify-center gap-1 font-display text-base font-bold text-legend">
                      <IconCoin size={14} /> {fmt(info.price)}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-white/5 px-3 py-2">
                    <p className="text-[11px] text-ink-mist">Даёт</p>
                    <p className="font-display text-base font-bold text-ink-chalk">+{info.rent_pct}% к ренте домов</p>
                  </div>
                </div>
                <p className="text-[11px] text-ink-mist">Откроешь все места — над стадионом будет фейерверк 🎆</p>
                <button
                  type="button"
                  disabled={!state?.enabled || !state.unlocked || busy || short > 0}
                  onClick={() => onBuy(place.code)}
                  className="min-h-[44px] rounded-xl bg-floodlight px-4 text-sm font-bold text-bg-base disabled:opacity-40"
                >
                  {!state?.unlocked
                    ? "Сначала открой город"
                    : short > 0 ? `Не хватает ${fmt(short)} монет` : `Открыть за ${fmt(info.price)}`}
                </button>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

function RenameSheet({
  open, current, stars, busy, onClose, onSave,
}: {
  open: boolean; current: string; stars: number; busy: boolean; onClose: () => void; onSave: (name: string) => void;
}) {
  const [name, setName] = useState(current);
  useEffect(() => { if (open) setName(current); }, [open, current]);
  const clean = name.trim().replace(/\s+/g, " ");
  const valid = clean.length >= 2 && clean.length <= 24 && clean !== current;
  return createPortal(
    <AnimatePresence>
      {open && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        >
          <motion.form
            role="dialog" aria-label="Название города"
            className="safe-bottom flex w-full max-w-lg flex-col gap-3 rounded-t-3xl border border-white/10 bg-bg-surface p-4 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }} onClick={(e) => e.stopPropagation()}
            onSubmit={(e) => { e.preventDefault(); if (valid) onSave(clean); }}
          >
            <div className="flex items-center justify-between">
              <p className="font-display text-lg font-bold text-ink-chalk">Название города</p>
              <button type="button" onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 place-items-center rounded-full bg-white/5">
                <IconClose size={16} />
              </button>
            </div>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              maxLength={24}
              placeholder="Например, Сан-Виктор"
              aria-label="Новое название"
              className="min-h-[44px] rounded-xl border border-white/10 bg-white/5 px-3 text-base text-ink-chalk outline-none focus:border-accent-lime"
            />
            <p className="text-[11px] text-ink-mist">От 2 до 24 символов: буквы, цифры, пробелы и . ' - « »</p>
            <button
              type="submit"
              disabled={!valid || busy}
              className="min-h-[44px] rounded-xl bg-floodlight px-4 text-sm font-bold text-bg-base disabled:opacity-40"
            >
              Переименовать за ⭐ {fmt(stars)}
            </button>
          </motion.form>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}

function DistrictView({
  district, state, messages, buying, onBuy, settling, onSettle,
}: {
  district: District; state?: TownState; messages: ReactNode; buying: boolean; onBuy: (code: string) => Promise<unknown>;
  settling: boolean; onSettle: (residentId: number, district: string | null) => Promise<unknown>;
}) {
  const [picked, setPicked] = useState<TownBuilding | null>(null);
  const info = state?.districts.find((d) => d.code === district.code);
  // A happy district is busy: the fewer people on its streets, the sadder it is.
  const movers = info ? district.movers.filter((_, i) => i % 10 < 3 + Math.round((info.mood / 100) * 7)) : district.movers;
  const mine = new Set(state?.houses.filter((h) => h.district === district.code).map((h) => h.code));
  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="grid h-11 w-11 shrink-0 place-items-center rounded-2xl bg-white/5 text-2xl" aria-hidden>{district.emoji}</span>
        <div className="min-w-0">
          <h1 className="font-display text-xl font-bold leading-tight text-ink-chalk">{district.name}</h1>
          <p className="truncate text-xs text-ink-mist">
            {info ? `Твоих домов ${info.owned}/${info.total} · дом +${fmt(info.rent)} в день · ${moodEmoji(info.mood)} ${info.mood}` : district.tagline}
          </p>
        </div>
      </div>

      <nav className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1" aria-label="Районы">
        <Link to="/town" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🗺️ Карта</Link>
        {DISTRICTS.map((d) => (
          <Link
            key={d.code}
            to={`/town/${d.code}`}
            replace
            aria-current={d.code === district.code ? "page" : undefined}
            className={`shrink-0 rounded-full px-3 py-1.5 text-xs font-bold ${
              d.code === district.code ? "bg-accent-lime text-bg-base" : "bg-white/5 text-ink-mist"
            }`}
          >
            {d.emoji} {d.name}
          </Link>
        ))}
        <Link to="/base" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🏟️ База</Link>
      </nav>

      {messages}

      <section className="rounded-3xl border border-white/10 bg-bg-surface p-2">
        <TownScene
          art={district.art}
          label={`${district.name}: ${district.buildings.length} зданий`}
          movers={movers}
          water={district.water}
          onPick={(c) => setPicked(district.buildings.find((b) => b.code === c) ?? null)}
          zones={district.buildings.map((b) => {
            const own = mine.has(b.code);
            return {
              code: b.code,
              label: own ? `${b.name} · твой дом` : info ? `${b.name} · ${fmt(info.next_price)} монет` : b.name,
              zone: b.zone,
              locked: !own,
              badge: (
                <span
                  className={`absolute left-1/2 top-1 -translate-x-1/2 rounded-full px-1.5 text-[11px] leading-5 ring-1 ${
                    own ? "bg-accent-lime/85 ring-white/40" : "bg-black/65 ring-white/20"
                  }`}
                  aria-hidden
                >
                  {own ? "🏠" : "🔒"}
                </span>
              ),
            };
          })}
        />
      </section>

      {state && info && state.unlocked && (
        <MoodPanel info={info} state={state} district={district} settling={settling} onSettle={onSettle} />
      )}

      <HouseSheet
        building={picked}
        district={district}
        state={state}
        owned={!!picked && mine.has(picked.code)}
        buying={buying}
        onBuy={(c) => onBuy(c).then(() => setPicked(null), () => setPicked(null))}
        onClose={() => setPicked(null)}
      />
    </div>
  );
}

function moodEmoji(mood: number): string {
  return mood >= 80 ? "😄" : mood >= 60 ? "🙂" : mood >= 40 ? "😐" : "😟";
}

/** The district's mood: what makes it, what it pays, and its residents. */
function MoodPanel({ info, state, district, settling, onSettle }: {
  info: TownDistrictState; state: TownState; district: District; settling: boolean;
  onSettle: (residentId: number, district: string | null) => Promise<unknown>;
}) {
  const m = state.mood;
  const [choosing, setChoosing] = useState(false);
  const { data: album } = useQuery({ queryKey: ["town-residents"], queryFn: fetchTownResidents });
  const byId = new Map((album?.residents ?? []).map((r) => [r.id, r]));
  const settled = info.residents.map((id) => byId.get(id)).filter((r) => !!r);
  const free = Math.max(0, m.resident_slots - info.residents.length);
  const rows: [string, number, number, string][] = [
    ["🧹 Уход", info.parts.care, m.care, `Собирай ренту хотя бы раз в ${m.care_full_hours} ч — иначе уход тает`],
    ["🏠 Дома", info.parts.houses, m.houses, "Каждый купленный дом района"],
    ["⛲ Места", info.parts.decor, m.decor, "Пирс — пляжу, парк — центру и фавелам, остров — всем"],
    ["🧑 Жители", info.parts.residents, m.resident_slots * m.resident_legendary, `До ${m.resident_slots} жителей: +${m.resident}, легенда +${m.resident_legendary}`],
  ];
  return (
    <section className="flex flex-col gap-2 rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Настроение района" data-testid="mood-panel">
      <div className="flex items-center justify-between">
        <p className="text-sm font-bold text-ink-chalk">{moodEmoji(info.mood)} Настроение {info.mood}/100</p>
        <p className={`text-xs font-bold ${info.pct >= 100 ? "text-accent-lime" : "text-legend"}`}>рента домов {info.pct}%</p>
      </div>
      <div className="h-2 overflow-hidden rounded-full bg-white/10">
        <div className="h-full rounded-full bg-gradient-to-r from-amber-400 to-accent-lime" style={{ width: `${info.mood}%` }} />
      </div>
      <ul className="flex flex-col gap-1">
        {rows.map(([label, value, max, hint]) => (
          <li key={label} className="flex items-center gap-2 text-[11px]">
            <span className="w-20 shrink-0 text-ink-chalk">{label}</span>
            <span className="w-12 shrink-0 font-mono text-ink-mist">{value}/{max}</span>
            <span className="min-w-0 flex-1 truncate text-ink-mist-dim">{hint}</span>
          </li>
        ))}
      </ul>
      <div className="flex items-center gap-2">
        {settled.map((r) => (
          <button
            key={r.id} type="button" disabled={settling} onClick={() => void onSettle(r.id, null)}
            className="relative h-12 w-12 shrink-0 overflow-hidden rounded-xl bg-white/5 ring-1 ring-cyan-300/40"
            aria-label={`${r.name} — выписать из района`}
          >
            {r.image_path ? <img src={staticUrl(r.image_path)} alt="" className="h-full w-full object-cover" /> : <span className="text-2xl">{r.icon}</span>}
            <span className="absolute right-0 top-0 rounded-bl bg-black/70 px-0.5 text-[9px] text-white">✕</span>
          </button>
        ))}
        {Array.from({ length: free }, (_, i) => (
          <button
            key={i} type="button" onClick={() => setChoosing(true)}
            className="grid h-12 w-12 shrink-0 place-items-center rounded-xl border-2 border-dashed border-white/20 text-lg text-ink-mist"
            aria-label="Поселить жителя"
          >
            +
          </button>
        ))}
        <span className="min-w-0 flex-1 text-[11px] leading-tight text-ink-mist">Посели сюда жителей. Нажми на жителя, чтобы выписать</span>
      </div>
      {choosing && createPortal(
        <div className="fixed inset-0 z-50 flex items-end justify-center bg-black/60" onClick={() => setChoosing(false)}>
          <div
            role="dialog" aria-label="Поселить жителя" onClick={(e) => e.stopPropagation()}
            className="safe-bottom max-h-[70vh] w-full max-w-lg overflow-y-auto rounded-t-3xl border border-white/10 bg-bg-surface p-4"
          >
            <p className="mb-2 font-display text-lg font-bold text-ink-chalk">Кого поселить: {district.name}</p>
            {!album?.residents.some((r) => r.owned) && (
              <p className="text-xs text-ink-mist">У тебя пока нет жителей — они приходят из паков «Жители».</p>
            )}
            <div className="grid grid-cols-3 gap-2">
              {(album?.residents ?? []).filter((r) => r.owned && r.district !== district.code).map((r) => {
                const elsewhere = r.district ? state.districts.find((d) => d.code === r.district)?.name : null;
                return (
                  <button
                    key={r.id} type="button" disabled={settling}
                    onClick={() => void onSettle(r.id, district.code).then(() => setChoosing(false), () => setChoosing(false))}
                    className="flex flex-col items-center gap-1 rounded-xl bg-white/5 p-2 text-center"
                  >
                    {r.image_path ? <img src={staticUrl(r.image_path)} alt="" className="h-14 w-14 rounded-lg object-cover" /> : <span className="text-3xl">{r.icon}</span>}
                    <span className="text-[11px] font-bold text-ink-chalk">{r.name}</span>
                    {r.bonus_label && <span className="text-[10px] font-semibold text-cyan-300">{r.bonus_label}</span>}
                    <span className="text-[10px] text-ink-mist">
                      {r.rarity === "legendary" ? `+${state.mood.resident_legendary}` : `+${state.mood.resident}`} к настроению
                      {elsewhere ? ` · сейчас: ${elsewhere}` : ""}
                    </span>
                  </button>
                );
              })}
            </div>
          </div>
        </div>,
        document.body,
      )}
    </section>
  );
}

function HouseSheet({
  building, district, state, owned, buying, onBuy, onClose,
}: {
  building: TownBuilding | null; district: District; state?: TownState; owned: boolean; buying: boolean;
  onBuy: (code: string) => void; onClose: () => void;
}) {
  const balance = useAuthStore((s) => s.user?.balance ?? 0);
  const info = state?.districts.find((d) => d.code === district.code);
  const price = info?.next_price ?? 0;
  const short = Math.max(0, price - balance);
  return createPortal(
    <AnimatePresence>
      {building && (
        <motion.div
          className="fixed inset-0 z-50 flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center"
          initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} onClick={onClose}
        >
          <motion.div
            role="dialog" aria-label={building.name}
            className="safe-bottom w-full max-w-lg rounded-t-3xl border border-white/10 bg-bg-surface p-4 sm:rounded-3xl"
            initial={{ y: 80, opacity: 0 }} animate={{ y: 0, opacity: 1 }} exit={{ y: 80, opacity: 0 }}
            transition={{ type: "spring", damping: 24, stiffness: 300 }} onClick={(e) => e.stopPropagation()}
          >
            <div className="flex items-start gap-3">
              <span className="grid h-12 w-12 shrink-0 place-items-center rounded-xl bg-white/5 text-2xl" aria-hidden>{building.emoji}</span>
              <div className="min-w-0 flex-1">
                <p className="font-display text-lg font-bold text-ink-chalk">{building.name}</p>
                <p className="text-xs text-ink-mist">{district.name} · {building.about}</p>
              </div>
              <button type="button" onClick={onClose} aria-label="Закрыть" className="grid h-9 w-9 place-items-center rounded-full bg-white/5">
                <IconClose size={16} />
              </button>
            </div>

            {!info ? (
              <div className="mt-4 h-16 animate-pulse rounded-2xl bg-white/5" aria-busy />
            ) : owned ? (
              <p className="mt-4 rounded-2xl bg-accent-lime/10 px-3 py-2.5 text-sm text-accent-lime">
                🏠 Твой дом. Приносит +{fmt(info.rent)} монет в день — забирай ренту наверху экрана.
              </p>
            ) : (
              <div className="mt-4 flex flex-col gap-2">
                <div className="grid grid-cols-2 gap-2 text-center">
                  <div className="rounded-2xl bg-white/5 px-3 py-2">
                    <p className="text-[11px] text-ink-mist">Цена</p>
                    <p className="flex items-center justify-center gap-1 font-display text-base font-bold text-legend">
                      <IconCoin size={14} /> {fmt(price)}
                    </p>
                  </div>
                  <div className="rounded-2xl bg-white/5 px-3 py-2">
                    <p className="text-[11px] text-ink-mist">Рента</p>
                    <p className="font-display text-base font-bold text-ink-chalk">+{fmt(info.rent)} в день</p>
                  </div>
                </div>
                {!!state?.price_growth_pct && (
                  <p className="text-[11px] text-ink-mist">
                    Каждый купленный дом поднимает цену следующих на {state?.price_growth_pct}%.
                  </p>
                )}
                <button
                  type="button"
                  disabled={!state?.enabled || !state.unlocked || buying || short > 0}
                  onClick={() => onBuy(building.code)}
                  className="min-h-[44px] rounded-xl bg-floodlight px-4 text-sm font-bold text-bg-base disabled:opacity-40"
                >
                  {!state?.unlocked
                    ? "Сначала открой город"
                    : short > 0 ? `Не хватает ${fmt(short)} монет` : `Купить за ${fmt(price)}`}
                </button>
              </div>
            )}
          </motion.div>
        </motion.div>
      )}
    </AnimatePresence>,
    document.body,
  );
}
