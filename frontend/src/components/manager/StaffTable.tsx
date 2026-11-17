import { useMutation } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState, type ReactNode } from "react";

import {
  buyManagerFleet,
  fireManagerStaff,
  hireManagerStaff,
  orderManagerStaff,
  type ManagerFleetKind,
  type ManagerRarity,
  type ManagerStaffMember,
  type ManagerStaffRole,
  type ManagerStaffView,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { staticUrl } from "@/lib/api";
import { eur } from "@/lib/managerMoney";
import { staffArt } from "@/lib/staffArt";
import { hapticSelection } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

export const RARITY: Record<ManagerRarity, { label: string; ring: string; text: string; glow: string }> = {
  common: { label: "обычный", ring: "ring-white/30", text: "text-ink-mist", glow: "" },
  rare: { label: "редкий", ring: "ring-sky-400", text: "text-sky-300", glow: "shadow-[0_0_14px_-2px_rgba(56,189,248,0.7)]" },
  epic: { label: "эпический", ring: "ring-fuchsia-400", text: "text-fuchsia-300", glow: "shadow-[0_0_14px_-2px_rgba(232,121,249,0.7)]" },
  legendary: { label: "легендарный", ring: "ring-amber-300", text: "text-amber-300", glow: "shadow-[0_0_18px_-2px_rgba(252,211,77,0.9)]" },
};

/** A seat's label under the photo (the full name is in its sheet). */
const SHORT: Record<string, string> = {
  coach: "Тренер", director: "Спортдиректор", scout: "Скаутинг", academy: "Академия", physio: "Медцентр",
  transport: "Транспорт", stadium: "Стадион", press: "Пресса", marketing: "Коммерция", finance: "Финансы",
};

/** The chairs of `council_table.webp` (square, % of its side): the
 * president's, then the ten departments clockwise. The VIP desks are by
 * the cabinets in its top corners (StaffTab's VipCorner). */
const TABLE_SEATS: [number, number][] = [
  [50, 33], [68.6, 37.5], [79.7, 47], [85.5, 58], [79.7, 74], [60.6, 85],
  [39.9, 85], [20.7, 74], [14.5, 58], [20.3, 47], [31.5, 37.5],
];

/** Seat `i` of `n` around the table, the president's at the top. */
function seatAt(i: number, n: number, r = 41): { left: string; top: string } {
  const a = -Math.PI / 2 + (2 * Math.PI * i) / n;
  return { left: `${50 + r * Math.cos(a)}%`, top: `${50 + r * Math.sin(a)}%` };
}

function Face({ m, size }: { m: { image: string | null; icon: string; name: string }; size: number }) {
  return m.image
    ? <img src={staticUrl(m.image)} alt={m.name} className="h-full w-full object-cover" />
    : <span className="flex h-full w-full items-center justify-center bg-bg-raised" style={{ fontSize: size * 0.48 }}>{m.icon}</span>;
}

/** «Штат»: a round table — the president at its head (his Telegram photo),
 * a seat for each of the ten departments. A tap opens the seat's sheet. */
export default function StaffTable({ data, onDone, onError, extra, corners, onHelp }: {
  data: ManagerStaffView; onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void;
  /** Department-specific panel inside its sheet (the sporting director). */
  extra?: (role: ManagerStaffRole) => ReactNode;
  /** The VIP desks by the cabinets (absolutely placed over the table). */
  corners?: ReactNode;
  /** «?» by the title: how the staff works. */
  onHelp?: () => void;
}) {
  const user = useAuthStore((s) => s.user);
  const [open, setOpen] = useState<ManagerStaffRole | null>(null);
  const byRole = new Map(data.staff.map((s) => [s.role, s]));
  const full = data.staff.length >= data.slots;
  const n = data.roles.length + 1;
  const table = staffArt("council_table");
  const chair = staffArt("seat_empty");
  const at = (i: number) => (table && n === TABLE_SEATS.length
    ? { left: `${TABLE_SEATS[i][0]}%`, top: `${TABLE_SEATS[i][1]}%` } : seatAt(i, n));
  return (
    <section className="flex flex-col gap-3 rounded-3xl bg-gradient-to-b from-[#16120c] to-bg-surface p-3 ring-1 ring-amber-200/15" data-testid="club-staff">
      <div className="flex items-center justify-between gap-2 px-1">
        <h2 className="flex items-center gap-2 font-display text-base font-bold text-ink-chalk">
          🏢 Персонал клуба
          {onHelp && (
            <button onClick={onHelp} aria-label="Как работает персонал" data-testid="staff-help"
              className="flex h-6 w-6 items-center justify-center rounded-full bg-white/10 text-xs font-black text-amber-100 active:scale-90">?</button>
          )}
        </h2>
        <span className="rounded-full bg-black/40 px-2 py-0.5 text-micro font-bold text-amber-100">
          {data.staff.length}/{data.slots} мест · {eur(data.wages)}/сезон
        </span>
      </div>
      <div className="relative mx-auto aspect-square w-full max-w-[420px]" data-testid="staff-table">
        {table ? (
          <img src={table} alt="" className="absolute inset-0 h-full w-full rounded-2xl object-cover" />
        ) : (
          <div className="absolute left-1/2 top-1/2 h-[56%] w-[56%] -translate-x-1/2 -translate-y-1/2 rounded-full bg-[radial-gradient(circle_at_40%_35%,#5a3b22,#2b1a0e_70%)] shadow-[0_20px_60px_-10px_rgba(0,0,0,0.9),inset_0_0_0_6px_rgba(212,175,55,0.35)]">
            <div className="absolute inset-[18%] rounded-full border border-amber-300/30 bg-[radial-gradient(circle,rgba(34,120,60,0.45),rgba(20,60,30,0.15))]">
              <div className="absolute left-1/2 top-0 h-full w-px bg-amber-200/25" />
              <div className="absolute left-1/2 top-1/2 h-1/3 w-1/3 -translate-x-1/2 -translate-y-1/2 rounded-full border border-amber-200/25" />
            </div>
          </div>
        )}
        {corners}
        {/* The president */}
        <div className="absolute -translate-x-1/2 -translate-y-1/2 text-center" style={{ ...at(0), width: "19%" }} data-testid="seat-president">
          <span className="mx-auto block aspect-square w-[72%] overflow-hidden rounded-full ring-[3px] ring-amber-300 shadow-[0_0_20px_-2px_rgba(252,211,77,0.9)]">
            {user?.avatar_url
              ? <img src={user.avatar_url} alt="" className="h-full w-full object-cover" />
              : <span className="flex h-full w-full items-center justify-center bg-amber-300 font-display text-xl font-black text-bg-base">{(user?.first_name || "П")[0]}</span>}
          </span>
          <span className="mt-0.5 inline-block rounded-full bg-black/55 px-1.5 text-[9px] font-black uppercase tracking-wide text-amber-200">Президент</span>
        </div>
        {data.roles.map((r, i) => {
          const m = byRole.get(r.code);
          const pos = at(i + 1);
          const icon = staffArt(`dept_${r.code}`);
          return (
            <button key={r.code} onClick={() => { hapticSelection(); setOpen(r.code); }} data-testid={`seat-${r.code}`}
              className="absolute -translate-x-1/2 -translate-y-1/2 text-center active:scale-95" style={{ ...pos, width: "17%" }}>
              <span className={`relative mx-auto block aspect-square w-[66%] rounded-full ${m ? `ring-2 ${RARITY[m.rarity].ring} ${RARITY[m.rarity].glow}` : table ? "" : "border border-dashed border-white/30"}`}>
                <span className="block h-full w-full overflow-hidden rounded-full">
                  {m ? <Face m={m} size={34} /> : table
                    // The real chair of the picture stays empty: just a «+» on it.
                    ? <span className={`flex h-full w-full items-center justify-center text-lg font-black ${full ? "text-white/30" : "text-amber-100 drop-shadow-[0_0_6px_rgba(252,211,77,0.9)]"}`}>{full ? "🔒" : "＋"}</span>
                    : chair
                    ? <img src={chair} alt="" className={`h-full w-full object-cover ${full ? "opacity-30" : "opacity-70"}`} />
                    : <span className={`flex h-full w-full items-center justify-center bg-black/50 text-lg ${full ? "text-white/20" : "text-white/50"}`}>{full ? "🔒" : "＋"}</span>}
                </span>
                {icon
                  ? <img src={icon} alt="" className="absolute -bottom-1.5 -right-2 h-[52%] w-[52%] drop-shadow" />
                  : <span className="absolute -bottom-1 -right-1.5 flex h-[45%] w-[45%] items-center justify-center rounded-full bg-bg-base text-[11px] ring-1 ring-white/15">{r.emoji}</span>}
              </span>
              <span className={`mt-0.5 block truncate rounded-full bg-black/55 px-1 text-[9px] font-bold leading-tight ${m ? "text-ink-chalk" : "text-ink-mist"}`}>{SHORT[r.code] ?? r.dept}</span>
            </button>
          );
        })}
      </div>
      {!data.window && <p className="px-1 text-micro text-amber-200">⏳ Нанимать — в межсезонье. Поручения и транспорт — в карточке департамента.</p>}
      <AnimatePresence>
        {open && (
          <SeatSheet key={open} role={open} data={data} member={byRole.get(open)} full={full} onClose={() => setOpen(null)}
            onDone={onDone} onError={onError} extra={extra?.(open)} />
        )}
      </AnimatePresence>
    </section>
  );
}

function SeatSheet({ role, data, member, full, onClose, onDone, onError, extra }: {
  role: ManagerStaffRole; data: ManagerStaffView; member?: ManagerStaffMember; full: boolean; onClose: () => void;
  onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void; extra?: ReactNode;
}) {
  const info = data.roles.find((r) => r.code === role)!;
  const [fire, setFire] = useState(false);
  const [pick, setPick] = useState(!member);
  const hire = useMutation({
    mutationFn: async (resident: number) => {
      if (member) await fireManagerStaff(member.id);
      return hireManagerStaff(resident, role);
    },
    onSuccess: (v) => { setPick(false); onDone(v); }, onError,
  });
  const out = useMutation({ mutationFn: () => fireManagerStaff(member!.id), onSuccess: (v) => { onDone(v); onClose(); }, onError });
  const order = useMutation({ mutationFn: () => orderManagerStaff(role), onSuccess: onDone, onError });
  const o = data.orders[role];
  return (
    <>
      <motion.div className="fixed inset-0 z-[60] bg-black/60" onClick={onClose} initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
      <motion.section
        className="fixed inset-x-0 bottom-0 z-[61] mx-auto flex max-h-[86vh] max-w-[480px] flex-col gap-3 overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-8 ring-1 ring-white/10"
        initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 30, stiffness: 320 }}
        data-testid="seat-sheet" role="dialog" aria-label={info.dept}>
        <div className="mx-auto h-1 w-10 rounded-full bg-white/20" />
        <div className="flex items-center gap-3">
          <span className={`h-20 w-20 shrink-0 overflow-hidden rounded-2xl ${member ? `ring-2 ${RARITY[member.rarity].ring} ${RARITY[member.rarity].glow}` : "ring-1 ring-white/15"}`}>
            {member ? <Face m={member} size={80} /> : staffArt(`dept_${role}`)
              ? <img src={staffArt(`dept_${role}`)} alt="" className="h-full w-full bg-bg-raised object-contain p-1" />
              : <span className="flex h-full w-full items-center justify-center bg-bg-raised text-4xl">{info.emoji}</span>}
          </span>
          <div className="min-w-0 flex-1">
            <p className="text-micro font-bold uppercase tracking-[0.16em] text-amber-200">{info.emoji} {info.dept}</p>
            <p className="font-display text-lg font-black leading-tight text-ink-chalk">{member ? member.name : "Место свободно"}</p>
            <p className="text-caption text-ink-mist">{info.name}{member ? <> · <span className={RARITY[member.rarity].text}>{RARITY[member.rarity].label}</span></> : ""}</p>
          </div>
          <button onClick={onClose} aria-label="Закрыть" className="self-start rounded-full bg-bg-raised px-2.5 py-1 text-sm text-ink-mist">✕</button>
        </div>

        {member && (
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-xl bg-accent-lime/10 p-2.5 ring-1 ring-accent-lime/30">
              <p className="text-micro text-ink-mist">Эффект</p>
              <p className="text-xs font-bold text-accent-lime">{member.effect_text}</p>
            </div>
            <div className="rounded-xl bg-bg-raised p-2.5">
              <p className="text-micro text-ink-mist">Зарплата</p>
              <p className="text-xs font-bold text-ink-chalk">{eur(member.wage)}/сезон</p>
            </div>
          </div>
        )}
        <div className="rounded-xl bg-black/25 p-2.5">
          <p className="mb-1 text-micro font-bold uppercase tracking-wide text-ink-mist">Сила по редкости</p>
          {(Object.keys(RARITY) as ManagerRarity[]).map((r) => (
            <p key={r} className={`flex justify-between text-caption ${member?.rarity === r ? "font-bold text-ink-chalk" : "text-ink-mist"}`}>
              <span className={RARITY[r].text}>{RARITY[r].label}</span><span>{info.effects[r]}</span>
            </p>
          ))}
        </div>

        {member && o && (
          <div className="flex flex-col gap-1.5 rounded-xl bg-gradient-to-br from-amber-400/15 to-transparent p-3 ring-1 ring-amber-300/30" data-testid="staff-order">
            <p className="text-sm font-bold text-ink-chalk">{o.emoji} Поручение: {o.title}</p>
            <p className="text-caption text-ink-mist">{o.about}</p>
            <p className="text-micro text-amber-100">
              {[o.fans ? `+${o.fans} болельщиков` : "", o.form_pct ? `+${o.form_pct}% к форме на ${o.form_rounds} тур.` : "", "раз в сезон"].filter(Boolean).join(" · ")}
              {o.season ? " · только во время сезона" : ""}
            </p>
            <button disabled={o.done || order.isPending} onClick={() => order.mutate()} data-testid="order-do"
              className="mt-1 rounded-xl bg-amber-300 py-2 text-sm font-bold text-bg-base active:scale-95 disabled:bg-bg-raised disabled:text-ink-mist">
              {o.done ? "✓ Уже в этом сезоне" : `Поручить · ${eur(o.cost)}`}
            </button>
          </div>
        )}

        {member && role === "transport" && <FleetPanel kinds={data.fleet.kinds} window={data.window} onDone={onDone} onError={onError} />}
        {member && extra}

        {pick ? (
          <div className="flex flex-col gap-1.5" data-testid="hire-sheet">
            <p className="text-xs font-bold text-ink-chalk">{member ? "Кем заменить?" : `Кого назначить: ${info.name.toLowerCase()}?`}</p>
            {!data.window && <p className="text-micro text-amber-200">⏳ Нанимать — в межсезонье.</p>}
            {full && !member && <p className="text-micro text-amber-200">Все {data.slots} мест штаба заняты — освободи место или поднимись в дивизионе.</p>}
            {data.candidates.length === 0 && <p className="text-micro text-ink-mist">Нет свободных жителей — выбивай их в паках «Жители города».</p>}
            {data.candidates.map((c) => (
              <button key={c.resident_id} disabled={hire.isPending || !data.window || (full && !member)} onClick={() => hire.mutate(c.resident_id)}
                className={`flex items-center gap-2 rounded-xl bg-bg-raised p-2 text-left ring-1 disabled:opacity-50 ${RARITY[c.rarity].ring}`}>
                <span className="h-9 w-9 shrink-0 overflow-hidden rounded-lg"><Face m={c} size={36} /></span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-bold text-ink-chalk">{c.name}</span>
                  <span className={`block text-[10px] font-semibold ${RARITY[c.rarity].text}`}>{RARITY[c.rarity].label} · {info.effects[c.rarity]}</span>
                </span>
                <span className="shrink-0 text-[10px] text-ink-mist">{eur(c.wage)}</span>
              </button>
            ))}
          </div>
        ) : member && (
          <div className="grid grid-cols-2 gap-2">
            <button onClick={() => setPick(true)} className="rounded-xl bg-bg-raised py-2.5 text-sm font-bold text-ink-chalk">🔄 Заменить</button>
            <button onClick={() => setFire(true)} className="rounded-xl bg-red-500/15 py-2.5 text-sm font-bold text-red-300">Уволить</button>
          </div>
        )}
        <ConfirmDialog open={fire} title="Уволить сотрудника?" description="Житель останется в городе, должность освободится."
          confirmLabel="Уволить" onConfirm={() => { setFire(false); out.mutate(); }} onCancel={() => setFire(false)} />
      </motion.section>
    </>
  );
}

/** «Транспортный департамент»: the bus and the plane, level by level. */
function FleetPanel({ kinds, window, onDone, onError }: {
  kinds: ManagerFleetKind[]; window: boolean; onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void;
}) {
  const buy = useMutation({ mutationFn: buyManagerFleet, onSuccess: onDone, onError });
  const [ask, setAsk] = useState<ManagerFleetKind | null>(null);
  const next = ask ? ask.items[ask.level] : null;
  return (
    <div className="flex flex-col gap-2" data-testid="fleet">
      <p className="text-micro font-bold uppercase tracking-wide text-ink-mist">Парк клуба</p>
      {kinds.map((k) => {
        const now = k.level > 0 ? k.items[k.level - 1] : null;
        const up = k.items[k.level];
        // Nothing bought yet: the empty hangar, else the next item greyed out.
        const hangar = now ? undefined : staffArt(`hangar_${k.kind}`) ?? staffArt("hangar");
        const art = hangar ?? staffArt(now?.code ?? up?.code);
        return (
          <div key={k.kind} className="overflow-hidden rounded-xl bg-bg-raised ring-1 ring-white/5">
            <div className="relative h-24 bg-gradient-to-br from-slate-800 to-black">
              {art ? <img src={art} alt="" className={`h-full w-full object-cover ${now || hangar ? "" : "opacity-40 grayscale"}`} />
                : <span className={`flex h-full items-center justify-center text-5xl ${now ? "" : "opacity-30 grayscale"}`}>{(now ?? up)?.emoji}</span>}
              <span className="absolute left-2 top-2 rounded-full bg-black/60 px-2 py-0.5 text-micro font-bold text-ink-chalk">{k.title}: {now ? now.name : "нет"}</span>
            </div>
            <div className="flex items-center gap-2 p-2.5">
              <span className="min-w-0 flex-1 text-[11px] text-ink-mist">
                {now ? <>+{now.away_pct}% в гостях{now.injury_pct ? ` · −${now.injury_pct}% травм` : ""} · {eur(now.upkeep)}/сезон</> : "Своего транспорта нет"}
              </span>
              {up ? (
                <button disabled={!window || buy.isPending} onClick={() => setAsk(k)}
                  className="shrink-0 rounded-lg bg-amber-300 px-2.5 py-1.5 text-[11px] font-bold text-bg-base disabled:opacity-40">
                  {now ? "Улучшить" : "Купить"} · {eur(up.price)}
                </button>
              ) : <span className="shrink-0 text-[11px] font-bold text-amber-200">лучший</span>}
            </div>
          </div>
        );
      })}
      {!window && <p className="text-micro text-amber-200">⏳ Покупать транспорт — в межсезонье.</p>}
      <ConfirmDialog open={!!ask} title={next ? `${next.emoji} ${next.name}?` : ""}
        description={next ? `${eur(next.price)} из бюджета клуба, содержание ${eur(next.upkeep)} за сезон: +${next.away_pct}% к силе в гостях${next.injury_pct ? `, −${next.injury_pct}% к травмам` : ""}.` : undefined}
        confirmLabel="Купить" onConfirm={() => { if (ask) buy.mutate(ask.kind); setAsk(null); }} onCancel={() => setAsk(null)} />
    </div>
  );
}
