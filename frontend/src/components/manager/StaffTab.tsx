import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useState } from "react";

import {
  buyManagerStaffItem,
  doManagerAdvice,
  fetchManagerAssistant,
  fetchManagerDecisions,
  fetchManagerDirector,
  fetchManagerStaff,
  renameManagerVip,
  setManagerAssistantRules,
  setManagerDirectorBudget,
  signManagerNpc,
  startManagerAssistantTrial,
  wearManagerStaffItem,
  type ManagerAssistantRules,
  type ManagerDirectorOption,
  type ManagerRarity,
  type ManagerStaffItem,
  type ManagerStaffView,
  type ManagerVip,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import CoachCard from "@/components/manager/CoachCard";
import { FinanceReview } from "@/components/manager/PresidentDecisions";
import OfficeScene, { CarArt } from "@/components/manager/OfficeScene";
import StaffPortrait from "@/components/manager/StaffPortrait";
import StaffTable from "@/components/manager/StaffTable";
import { staticUrl } from "@/lib/api";
import { useFocusTarget } from "@/lib/managerFocus";
import { MIcon } from "@/lib/managerIcons";
import { eur } from "@/lib/managerMoney";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify, hapticSelection } from "@/lib/telegram";
import { usePersistentState } from "@/lib/usePersistentState";

const RARITY: Record<ManagerRarity, { label: string; ring: string; text: string }> = {
  common: { label: "обычный", ring: "ring-white/15", text: "text-ink-mist" },
  rare: { label: "редкий", ring: "ring-sky-400/60", text: "text-sky-300" },
  epic: { label: "эпический", ring: "ring-fuchsia-400/60", text: "text-fuchsia-300" },
  legendary: { label: "легендарный", ring: "ring-amber-300/80", text: "text-amber-300" },
};

const until = (iso: string | null) => iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : "";

type Vip = "assistant" | "analyst";

/** Where a «Сегодня в клубе» target lives. */
const FOCUS: Record<string, Vip> = { advice: "assistant", analyst: "analyst" };

/** «👥 Штаб» of «Менеджер»: a hero with the office and both VIP, then four
 * desks — «Помощница» (her report with one-tap advice and the fine rules),
 * «Аналитик» (skills and his finance review), «Штат» (the club staff from the
 * owner's «Жители города» and the sporting director) and «Гараж». */
export default function StaffTab({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "staff"], queryFn: fetchManagerStaff });
  // The round table is the tab; a VIP's desk opens under it from their corner.
  const [desk, setDesk] = useState<Vip | null>(null);
  const [introSeen, setIntroSeen] = usePersistentState<boolean>("manager.staffIntro", false);
  const [help, setHelp] = useState(false);
  const intro = help || !introSeen;
  const closeIntro = () => { setIntroSeen(true); setHelp(false); };
  const [busy, setBusy] = useState<string | null>(null);
  useFocusTarget((t) => { if (FOCUS[t]) setDesk(FOCUS[t]); });
  const done = (v: ManagerStaffView) => {
    hapticNotify("success");
    queryClient.setQueryData(["manager", "staff"], v);
    void queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
    void queryClient.invalidateQueries({ queryKey: ["manager", "assistant"] });
  };
  const stars = async (code: string) => {
    setBusy(code);
    try {
      if ((await payMyPlayerWithStars({ purchase: "manager", code })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["manager"] });
      }
    } catch (err) {
      onError(err);
    } finally {
      setBusy(null);
    }
  };
  const trial = useMutation({ mutationFn: startManagerAssistantTrial, onSuccess: done, onError });
  const item = useMutation({
    mutationFn: ({ code, buy }: { code: string; buy: boolean }) => (buy ? buyManagerStaffItem(code) : wearManagerStaffItem(code)),
    onSuccess: done, onError,
  });
  if (!data) return <ListSkeleton />;
  const none = data.vip.every((v) => !v.active);
  const takeItem = (i: ManagerStaffItem) => {
    if (i.owned) item.mutate({ code: i.code, buy: false });
    else if (i.stars > 0) void stars(i.code);
    else item.mutate({ code: i.code, buy: true });
  };
  const vipOf = (role: "assistant" | "analyst") => data.vip.find((v) => v.role === role) ?? data.vip[0];
  const details = (role: "assistant" | "analyst") => {
    const vip = vipOf(role);
    return (
      <VipDetails key={vip.role} vip={vip} data={data} busy={busy === vip.code || trial.isPending} onStars={() => void stars(vip.code)}
        onTrial={() => trial.mutate()} onDone={done} onError={onError} onItem={takeItem} itemBusy={item.isPending || !!busy} />
    );
  };

  return (
    <div className="flex flex-col gap-4" data-testid="staff-tab">
      {/* What the tab is: a popup on the first visit, then behind «?» by the table's title. */}
      <AnimatePresence>
        {intro && (
          <>
            <motion.div key="intro-shade" className="fixed inset-0 z-[60] bg-black/60" onClick={closeIntro}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.section key="intro" data-testid="staff-hero" role="dialog" aria-label="Персонал"
              className="fixed inset-x-4 top-[14vh] z-[61] mx-auto max-h-[72vh] max-w-[440px] overflow-y-auto rounded-3xl bg-[#0e1622] shadow-2xl ring-1 ring-violet-300/30"
              initial={{ opacity: 0, scale: 0.92 }} animate={{ opacity: 1, scale: 1 }} exit={{ opacity: 0, scale: 0.92 }}>
        <OfficeScene room={data.worn.room?.art} code={data.worn.room?.code} className="absolute inset-0 h-full w-full opacity-45" />
        <div className="absolute inset-0 bg-gradient-to-b from-[#120d24]/70 via-[#0e1622]/85 to-[#0b1410]" />
        <div className="relative p-4">
          <p className="text-micro font-bold uppercase tracking-[0.2em] text-violet-200">👥 Персонал</p>
          <p className="mt-1 text-xs text-ink-mist">Жители города за круглым столом усиливают клуб. {vipOf("assistant").name} и {vipOf("analyst").name} — у шкафов: нажми на них.</p>
          <HeroChips data={data} />
          {none && data.bundle_stars > 0 && (
            <button disabled={busy === "staff_bundle"} onClick={() => void stars("staff_bundle")} data-testid="staff-bundle"
              className="mt-3 flex w-full items-center justify-between gap-2 rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 px-3.5 py-2.5 text-left text-bg-base shadow-[0_8px_24px_-10px_rgba(251,191,36,0.9)]">
              <span className="min-w-0">
                <span className="block text-sm font-black">Оба сразу</span>
                <span className="block text-micro font-semibold opacity-80">Аналитик + помощник на {vipOf("assistant").days} дн. — выгоднее</span>
              </span>
              <span className="shrink-0 rounded-xl bg-black/20 px-2.5 py-1 text-sm font-black">{data.bundle_stars} ⭐</span>
            </button>
          )}
        </div>
              <div className="relative flex flex-col gap-2 px-4 pb-4">
                <p className="text-micro leading-snug text-ink-mist">Сила клуба — от персонала из жителей города и твоих решений. {vipOf("assistant").name}, {vipOf("analyst").name} и их образы — удобство и стиль. Машины и кабинеты — в «Клуб» → «Стиль».</p>
                <button onClick={closeIntro} className="w-full rounded-2xl bg-floodlight py-2.5 text-sm font-bold text-bg-base" data-testid="staff-intro-ok">Понятно</button>
              </div>
            </motion.section>
          </>
        )}
      </AnimatePresence>

      <StaffTable data={data} onDone={done} onError={onError}
        extra={(role) => (role === "director" ? <DirectorPanel data={data} onError={onError} />
          : role === "coach" ? (() => { const c = data.staff.find((s) => s.role === "coach")?.coach; return c ? <CoachCard coach={c} compact /> : null; })()
          : null)}
        onHelp={() => setHelp(true)}
        corners={data.vip.map((v) => <VipCorner key={v.code} vip={v} on={desk === v.role}
          onPick={() => { hapticSelection(); setDesk(desk === v.role ? null : v.role); }} />)} />

      {/* A VIP's desk opens as a sheet from the bottom, like the seats at the table. */}
      <AnimatePresence>
        {desk && (
          <>
            <motion.div key="shade" className="fixed inset-0 z-[60] bg-black/60" onClick={() => setDesk(null)}
              initial={{ opacity: 0 }} animate={{ opacity: 1 }} exit={{ opacity: 0 }} />
            <motion.section key="sheet"
              className="fixed inset-x-0 bottom-0 z-[61] mx-auto flex max-h-[86vh] max-w-[480px] flex-col gap-3 overflow-y-auto rounded-t-3xl bg-bg-surface p-4 pb-8 ring-1 ring-violet-300/25"
              initial={{ y: "100%" }} animate={{ y: 0 }} exit={{ y: "100%" }} transition={{ type: "spring", damping: 30, stiffness: 320 }}
              data-testid="vip-sheet" role="dialog" aria-label={vipOf(desk).name}>
              <div className="mx-auto h-1 w-10 rounded-full bg-white/20" />
              <div className="flex items-center gap-3">
                <span className="h-16 w-16 shrink-0 overflow-hidden rounded-2xl ring-2 ring-violet-300">
                  <StaffPortrait role={desk} art={vipOf(desk).skin?.art} code={vipOf(desk).skin?.code} size={64} />
                </span>
                <div className="min-w-0 flex-1">
                  <p className="text-micro font-bold uppercase tracking-[0.16em] text-violet-200">{desk === "assistant" ? "🗂 Помощница" : "📊 Аналитик"}</p>
                  <p className="font-display text-lg font-black leading-tight text-ink-chalk">{vipOf(desk).name}</p>
                  <p className="text-caption text-ink-mist">{vipOf(desk).active ? "Работает на тебя" : "Пока не нанят"}</p>
                </div>
                <button onClick={() => setDesk(null)} aria-label="Закрыть" className="self-start rounded-full bg-bg-raised px-2.5 py-1 text-sm text-ink-mist" data-testid="desk-close">✕</button>
              </div>
              {desk === "assistant" && (
                <>
                  {vipOf("assistant").active && <AssistantDesk onError={onError} />}
                  {details("assistant")}
                </>
              )}
              {desk === "analyst" && (
                <>
                  {details("analyst")}
                  {vipOf("analyst").active && <AnalystReview />}
                </>
              )}
            </motion.section>
          </>
        )}
      </AnimatePresence>
    </div>
  );
}

/** «Гараж»: the president's car and office room — in «Клуб» → «Стиль». */
export function StaffGarage({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "staff"], queryFn: fetchManagerStaff });
  const [busy, setBusy] = useState(false);
  const item = useMutation({
    mutationFn: ({ code, buy }: { code: string; buy: boolean }) => (buy ? buyManagerStaffItem(code) : wearManagerStaffItem(code)),
    onSuccess: (v) => { hapticNotify("success"); queryClient.setQueryData(["manager", "staff"], v); },
    onError,
  });
  if (!data) return null;
  const take = async (i: ManagerStaffItem) => {
    if (i.owned) return item.mutate({ code: i.code, buy: false });
    if (i.stars <= 0) return item.mutate({ code: i.code, buy: true });
    setBusy(true);
    try {
      if ((await payMyPlayerWithStars({ purchase: "manager", code: i.code })) === "paid") {
        hapticNotify("success");
        await queryClient.invalidateQueries({ queryKey: ["manager"] });
      }
    } catch (err) {
      onError(err);
    } finally {
      setBusy(false);
    }
  };
  return (
    <section className="flex flex-col gap-2" data-testid="style-garage">
      <h2 className="flex items-center gap-2 px-1 font-display text-base font-bold text-ink-chalk">
        <MIcon code="desk_garage" emoji="🚘" className="h-7 w-7" /> Гараж и кабинет
      </h2>
      <Status data={data} onItem={(i) => void take(i)} busy={item.isPending || busy} />
    </section>
  );
}

function HeroChips({ data }: { data: ManagerStaffView }) {
  const { data: office } = useQuery({ queryKey: ["manager", "assistant"], queryFn: fetchManagerAssistant, enabled: data.vip.some((v) => v.role === "assistant" && v.active) });
  const chips = [`🏢 Персонал ${data.staff.length}/${data.slots}`, `💶 ${eur(data.wages)}/сезон`];
  if (office?.active) chips.push(office.rules.mode === "advise" ? "🗒 Только советует" : "⚙️ Действует сама");
  if (office?.report.todo) chips.push(`💡 Советов: ${office.report.todo}`);
  return (
    <div className="mt-3 flex flex-wrap gap-1.5">
      {chips.map((c) => <span key={c} className="rounded-full bg-black/40 px-2.5 py-1 text-micro font-semibold text-violet-100 ring-1 ring-white/10">{c}</span>)}
    </div>
  );
}

// --- «Помощница»: the report, one-tap advice ------------------------------------------------------

function AssistantDesk({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "assistant"], queryFn: fetchManagerAssistant });
  const advice = useMutation({
    mutationFn: doManagerAdvice,
    onSuccess: (v) => {
      hapticNotify("success");
      queryClient.setQueryData(["manager", "assistant"], v);
      void queryClient.invalidateQueries({ queryKey: ["manager"] });
    },
    onError,
  });
  if (!data) return null;
  const todo = data.report.entries.filter((e) => e.action && !e.done && e.id);
  const rest = data.report.entries.filter((e) => !(e.action && !e.done && e.id)).slice(0, 6);
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl bg-gradient-to-br from-violet-500/15 to-bg-surface p-4 ring-1 ring-violet-300/25" data-testid="assistant-desk" data-focus="advice">
      <p className="flex items-center justify-between text-sm font-bold text-ink-chalk">
        <span>🗂 Отчёт {data.name}</span>
        <span className="text-micro font-semibold text-ink-mist">−{eur(data.report.spent)} · +{eur(data.report.earned)}</span>
      </p>
      {todo.length > 0 && (
        <div className="flex flex-col gap-1.5">
          <p className="text-micro font-bold uppercase tracking-[0.14em] text-accent-lime">Ждут твоего решения</p>
          {todo.map((e) => (
            <div key={e.id} className="flex items-center gap-2 rounded-xl bg-accent-lime/10 p-2 ring-1 ring-accent-lime/30">
              <span className="text-base leading-none">{e.icon}</span>
              <span className="min-w-0 flex-1 text-caption text-ink-chalk">{e.text}</span>
              <button disabled={advice.isPending} onClick={() => advice.mutate(e.id!)} data-testid="advice-do"
                className="shrink-0 rounded-lg bg-accent-lime px-2.5 py-1.5 text-micro font-black text-bg-base active:scale-95 disabled:opacity-50">
                Сделать
              </button>
            </div>
          ))}
        </div>
      )}
      {rest.length > 0 ? (
        <ul className="flex flex-col gap-1">
          {rest.map((e, i) => (
            <li key={e.id ?? `${e.at}-${i}`} className={`flex gap-2 text-caption ${e.done ? "text-ink-mist" : "text-ink-chalk"}`}>
              <span>{e.done ? "✅" : e.icon}</span><span className="min-w-0 flex-1">{e.text}</span>
              {e.eur !== 0 && !e.action && <span className={e.eur > 0 ? "text-emerald-300" : "text-red-300"}>{eur(e.eur)}</span>}
            </li>
          ))}
        </ul>
      ) : todo.length === 0 && <p className="text-caption text-ink-mist">Пока тихо — {data.name} начнёт работу перед закрытием окна.</p>}
    </section>
  );
}

// --- «Аналитик»: the finance review ----------------------------------------------------------------

function AnalystReview() {
  const { data } = useQuery({ queryKey: ["manager", "decisions"], queryFn: fetchManagerDecisions });
  if (!data?.review) return null;
  return <FinanceReview review={data.review} />;
}

// --- «Спортивный директор» ---------------------------------------------------------------------------

function DirectorPanel({ data, onError }: { data: ManagerStaffView; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const hired = data.staff.some((s) => s.role === "director");
  const { data: dir } = useQuery({ queryKey: ["manager", "director"], queryFn: fetchManagerDirector, enabled: hired });
  const [ask, setAsk] = useState<{ o: ManagerDirectorOption; kind: "loan" | "buy" } | null>(null);
  const budget = useMutation({
    mutationFn: setManagerDirectorBudget,
    onSuccess: (v) => { hapticSelection(); queryClient.setQueryData(["manager", "director"], v); },
    onError,
  });
  const sign = useMutation({
    mutationFn: ({ o, kind }: { o: ManagerDirectorOption; kind: "loan" | "buy" }) => signManagerNpc(o.player_id, kind),
    onSuccess: (v) => {
      hapticNotify("success");
      queryClient.setQueryData(["manager"], v);
      void queryClient.invalidateQueries({ queryKey: ["manager", "director"] });
      void queryClient.invalidateQueries({ queryKey: ["manager", "summary"] });
    },
    onError,
  });
  if (!hired) {
    return (
      <section className="rounded-2xl bg-bg-surface p-4 text-caption text-ink-mist" data-focus="director">
        🧭 <b className="text-ink-chalk">Спортивный директор</b> подберёт замены на пустые места и уходящих игроков в рамках твоего бюджета. Назначь жителя на эту должность выше.
      </section>
    );
  }
  if (!dir) return <ListSkeleton />;
  const steps = [8, 4, 2, 1].map((d) => Math.round(dir.grant / d));
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-gradient-to-br from-teal-500/15 to-bg-surface p-4 ring-1 ring-teal-300/25" data-testid="director-panel" data-focus="director">
      <div className="flex items-center gap-2.5">
        {dir.image ? <img src={staticUrl(dir.image)} alt="" className="h-11 w-11 rounded-xl object-cover" /> : <span className="text-3xl">{dir.icon}</span>}
        <span className="min-w-0 flex-1">
          <span className="block text-sm font-bold text-ink-chalk">🧭 {dir.name}</span>
          <span className={`block text-micro font-semibold ${RARITY[dir.rarity].text}`}>{RARITY[dir.rarity].label} · {dir.count} вар. на место</span>
        </span>
      </div>
      <div>
        <p className="mb-1 text-micro text-ink-mist">Бюджет на одну замену: <b className="text-ink-chalk">{eur(dir.budget)}</b></p>
        <div className="grid grid-cols-4 gap-1.5">
          {steps.map((v) => (
            <button key={v} disabled={budget.isPending} onClick={() => budget.mutate(v)}
              className={`rounded-lg py-1.5 text-[10px] font-bold ${v === dir.budget ? "bg-teal-300 text-bg-base" : "bg-bg-raised text-ink-mist"}`}>{eur(v)}</button>
          ))}
        </div>
      </div>
      {!dir.window && <p className="text-micro text-amber-200">⏳ Подписать — в трансферное окно. Пока директор только присматривает.</p>}
      {dir.needs.length === 0 && <p className="text-caption text-ink-mist">Состав укомплектован — замены не нужны.</p>}
      {dir.needs.map((n) => (
        <div key={n.title} className="flex flex-col gap-1.5 rounded-xl bg-black/20 p-2.5">
          <p className="text-xs font-bold text-ink-chalk">{n.why === "empty" ? "🕳" : "👋"} {n.title}</p>
          {n.options.length === 0 && <p className="text-micro text-ink-mist">В этот бюджет никого — подними его.</p>}
          {n.options.map((o) => (
            <div key={o.player_id} className="flex items-center gap-2 rounded-lg bg-bg-raised px-2 py-1.5">
              <span className="w-7 shrink-0 text-center font-mono text-sm font-black text-amber-200">{o.rating}</span>
              <span className="min-w-0 flex-1">
                <span className="block truncate text-xs font-semibold text-ink-chalk">{o.name}</span>
                <span className="block truncate text-[10px] text-ink-mist">{o.position}{o.fits ? " · своя позиция" : ""}{o.club ? ` · ${o.club}` : ""}</span>
              </span>
              {o.can_loan && (
                <button disabled={!dir.window || sign.isPending} onClick={() => setAsk({ o, kind: "loan" })}
                  className="shrink-0 rounded-lg bg-teal-300/20 px-2 py-1 text-[10px] font-bold text-teal-100 disabled:opacity-40">Аренда {eur(o.loan_fee)}</button>
              )}
              {o.can_buy && (
                <button disabled={!dir.window || sign.isPending} onClick={() => setAsk({ o, kind: "buy" })}
                  className="shrink-0 rounded-lg bg-amber-300/20 px-2 py-1 text-[10px] font-bold text-amber-100 disabled:opacity-40">Купить {eur(o.value)}</button>
              )}
            </div>
          ))}
        </div>
      ))}
      <ConfirmDialog open={!!ask} title={ask ? `${ask.kind === "loan" ? "Арендовать" : "Купить"} ${ask.o.name}?` : ""}
        description={ask ? `${ask.kind === "loan" ? `Аренда ${eur(ask.o.loan_fee)}` : `Трансфер ${eur(ask.o.value)}`}, зарплата ${eur(ask.o.wage_now)} за сезон.` : undefined}
        confirmLabel="Подписать" onConfirm={() => { if (ask) sign.mutate(ask); setAsk(null); }} onCancel={() => setAsk(null)} />
    </section>
  );
}

/** A VIP at their own desk by the trophy cabinets of the boardroom: the assistant at the laptop on the left, the analyst at the monitors on the right. */
function VipCorner({ vip, on, onPick }: { vip: ManagerVip; on: boolean; onPick: () => void }) {
  const left = vip.role === "assistant";
  return (
    <button onClick={onPick} data-testid={`corner-${vip.role}`}
      className="absolute -translate-x-1/2 -translate-y-1/2 text-center active:scale-95" style={{ left: left ? "12%" : "89%", top: left ? "22%" : "29%", width: "16%" }}>
      <span className={`relative mx-auto block aspect-square w-[78%] overflow-hidden rounded-2xl ring-2 ${on ? "ring-amber-300 shadow-[0_0_20px_-2px_rgba(251,191,36,0.95)]" : vip.active ? "ring-violet-300 shadow-[0_0_18px_-2px_rgba(167,139,250,0.9)]" : "ring-white/20"}`}>
        <StaffPortrait role={vip.role} art={vip.skin?.art} code={vip.skin?.code} size={56} className={vip.active ? "" : "opacity-60 grayscale-[45%]"} />
        {!vip.active && <span className="absolute inset-x-0 bottom-0 bg-black/70 text-[8px] font-black uppercase text-amber-200">{vip.trial ? "неделя 0 ⭐" : "нанять"}</span>}
      </span>
      <span className="mt-0.5 block truncate rounded-full bg-violet-950/80 px-1 text-[9px] font-bold leading-tight text-violet-100">{vip.name}</span>
    </button>
  );
}

function VipDetails({ vip, data, busy, itemBusy, onStars, onTrial, onDone, onError, onItem }: {
  vip: ManagerVip; data: ManagerStaffView; busy: boolean; itemBusy: boolean; onStars: () => void; onTrial: () => void;
  onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void; onItem: (i: ManagerStaffItem) => void;
}) {
  const [name, setName] = useState(vip.name);
  const rename = useMutation({ mutationFn: () => renameManagerVip(vip.role, name), onSuccess: onDone, onError });
  const skins = data.items.filter((i) => i.kind === "skin" && i.role === vip.role);
  const skills = vip.role === "assistant"
    ? ["Подпишет спонсора и спонсора формы, если забыл", "Займёт пустые места арендой в пределах лимита", "Продлит нужных игроков по твоим правилам",
      "Отклонит дешёвые предложения за твоих игроков", "Ответит на события и пресс-конференции, если ты не успел", "Поставит установку на матч"]
    : ["Разбор соперника по линиям, форма, травмы", "Совет на тур: установка и стиль против соперника", "Оценка сделки до отправки",
      "Разбор прошлого матча", "Прогноз места в сезоне", "Алерты по курсу твоих акций"];
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="vip-details">
      <div className="flex items-start gap-3">
        <StaffPortrait role={vip.role} art={vip.skin?.art} code={vip.skin?.code} size={64} />
        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-bold text-ink-chalk">{vip.emoji} {vip.title}</p>
          <p className="text-micro text-ink-mist">{vip.about}</p>
          {vip.active && vip.until && <p className="mt-1 inline-block rounded-full bg-accent-lime/15 px-2 py-0.5 text-[10px] font-bold text-accent-lime">работает до {until(vip.until)}</p>}
        </div>
      </div>
      <ul className="grid grid-cols-1 gap-1 text-caption text-ink-chalk">
        {skills.map((t) => <li key={t} className="flex gap-1.5"><span className="text-accent-lime">✓</span>{t}</li>)}
      </ul>
      <div className="flex gap-2">
        {vip.trial && !vip.active && (
          <button disabled={busy} onClick={onTrial} className="flex-1 rounded-xl bg-accent-lime py-2.5 text-sm font-bold text-bg-base" data-testid="assistant-trial">
            Неделя бесплатно
          </button>
        )}
        {vip.stars > 0 && (
          <button disabled={busy} onClick={onStars} className="flex-1 rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base">
            {vip.active ? "Продлить" : "Нанять"} · {vip.days} дн. · {vip.stars} ⭐
          </button>
        )}
      </div>
      <div className="flex gap-2">
        <input value={name} maxLength={20} onChange={(e) => setName(e.target.value)} aria-label="Имя"
          className="min-w-0 flex-1 rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none ring-1 ring-white/10 focus:ring-violet-300" />
        <button disabled={rename.isPending || name.trim() === vip.name || name.trim().length < 2} onClick={() => rename.mutate()}
          className="shrink-0 rounded-xl bg-bg-raised px-3 py-2 text-xs font-bold text-ink-chalk ring-1 ring-white/10 disabled:opacity-40">Переименовать</button>
      </div>
      <p className="text-micro font-bold uppercase tracking-wide text-ink-mist">Образ</p>
      <div className="grid grid-cols-3 gap-2" data-testid="vip-skins">
        {skins.map((s) => {
          const on = vip.skin?.code === s.code;
          return (
            <button key={s.code} disabled={itemBusy || on} onClick={() => onItem(s)}
              className={`flex flex-col items-center rounded-xl p-1.5 text-center ${on ? "bg-violet-400/15 ring-2 ring-violet-300" : "bg-bg-raised ring-1 ring-white/5"}`}>
              <StaffPortrait role={vip.role} art={s.art} code={s.code} size={58} />
              <span className="mt-0.5 line-clamp-1 text-[10px] font-bold text-ink-chalk">{s.name}</span>
              <span className="text-[10px] font-semibold text-ink-mist">{on ? "надет" : s.owned ? "надеть" : s.stars > 0 ? `${s.stars} ⭐` : `${s.coins} 🪙`}</span>
            </button>
          );
        })}
      </div>
      {vip.role === "assistant" && vip.active && <AssistantRules onDone={onDone} onError={onError} />}
    </section>
  );
}

const STYLE_LABEL = { safe: "Осторожно", balanced: "Взвешенно", bold: "Смело", off: "Не трогать" } as const;
const PLAN_LABEL = { auto: "По совету аналитика", normal: "Обычная игра", off: "Не трогать" } as const;

function AssistantRules({ onDone, onError }: { onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void }) {
  const { data } = useQuery({ queryKey: ["manager", "assistant"], queryFn: fetchManagerAssistant });
  const save = useMutation({ mutationFn: (r: Partial<ManagerAssistantRules>) => setManagerAssistantRules(r), onSuccess: onDone, onError });
  if (!data) return null;
  const r = data.rules;
  const toggle = (key: "sponsor" | "kit" | "fill", label: string) => (
    <button key={key} onClick={() => save.mutate({ [key]: !r[key] })} disabled={save.isPending}
      className={`rounded-xl px-2 py-2 text-micro font-bold ${r[key] ? "bg-accent-lime/15 text-accent-lime ring-1 ring-accent-lime/40" : "bg-bg-raised text-ink-mist"}`}>
      {r[key] ? "✓" : "○"} {label}
    </button>
  );
  return (
    <div className="flex flex-col gap-2.5 rounded-xl bg-black/20 p-3" data-testid="assistant-rules">
      <p className="text-micro font-bold uppercase tracking-wide text-violet-200">Правила помощника</p>
      <div className="grid grid-cols-2 gap-1.5" data-testid="assistant-mode">
        {([["act", "⚙️ Действует сама", "делает по правилам"], ["advise", "🗒 Только советует", "решаешь ты — бонус за ручное управление"]] as const).map(([m, label, hint]) => (
          <button key={m} disabled={save.isPending} onClick={() => m !== r.mode && save.mutate({ mode: m })}
            className={`rounded-xl px-2 py-2 text-left ${r.mode === m ? "bg-violet-400/20 ring-1 ring-violet-300" : "bg-bg-raised"}`}>
            <span className={`block text-micro font-bold ${r.mode === m ? "text-violet-100" : "text-ink-mist"}`}>{label}</span>
            <span className="block text-[10px] leading-tight text-ink-mist">{hint}</span>
          </button>
        ))}
      </div>
      <div className="grid grid-cols-3 gap-1.5">
        {toggle("sponsor", "Спонсор")}{toggle("kit", "Форма")}{toggle("fill", "Пустые места")}
      </div>
      <Row label="Лимит трат за окно" value={eur(r.limit)}>
        {[0.5, 1, 2].map((k) => {
          const v = Math.round((r.limit || 1) * k);
          return k === 1 ? null : (
            <button key={k} onClick={() => save.mutate({ limit: v })} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk">{k < 1 ? "−" : "+"}</button>
          );
        })}
      </Row>
      <Scale label="из них на трансферы" value={r.transfer_limit} cap={r.limit} onSet={(v) => save.mutate({ transfer_limit: v })} />
      <Scale label="из них на продления" value={r.renew_limit} cap={r.limit} onSet={(v) => save.mutate({ renew_limit: v })} />
      <Scale label="Не продавать дешевле" value={r.min_sale} cap={r.limit * 4} zero="любая цена" onSet={(v) => save.mutate({ min_sale: v })} />
      <Row label="Продлевать от рейтинга" value={String(r.renew_min_rating)}>
        <button onClick={() => save.mutate({ renew_min_rating: Math.max(0, r.renew_min_rating - 5) })} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk">−</button>
        <button onClick={() => save.mutate({ renew_min_rating: Math.min(99, r.renew_min_rating + 5) })} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk">+</button>
      </Row>
      <Row label="Отклонять ставки ниже" value={`${r.decline_below_pct}% цены`}>
        <button onClick={() => save.mutate({ decline_below_pct: Math.max(0, r.decline_below_pct - 10) })} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk">−</button>
        <button onClick={() => save.mutate({ decline_below_pct: Math.min(300, r.decline_below_pct + 10) })} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk">+</button>
      </Row>
      <Choice label="События и пресса" value={r.events} options={STYLE_LABEL} onPick={(v) => save.mutate({ events: v })} />
      <Choice label="Установка на матч" value={r.plan} options={PLAN_LABEL} onPick={(v) => save.mutate({ plan: v })} />
      {data.squad.length > 0 && (
        <div className="flex flex-col gap-1" data-testid="assistant-keep">
          <span className="text-micro text-ink-mist">⭐ Неприкасаемые — не продаёт, всегда продлевает ({r.keep.length}/{KEEP_MAX})</span>
          <div className="flex flex-wrap gap-1">
            {data.squad.map((p) => {
              const on = r.keep.includes(p.key);
              return (
                <button key={p.key} disabled={save.isPending || (!on && r.keep.length >= KEEP_MAX)}
                  onClick={() => save.mutate({ keep: on ? r.keep.filter((k) => k !== p.key) : [...r.keep, p.key] })}
                  className={`rounded-full px-2 py-1 text-[10px] font-bold ${on ? "bg-amber-300/20 text-amber-100 ring-1 ring-amber-300/60" : "bg-bg-raised text-ink-mist"} disabled:opacity-40`}>
                  {on ? "⭐ " : ""}{p.name}{p.rating ? ` ${p.rating}` : ""}
                </button>
              );
            })}
          </div>
        </div>
      )}
    </div>
  );
}

const KEEP_MAX = 11;

/** A money rule stepped by halves and doubles (0 = off), within `cap`. */
function Scale({ label, value, cap, zero, onSet }: { label: string; value: number; cap: number; zero?: string; onSet: (v: number) => void }) {
  const unit = Math.max(1, Math.round(cap / 8));
  const down = value <= unit ? 0 : Math.round(value / 2);
  const up = Math.min(cap, value === 0 ? unit : value * 2);
  return (
    <Row label={label} value={value === 0 && zero ? zero : eur(value)}>
      <button disabled={value === 0} onClick={() => onSet(down)} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk disabled:opacity-40">−</button>
      <button disabled={value >= cap} onClick={() => onSet(up)} className="rounded-lg bg-bg-raised px-2 py-1 text-micro font-bold text-ink-chalk disabled:opacity-40">+</button>
    </Row>
  );
}

function Row({ label, value, children }: { label: string; value: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center gap-2 text-xs">
      <span className="min-w-0 flex-1 text-ink-mist">{label}</span>
      <span className="font-mono font-bold text-ink-chalk">{value}</span>
      <span className="flex gap-1">{children}</span>
    </div>
  );
}

function Choice<T extends string>({ label, value, options, onPick }: { label: string; value: T; options: Record<T, string>; onPick: (v: T) => void }) {
  const keys = Object.keys(options) as T[];
  return (
    <div className="flex flex-col gap-1">
      <span className="text-micro text-ink-mist">{label}</span>
      <div className={`grid gap-1 ${keys.length === 4 ? "grid-cols-4" : "grid-cols-3"}`}>
        {keys.map((k) => (
          <button key={k} onClick={() => k !== value && onPick(k)}
            className={`rounded-lg px-1 py-1.5 text-[10px] font-bold leading-tight ${k === value ? "bg-violet-400/20 text-violet-100 ring-1 ring-violet-300" : "bg-bg-raised text-ink-mist"}`}>
            {options[k]}
          </button>
        ))}
      </div>
    </div>
  );
}

// --- the president's car and office --------------------------------------------------------------

function Status({ data, onItem, busy }: { data: ManagerStaffView; onItem: (i: ManagerStaffItem) => void; busy: boolean }) {
  const price = (i: ManagerStaffItem) => (i.owned ? "есть" : i.stars > 0 ? `${i.stars} ⭐` : `${i.coins.toLocaleString("ru-RU")} 🪙`);
  const grid = (kind: "car" | "room") => (
    <div className="grid grid-cols-2 gap-2">
      {data.items.filter((i) => i.kind === kind).map((i) => {
        const on = data.worn[kind]?.code === i.code;
        return (
          <button key={i.code} disabled={busy || on} onClick={() => onItem(i)}
            className={`flex flex-col items-center gap-1 overflow-hidden rounded-xl p-2 text-center ${on ? "bg-amber-300/10 ring-2 ring-amber-300" : "bg-bg-raised ring-1 ring-white/5"}`}>
            {kind === "car"
              ? <span className="flex h-[72px] items-end"><CarArt art={i.art} code={i.code} width={108} /></span>
              : <OfficeScene room={i.art} code={i.code} className="h-[72px] w-full rounded-lg" />}
            <span className="line-clamp-1 text-[11px] font-bold text-ink-chalk">{i.name}</span>
            <span className={`text-[10px] font-semibold ${on ? "text-amber-200" : "text-ink-mist"}`}>{on ? "выбрано" : price(i)}</span>
          </button>
        );
      })}
    </div>
  );
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="president-status">
      <h2 className="font-display text-base font-bold text-ink-chalk">🚘 Гараж</h2>
      {grid("car")}
      <h2 className="mt-1 font-display text-base font-bold text-ink-chalk">🛋 Кабинет</h2>
      {grid("room")}
    </section>
  );
}
