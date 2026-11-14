import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";

import {
  fetchManagerOffice,
  repayManagerLoan,
  signManagerDeal,
  takeManagerLoan,
  type ManagerDealKind,
  type ManagerOffice,
  type ManagerReportSeason,
  type ManagerSponsorOffer,
  type ManagerTodayTab,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import { KitShirt } from "@/components/manager/Emblem";
import ExchangePanel from "@/components/manager/ExchangePanel";
import MatchdayPanel from "@/components/manager/MatchdayPanel";
import { AwayReport, DeskOverlay, Diary } from "@/components/manager/OfficeDesk";
import { useOfficeStaff } from "@/components/manager/useOfficeStaff";
import OfficeScene from "@/components/manager/OfficeScene";
import PresidentRating from "@/components/manager/PresidentRating";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";

type Section = "report" | "sponsor" | "bank" | "deals" | "matchday" | "exchange" | "rating";

/** ISO week key "2026-W45" → "неделя 45". */
function weekOf(key: string): string {
  return `неделя ${Number(key.split("-W")[1] ?? 0)}`;
}

/** "2026-W45" → "сезон недели 45". */
function seasonOf(key: string): string {
  return `сезон недели ${Number(key.split("-W")[1] ?? 0)}`;
}

const pct = (n: number) => `${Number.isInteger(n) ? n : n.toFixed(1).replace(".", ",")}%`;

/** «💼 Кабинет президента» of «Менеджер»: the club's value, the income and
 * expense report by seasons, the season sponsor, the bank and financial deals
 * for the coming season. Club euros only — they never become coins. */
export default function PresidentTab({ onError, onTab = () => {} }: { onError: (e: unknown) => void; onTab?: (t: ManagerTodayTab) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "office"], queryFn: fetchManagerOffice });
  const [section, setSection] = useState<Section>("report");
  const [confirm, setConfirm] = useState<{ title: string; text: string; run: () => void } | null>(null);
  const done = (office: ManagerOffice) => {
    hapticNotify("success");
    queryClient.setQueryData(["manager", "office"], office);
    void queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
  };
  const deal = useMutation({
    mutationFn: ({ kind, ...body }: { kind: ManagerDealKind; option?: string; seasons?: number; amount?: number }) => signManagerDeal(kind, body),
    onSuccess: done, onError,
  });
  if (!data) return <ListSkeleton />;
  const ask = (title: string, text: string, run: () => void) => setConfirm({ title, text, run });
  const sections: [Section, string, string][] = [
    ["report", "📊", "Отчёт"], ["sponsor", "🤝", "Спонсор"], ["bank", "🏦", "Банк"], ["deals", "💼", "Сделки"],
    ["matchday", "🏟️", "Матчдей"], ["exchange", "📈", "Биржа"], ["rating", "🏆", "Рейтинг"],
  ];
  return (
    <div className="flex flex-col gap-4" data-testid="president-tab">
      <OfficeHero office={data} onTab={onTab} />
      <AwayReport onTab={onTab} />
      <Diary onTab={onTab} />
      <div className="grid grid-cols-4 gap-1.5">
        {sections.map(([id, icon, label]) => (
          <button key={id} onClick={() => setSection(id)}
            className={`flex flex-col items-center gap-0.5 rounded-2xl py-2 text-micro font-bold transition ${section === id
              ? "bg-gradient-to-b from-amber-300 to-amber-500 text-bg-base shadow-[0_6px_18px_-6px_rgba(251,191,36,0.8)]"
              : "bg-bg-surface text-ink-mist"}`}>
            <span className="text-lg leading-none">{icon}</span>{label}
          </button>
        ))}
      </div>
      {!data.window_open && !["report", "exchange", "rating"].includes(section) && (
        <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-caption text-amber-200">
          ⏳ Идёт сезон. Новые сделки и кредит — в межсезонье, на следующий сезон. Погасить кредит можно в любой момент.
        </p>
      )}
      {section === "report" && <Report office={data} />}
      {section === "sponsor" && <Sponsors office={data} busy={deal.isPending}
        onSign={(s) => ask(`Подписать «${s.brand}»?`, "Спонсор — один на сезон, контракт не расторгается.", () => deal.mutate({ kind: "sponsor", option: s.code }))} />}
      {section === "bank" && <Bank office={data} onDone={done} onError={onError} ask={ask} />}
      {section === "exchange" && <ExchangePanel onError={onError} />}
      {section === "matchday" && <MatchdayPanel office={data} onDone={done} onError={onError} busy={deal.isPending}
        onInsure={() => ask("Застраховать игроков?", `${eur(data.offers.insurance.premium)} за сезон — страховка оплатит ${pct(data.offers.insurance.cover_pct)} лечения травм.`,
          () => deal.mutate({ kind: "insurance" }))} />}
      {section === "rating" && <PresidentRating />}
      {section === "deals" && <Deals office={data} busy={deal.isPending} ask={ask} sign={(kind, body) => deal.mutate({ kind, ...body })} />}
      <ConfirmDialog
        open={!!confirm} title={confirm?.title ?? ""} description={confirm?.text} confirmLabel="Подписать"
        onConfirm={() => { confirm?.run(); setConfirm(null); }} onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

// --- hero ---------------------------------------------------------------------------------------

const VALUE_PARTS: { key: keyof ManagerOffice["value"]["parts"]; label: string; color: string }[] = [
  { key: "squad", label: "Состав", color: "bg-emerald-400" },
  { key: "budget", label: "Бюджет", color: "bg-amber-300" },
  { key: "invested", label: "Вложения", color: "bg-sky-400" },
  { key: "base", label: "База", color: "bg-violet-400" },
  { key: "fans", label: "Фанаты", color: "bg-pink-400" },
  { key: "titles", label: "Трофеи", color: "bg-yellow-200" },
];

function OfficeHero({ office, onTab }: { office: ManagerOffice; onTab: (t: ManagerTodayTab) => void }) {
  const { staff } = useOfficeStaff();
  const parts = office.value.parts;
  const positive = VALUE_PARTS.filter((p) => parts[p.key] > 0);
  const sum = positive.reduce((s, p) => s + parts[p.key], 0) || 1;
  const last = office.report[0];
  return (
    <section className="relative overflow-hidden rounded-3xl ring-1 ring-amber-300/30" data-testid="office-hero">
      <div className="relative h-[200px]">
        <OfficeScene room={staff?.worn.room?.art} code={staff?.worn.room?.code} className="absolute inset-0 h-full w-full" />
        <div className="absolute inset-0 bg-gradient-to-r from-black/75 via-black/30 to-transparent" />
        <div className="relative p-4">
          <p className="text-micro font-bold uppercase tracking-[0.2em] text-amber-300">💼 Кабинет президента</p>
          <p className="mt-1 max-w-[55%] truncate font-display text-base font-bold text-ink-chalk">{office.name}</p>
          {staff?.worn.room && <p className="max-w-[55%] truncate text-[10px] text-ink-mist">{staff.worn.room.name}</p>}
        </div>
        <DeskOverlay onTab={onTab} />
      </div>
      <div className="relative bg-gradient-to-br from-[#2a1d05] via-[#14261d] to-[#0b1f2e] p-4 pt-3">
      <p className="relative text-micro uppercase tracking-wide text-ink-mist">Стоимость клуба</p>
      <p className="relative font-display text-3xl font-black leading-none text-transparent [text-shadow:none] bg-clip-text bg-gradient-to-r from-amber-200 via-yellow-300 to-amber-500">
        {eur(office.value.total)}
      </p>
      <div className="relative mt-3 flex h-2.5 overflow-hidden rounded-full bg-white/10">
        {positive.map((p) => <span key={p.key} className={p.color} style={{ width: `${(parts[p.key] / sum) * 100}%` }} />)}
      </div>
      <div className="relative mt-2 flex flex-wrap gap-x-3 gap-y-1 text-micro text-ink-mist">
        {positive.map((p) => (
          <span key={p.key} className="inline-flex items-center gap-1"><i className={`h-2 w-2 rounded-full ${p.color}`} />{p.label} {eur(parts[p.key])}</span>
        ))}
        {parts.debt < 0 && <span className="inline-flex items-center gap-1 text-red-300"><i className="h-2 w-2 rounded-full bg-red-400" />Долг {eur(parts.debt)}</span>}
      </div>
      <div className="relative mt-3 grid grid-cols-3 gap-2 text-center">
        <Chip label="бюджет" value={eur(office.budget)} tone="text-accent-lime" />
        <Chip label={last ? `итог · ${weekOf(last.key)}` : "итог сезона"} value={last ? eur(last.profit) : "—"}
          tone={!last ? "text-ink-mist" : last.profit >= 0 ? "text-emerald-300" : "text-red-300"} />
        <Chip label="фанаты" value={office.fans.toLocaleString("ru-RU")} tone="text-pink-300" />
      </div>
      </div>
    </section>
  );
}

function Chip({ label, value, tone }: { label: string; value: ReactNode; tone: string }) {
  return (
    <span className="rounded-xl bg-black/30 px-1.5 py-2 ring-1 ring-white/5">
      <span className={`block whitespace-nowrap font-display text-sm font-bold ${tone}`}>{value}</span>
      <span className="block truncate text-micro text-ink-mist">{label}</span>
    </span>
  );
}

// --- report -------------------------------------------------------------------------------------

function Report({ office }: { office: ManagerOffice }) {
  const seasons = [...office.report].reverse();
  const [key, setKey] = useState<string | null>(office.report[0]?.key ?? null);
  useEffect(() => { if (!key && office.report[0]) setKey(office.report[0].key); }, [office.report, key]);
  if (seasons.length === 0) {
    return <Card><p className="text-caption text-ink-mist">Отчёт появится с первыми деньгами клуба: грант, матчи, трансферы — всё попадёт сюда.</p></Card>;
  }
  const top = Math.max(1, ...seasons.map((s) => Math.max(s.income, -s.expense)));
  const chosen = office.report.find((s) => s.key === key) ?? office.report[0];
  return (
    <div className="flex flex-col gap-3">
      <Card title="📊 Доходы и расходы по сезонам">
        <div className="flex h-36 items-end gap-2" data-testid="report-chart">
          {seasons.map((s) => (
            <button key={s.key} onClick={() => setKey(s.key)}
              className={`flex h-full min-w-0 flex-1 flex-col items-center justify-end gap-1 rounded-xl px-1 pb-1 ${s.key === chosen.key ? "bg-white/10 ring-1 ring-amber-300/50" : ""}`}>
              <span className="flex h-full w-full items-end justify-center gap-0.5">
                <i className="w-1/2 max-w-3 rounded-t bg-gradient-to-t from-emerald-600 to-emerald-300" style={{ height: `${Math.max(4, (s.income / top) * 100)}%` }} />
                <i className="w-1/2 max-w-3 rounded-t bg-gradient-to-t from-red-600 to-rose-300" style={{ height: `${Math.max(4, (-s.expense / top) * 100)}%` }} />
              </span>
              <span className={`text-micro font-bold ${s.profit >= 0 ? "text-emerald-300" : "text-red-300"}`}>{s.profit >= 0 ? "+" : ""}{eur(s.profit)}</span>
              <span className="text-micro text-ink-mist">{Number(s.key.split("-W")[1])} н.</span>
            </button>
          ))}
        </div>
        <p className="mt-2 flex gap-3 text-micro text-ink-mist">
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-sm bg-emerald-400" />доходы</span>
          <span className="inline-flex items-center gap-1"><i className="h-2 w-2 rounded-sm bg-rose-400" />расходы</span>
          <span>· сезон = неделя</span>
        </p>
      </Card>
      <SeasonLines season={chosen} current={chosen.key === office.current_key} />
    </div>
  );
}

function SeasonLines({ season, current }: { season: ManagerReportSeason; current: boolean }) {
  const groups: [ManagerReportSeason["lines"][number]["group"], string][] = [["income", "Доходы"], ["expense", "Расходы"], ["finance", "Финансирование"]];
  return (
    <Card title={`🧾 Сезон · ${weekOf(season.key)}${current ? " (текущий)" : ""}`}>
      <div className="grid grid-cols-3 gap-2 text-center">
        <Chip label="доходы" value={eur(season.income)} tone="text-emerald-300" />
        <Chip label="расходы" value={eur(season.expense)} tone="text-red-300" />
        <Chip label="прибыль" value={eur(season.profit)} tone={season.profit >= 0 ? "text-amber-200" : "text-red-300"} />
      </div>
      {groups.map(([group, title]) => {
        const lines = season.lines.filter((l) => l.group === group);
        if (lines.length === 0) return null;
        return (
          <div key={group} className="mt-3">
            <p className="mb-1 text-micro font-bold uppercase tracking-wide text-ink-mist">{title}</p>
            {lines.map((l) => (
              <p key={l.kind} className="flex items-center justify-between border-b border-white/5 py-1.5 text-xs">
                <span className="text-ink-chalk">{l.label}</span>
                <b className={l.amount >= 0 ? "text-emerald-300" : "text-red-300"}>{l.amount >= 0 ? "+" : ""}{eur(l.amount)}</b>
              </p>
            ))}
          </div>
        );
      })}
    </Card>
  );
}

// --- sponsor ------------------------------------------------------------------------------------

const SPONSOR_TONES: Record<string, string> = {
  safe: "from-sky-500/30 via-sky-900/30 ring-sky-300/50",
  bonus: "from-emerald-500/30 via-emerald-900/30 ring-emerald-300/50",
  ambitious: "from-fuchsia-500/30 via-violet-900/30 ring-fuchsia-300/50",
};

function Sponsors({ office, busy, onSign }: { office: ManagerOffice; busy: boolean; onSign: (s: ManagerSponsorOffer) => void }) {
  const signed = office.deals.find((d) => d.kind === "sponsor" && d.season_key === office.season_key);
  return (
    <div className="flex flex-col gap-3">
      <p className="px-1 text-caption text-ink-mist">
        Спонсор на {seasonOf(office.season_key)} — один из трёх. {office.sponsors.marketing_pct > 0
          ? <>📣 Отдел маркетинга (ур. {office.levels.marketing}) поднимает суммы на <b className="text-accent-lime">+{pct(office.sponsors.marketing_pct)}</b>.</>
          : <>📣 Отдел маркетинга в «Клубной базе» поднимет суммы.</>}
      </p>
      {office.sponsors.offers.map((s) => {
        const mine = signed?.option === s.code;
        return (
          <section key={s.code} className={`relative overflow-hidden rounded-3xl bg-gradient-to-br to-bg-surface p-4 ring-1 ${SPONSOR_TONES[s.code] ?? "from-amber-500/30 ring-amber-300/50"} ${signed && !mine ? "opacity-50" : ""}`}>
            {mine && <span className="absolute right-3 top-3 rotate-[-12deg] rounded-md border-2 border-emerald-300 px-2 py-0.5 font-display text-xs font-black text-emerald-300">ПОДПИСАН</span>}
            <div className="flex items-center gap-3">
              <span className="flex h-12 w-12 items-center justify-center rounded-2xl bg-black/30 text-2xl ring-1 ring-white/15">{s.emoji}</span>
              <span className="min-w-0">
                <span className="block text-micro font-bold uppercase tracking-wide text-ink-mist">{s.name}</span>
                <span className="block truncate font-display text-base font-bold text-ink-chalk">{s.brand}</span>
              </span>
            </div>
            <div className="mt-3 flex flex-col gap-1 text-xs">
              {s.upfront > 0 && <Term label="Сразу при подписании" value={eur(s.upfront)} strong />}
              {s.per_win > 0 && <Term label="За каждую победу" value={`+${eur(s.per_win)}`} />}
              {s.places.map((v, i) => v > 0 && <Term key={i} label={i === 0 ? "🏆 Чемпионство" : `${i + 1} место`} value={`+${eur(v)}`} strong={i === 0} />)}
              {s.rest > 0 && <Term label="Любое другое место" value={`+${eur(s.rest)}`} />}
              {s.places.length > 0 && <Term label="Вылет" value={s.relegated > 0 ? `+${eur(s.relegated)}` : "ничего"} />}
            </div>
            {!signed && (
              <button disabled={busy || !office.window_open} onClick={() => onSign(s)}
                className="mt-3 w-full rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 py-2.5 text-sm font-black text-bg-base disabled:opacity-40">
                ✍️ Подписать
              </button>
            )}
          </section>
        );
      })}
    </div>
  );
}

function Term({ label, value, strong }: { label: string; value: string; strong?: boolean }) {
  return (
    <p className="flex items-center justify-between rounded-lg bg-black/20 px-2.5 py-1.5">
      <span className="text-ink-mist">{label}</span>
      <b className={strong ? "text-amber-200" : "text-ink-chalk"}>{value}</b>
    </p>
  );
}

// --- bank ---------------------------------------------------------------------------------------

function Bank({ office, onDone, onError, ask }: {
  office: ManagerOffice; onDone: (o: ManagerOffice) => void; onError: (e: unknown) => void; ask: (t: string, x: string, run: () => void) => void;
}) {
  const bank = office.loan;
  const [amount, setAmount] = useState(Math.min(bank.limit, Math.max(bank.min, Math.round(bank.limit / 2 / 100_000) * 100_000)));
  const [seasons, setSeasons] = useState(1);
  const take = useMutation({ mutationFn: () => takeManagerLoan(amount, seasons), onSuccess: onDone, onError });
  const repay = useMutation({ mutationFn: (sum?: number) => repayManagerLoan(sum), onSuccess: onDone, onError });
  const due = Math.round(amount * Math.pow(1 + bank.rate_pct / 100, seasons));
  const loan = bank.open;
  return (
    <div className="flex flex-col gap-3">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-slate-700 via-slate-900 to-black p-4 ring-1 ring-white/15">
        <span className="absolute -right-8 -top-10 h-32 w-32 rounded-full bg-amber-300/20 blur-2xl" />
        <div className="relative flex items-center justify-between">
          <span className="font-display text-sm font-black tracking-wide text-ink-chalk">🏦 FOOTY BANK</span>
          <span className="h-7 w-10 rounded-md bg-gradient-to-br from-yellow-200 to-amber-500 ring-1 ring-black/30" />
        </div>
        <p className="relative mt-4 text-micro uppercase tracking-wide text-ink-mist">{loan ? "Долг клуба" : "Кредитный лимит"}</p>
        <p className={`relative font-display text-2xl font-black ${loan?.status === "overdue" ? "text-red-300" : "text-ink-chalk"}`}>{eur(loan ? loan.debt : bank.limit)}</p>
        <p className="relative mt-2 font-mono text-micro tracking-widest text-ink-mist">
          {loan ? `${pct(loan.rate_pct)} ЗА СЕЗОН · ОСТАЛОСЬ ${loan.seasons_left} СЕЗ.` : `СТАВКА ${pct(bank.rate_pct)} ЗА СЕЗОН`}
        </p>
        <p className="relative mt-1 text-micro text-ink-mist">
          {office.levels.accounting > 0 ? `🧮 Бухгалтерия ур. ${office.levels.accounting}: ставка ${pct(bank.rate_pct)} вместо ${pct(bank.base_rate_pct)}` : "🧮 Бухгалтерия в «Клубной базе» снизит ставку"}
        </p>
      </section>
      {loan ? (
        <Card title={loan.status === "overdue" ? "⚠️ Кредит просрочен" : "Кредит"}>
          {loan.status === "overdue" && (
            <p className="mb-2 rounded-xl bg-red-500/15 px-3 py-2 text-caption text-red-200">
              Банк начислил штраф {pct(bank.penalty_pct)}. Пока долг не погашен, трансферы закрыты.
            </p>
          )}
          <p className="text-caption text-ink-mist">
            Взято {eur(loan.principal)} на {loan.seasons_total} сез. Проценты начисляются в начале каждого сезона, в начале сезона после срока банк спишет весь долг.
            Погасить раньше — значит не платить следующие проценты.
          </p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <button disabled={repay.isPending || office.budget <= 0} onClick={() => repay.mutate(Math.min(office.budget, Math.ceil(loan.debt / 2)))}
              className="rounded-2xl bg-bg-raised py-2.5 text-xs font-bold text-ink-chalk disabled:opacity-40">Погасить {eur(Math.min(office.budget, Math.ceil(loan.debt / 2)))}</button>
            <button disabled={repay.isPending || office.budget < loan.debt} onClick={() => repay.mutate(undefined)}
              className="rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 py-2.5 text-xs font-black text-bg-base disabled:opacity-40">Погасить всё</button>
          </div>
        </Card>
      ) : (
        <Card title="Взять кредит">
          {bank.limit < bank.min ? (
            <p className="text-caption text-ink-mist">Банк пока не даёт кредит: лимит зависит от гранта дивизиона и стоимости клуба.</p>
          ) : (
            <>
              <div className="flex items-baseline justify-between">
                <span className="font-display text-xl font-black text-ink-chalk">{eur(amount)}</span>
                <span className="text-micro text-ink-mist">до {eur(bank.limit)}</span>
              </div>
              <input type="range" min={bank.min} max={bank.limit} step={Math.max(1, Math.round(bank.limit / 50))} value={amount}
                onChange={(e) => setAmount(Number(e.target.value))} className="mt-2 w-full accent-amber-400" aria-label="Сумма кредита" />
              <div className="mt-3 grid grid-cols-3 gap-1.5">
                {Array.from({ length: bank.seasons_max }, (_, i) => i + 1).map((n) => (
                  <button key={n} onClick={() => setSeasons(n)}
                    className={`rounded-xl py-2 text-xs font-bold ${seasons === n ? "bg-amber-300 text-bg-base" : "bg-bg-raised text-ink-mist"}`}>{n} сез.</button>
                ))}
              </div>
              <p className="mt-3 rounded-xl bg-black/20 px-3 py-2 text-caption text-ink-mist">
                Вернуть ≈ <b className="text-ink-chalk">{eur(due)}</b> в начале сезона после срока. Не хватит денег — штраф {pct(bank.penalty_pct)} и запрет трансферов.
              </p>
              <button disabled={take.isPending || !office.window_open}
                onClick={() => ask(`Кредит ${eur(amount)}?`, `Ставка ${pct(bank.rate_pct)} за сезон, срок ${seasons} сез. Вернуть ≈ ${eur(due)}.`, () => take.mutate())}
                className="mt-3 w-full rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 py-2.5 text-sm font-black text-bg-base disabled:opacity-40">
                Получить деньги
              </button>
            </>
          )}
        </Card>
      )}
    </div>
  );
}

// --- deals --------------------------------------------------------------------------------------

const DEALS: { kind: Exclude<ManagerDealKind, "sponsor">; emoji: string; title: string; tone: string; line: string }[] = [
  { kind: "kit", emoji: "👕", title: "Спонсор на форме", tone: "from-amber-400/40 to-orange-700/30", line: "Бренд на футболке за деньги каждый сезон" },
  { kind: "tour", emoji: "✈️", title: "Предсезонное турне", tone: "from-sky-400/40 to-indigo-700/30", line: "Деньги и фанаты, но усталость на старте" },
  { kind: "tv", emoji: "📺", title: "ТВ-права вперёд", tone: "from-rose-400/40 to-red-800/30", line: "Деньги за матчи сезона — сейчас, со скидкой" },
  { kind: "deposit", emoji: "🔐", title: "Депозит", tone: "from-emerald-400/40 to-teal-800/30", line: "Надёжный процент к концу сезона" },
  { kind: "venture", emoji: "🎲", title: "Венчурный фонд", tone: "from-fuchsia-400/40 to-purple-800/30", line: "Риск: умножить или потерять" },
  { kind: "farm", emoji: "🌱", title: "Фарм-клуб", tone: "from-lime-400/40 to-green-800/30", line: "Дешевле аренды, сильнее воспитанники" },
];

function Deals({ office, busy, ask, sign }: {
  office: ManagerOffice; busy: boolean; ask: (t: string, x: string, run: () => void) => void;
  sign: (kind: ManagerDealKind, body: { option?: string; seasons?: number; amount?: number }) => void;
}) {
  const [open, setOpen] = useState<ManagerDealKind | null>(null);
  const status = (kind: Exclude<ManagerDealKind, "sponsor">) => office.offers[kind].taken;
  const active = office.deals.filter((d) => d.status === "active" && d.kind !== "sponsor");
  return (
    <div className="flex flex-col gap-3">
      <p className="px-1 text-caption text-ink-mist">
        Сделки на {seasonOf(office.season_key)}: каждая — раз в сезон. Здания «Клубной базы» работают множителями.
      </p>
      <div className="grid grid-cols-2 gap-2">
        {DEALS.map((d) => (
          <button key={d.kind} onClick={() => setOpen(open === d.kind ? null : d.kind)}
            className={`relative flex min-h-[112px] flex-col items-start gap-1 overflow-hidden rounded-2xl bg-gradient-to-br ${d.tone} p-3 text-left ring-1 ${open === d.kind ? "ring-2 ring-amber-300" : "ring-white/10"}`}>
            <span className="absolute -right-2 -top-2 text-5xl opacity-30">{d.emoji}</span>
            <span className="text-2xl">{d.emoji}</span>
            <span className="font-display text-xs font-bold leading-tight text-ink-chalk">{d.title}</span>
            <span className="text-micro leading-tight text-ink-mist">{d.line}</span>
            {status(d.kind) && <span className="absolute right-2 top-2 rounded-full bg-emerald-400 px-1.5 py-0.5 text-micro font-black text-bg-base">✓</span>}
          </button>
        ))}
      </div>
      {open && open !== "sponsor" && (
        <DealPanel kind={open} office={office} busy={busy} ask={ask} sign={sign} />
      )}
      {active.length > 0 && (
        <Card title="📁 Действующие сделки">
          {active.map((d) => {
            const meta = DEALS.find((x) => x.kind === d.kind) ?? (d.kind === "insurance" ? { emoji: "🚑", title: "Страховка игроков" } : undefined);
            return (
              <p key={d.id} className="flex items-center justify-between border-b border-white/5 py-1.5 text-xs">
                <span className="text-ink-chalk">{meta?.emoji} {meta?.title}{d.option && d.kind !== "tour" ? ` · ${d.option}` : ""}</span>
                <span className="text-ink-mist">{weekOf(d.season_key)}{d.seasons > 1 ? ` +${d.seasons - 1}` : ""} · {eur(d.amount)}</span>
              </p>
            );
          })}
        </Card>
      )}
    </div>
  );
}

function DealPanel({ kind, office, busy, ask, sign }: {
  kind: Exclude<ManagerDealKind, "sponsor">; office: ManagerOffice; busy: boolean; ask: (t: string, x: string, run: () => void) => void;
  sign: (kind: ManagerDealKind, body: { option?: string; seasons?: number; amount?: number }) => void;
}) {
  const o = office.offers;
  const lv = office.levels;
  const [choice, setChoice] = useState<string | null>(null);
  const [seasons, setSeasons] = useState(1);
  const [amount, setAmount] = useState(0);
  useEffect(() => { setChoice(null); setSeasons(1); setAmount(0); }, [kind]);
  const locked = !office.window_open || busy || o[kind].taken;
  const button = (label: string, disabled: boolean, title: string, text: string, body: { option?: string; seasons?: number; amount?: number }) => (
    <button disabled={locked || disabled} onClick={() => ask(title, text, () => sign(kind, body))}
      className="mt-3 w-full rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 py-2.5 text-sm font-black text-bg-base disabled:opacity-40">
      {o[kind].taken ? "✓ Уже подписано на этот сезон" : label}
    </button>
  );
  const boost = (icon: string, text: string) => <p className="mt-2 rounded-xl bg-black/25 px-3 py-2 text-caption text-ink-mist">{icon} {text}</p>;

  if (kind === "kit") {
    const k = o.kit;
    const brand = choice ?? k.worn;
    return (
      <Card title="👕 Спонсор на форме">
        <div className="flex items-center gap-3 rounded-2xl bg-gradient-to-r from-amber-500/20 to-transparent p-3">
          <KitShirt look={office.look} size={72} sponsor={brand} />
          <p className="text-caption text-ink-mist">
            {k.worn ? <>На форме — <b className="text-amber-200">{k.worn}</b>.</> : "Бренд будет на футболке клуба: в «Моём клубе», в карточке для соперников и в «Стиле»."}
          </p>
        </div>
        <div className="mt-3 flex flex-wrap gap-1.5">
          {k.brands.map((b) => (
            <button key={b} onClick={() => setChoice(b)} disabled={k.taken}
              className={`rounded-full px-3 py-1.5 text-xs font-bold disabled:opacity-50 ${choice === b ? "bg-amber-300 text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>{b}</button>
          ))}
        </div>
        <div className="mt-3 grid grid-cols-3 gap-1.5">
          {k.prices.map((price, i) => (
            <button key={i} onClick={() => setSeasons(i + 1)}
              className={`rounded-xl py-2 text-center ${seasons === i + 1 ? "bg-amber-300 text-bg-base" : "bg-bg-raised text-ink-chalk"}`}>
              <span className="block text-xs font-black">{i + 1} сез.</span>
              <span className="block text-micro">{eur(price)}/сез.</span>
            </button>
          ))}
        </div>
        {boost("👕", k.shop > 0 ? `Клубный магазин ур. ${k.shop} поднимает цену. Длинный контракт дороже за сезон, цена заморожена.` : "Клубный магазин в «Клубной базе» поднимет цену")}
        {button(`Подписать за ${eur(k.prices[seasons - 1])}/сезон`, !choice, `${choice} на форме на ${seasons} сез.?`,
          "Первый сезон оплачивается сразу, следующие — в начале каждого сезона. Расторгнуть нельзя.", { option: choice ?? undefined, seasons })}
      </Card>
    );
  }
  if (kind === "tour") {
    const t = o.tour;
    const picked = t.options.find((x) => x.code === choice);
    return (
      <Card title="✈️ Предсезонное турне">
        <div className="flex flex-col gap-2">
          {t.options.map((x) => (
            <button key={x.code} onClick={() => setChoice(x.code)}
              className={`flex items-center gap-3 rounded-2xl p-3 text-left ${choice === x.code ? "bg-sky-400/20 ring-2 ring-sky-300" : "bg-bg-raised"}`}>
              <span className="text-3xl">{x.emoji}</span>
              <span className="min-w-0 flex-1">
                <span className="block text-sm font-bold text-ink-chalk">{x.name}</span>
                <span className="block text-micro text-ink-mist">+{x.fans} фанатов · усталость −{pct(x.fatigue_pct)} в {x.fatigue_rounds} турах</span>
              </span>
              <span className="text-right">
                <b className="block text-xs text-emerald-300">+{eur(x.revenue - x.cost)}</b>
                <span className="block text-micro text-ink-mist">{eur(x.revenue)} − {eur(x.cost)}</span>
              </span>
            </button>
          ))}
        </div>
        {boost("🏨", t.hotel_cut_pct > 0 ? `Клубный отель ур. ${lv.hotel}: расходы −${pct(t.hotel_cut_pct)}` : "Клубный отель удешевит турне")}
        {boost("🎥", t.media_fans_pct > 0 ? `Медиацентр ур. ${lv.media}: фанатов +${pct(t.media_fans_pct)}` : "Медиацентр приведёт больше фанатов")}
        {button("Отправиться в турне", !picked || office.free_budget < (picked?.cost ?? 0), `${picked?.name}?`,
          `Доход ${eur(picked?.revenue ?? 0)}, расходы ${eur(picked?.cost ?? 0)}. Первые ${picked?.fatigue_rounds} туров команда будет слабее на ${pct(picked?.fatigue_pct ?? 0)}.`,
          { option: choice ?? undefined })}
      </Card>
    );
  }
  if (kind === "tv") {
    const t = o.tv;
    return (
      <Card title="📺 ТВ-права вперёд">
        <div className="grid grid-cols-2 gap-2 text-center">
          <Chip label="ожидаемо за сезон" value={eur(t.estimate)} tone="text-ink-chalk" />
          <Chip label={`сейчас, скидка ${pct(t.discount_pct)}`} value={eur(t.advance)} tone="text-amber-200" />
        </div>
        <p className="mt-2 text-caption text-ink-mist">Деньги сразу, но весь сезон доход за матчи получает телеканал. Билеты остаются клубу.</p>
        {boost("🎥", lv.media > 0 ? `Медиацентр ур. ${lv.media} уменьшил скидку` : "Медиацентр уменьшит скидку")}
        {button(`Продать за ${eur(t.advance)}`, false, "Продать ТВ-права?", `Сейчас +${eur(t.advance)}, за матчи сезона клуб ничего не получит.`, {})}
      </Card>
    );
  }
  if (kind === "deposit" || kind === "venture") {
    const d = kind === "deposit" ? o.deposit : o.venture;
    const value = Math.min(d.max, Math.max(d.min, amount || d.min));
    const unavailable = d.max < d.min || (kind === "deposit" && o.deposit.blocked);
    return (
      <Card title={kind === "deposit" ? "🔐 Депозит на сезон" : "🎲 Венчурный фонд"}>
        {kind === "deposit" ? (
          <p className="text-caption text-ink-mist">Деньги уходят в банк до конца сезона и возвращаются с процентом <b className="text-emerald-300">{pct(o.deposit.rate_pct)}</b>.</p>
        ) : (
          <p className="text-caption text-ink-mist">В конце сезона: шанс <b className="text-fuchsia-300">{pct(o.venture.win_pct)}</b> получить <b className="text-fuchsia-300">×{o.venture.multiplier}</b>, иначе вложение сгорает. Не больше {pct(o.venture.max_pct)} бюджета.</p>
        )}
        {unavailable ? (
          <p className="mt-2 text-caption text-amber-200">{kind === "deposit" && o.deposit.blocked ? "Банк не открывает депозит, пока у клуба есть кредит." : `Нужно хотя бы ${eur(d.min)} доступных денег.`}</p>
        ) : (
          <>
            <div className="mt-3 flex items-baseline justify-between">
              <span className="font-display text-xl font-black text-ink-chalk">{eur(value)}</span>
              <span className="text-micro text-ink-mist">до {eur(d.max)}</span>
            </div>
            <input type="range" min={d.min} max={d.max} step={Math.max(1, Math.round(d.max / 50))} value={value}
              onChange={(e) => setAmount(Number(e.target.value))} className="mt-2 w-full accent-amber-400" aria-label="Сумма" />
            {kind === "deposit"
              ? <p className="mt-2 text-caption text-ink-mist">Вернётся ≈ <b className="text-emerald-300">{eur(Math.round(value * (1 + o.deposit.rate_pct / 100)))}</b></p>
              : <p className="mt-2 text-caption text-ink-mist">Удача: <b className="text-fuchsia-300">{eur(value * o.venture.multiplier)}</b> · неудача: 0</p>}
          </>
        )}
        {kind === "deposit" && boost("🧮", lv.accounting > 0 ? `Бухгалтерия ур. ${lv.accounting} подняла ставку` : "Бухгалтерия поднимет ставку")}
        {button(kind === "deposit" ? "Открыть депозит" : "Вложить", unavailable,
          kind === "deposit" ? `Депозит ${eur(value)}?` : `Вложить ${eur(value)} в фонд?`,
          kind === "deposit" ? "Деньги вернутся с процентами в конце сезона." : "Деньги могут сгореть. Результат — в конце сезона.", { amount: value })}
      </Card>
    );
  }
  const f = o.farm;
  return (
    <Card title="🌱 Фарм-клуб на сезон">
      <div className="grid grid-cols-3 gap-2 text-center">
        <Chip label="стоит" value={eur(f.fee)} tone="text-ink-chalk" />
        <Chip label="аренды" value={`−${pct(f.loan_cut_pct)}`} tone="text-emerald-300" />
        <Chip label="воспитанники" value={`+${f.kid_bonus}`} tone="text-lime-300" />
      </div>
      <p className="mt-2 text-caption text-ink-mist">Аренды футболистов на этот сезон дешевле, «ребята из академии» на пустых местах — сильнее.</p>
      {boost("🏋️", lv.training > 0 ? `Тренировочный центр ур. ${lv.training} усиливает воспитанников` : "Тренировочный центр усилит воспитанников")}
      {button(`Подписать за ${eur(f.fee)}`, office.free_budget < f.fee, "Фарм-клуб на сезон?", `Стоит ${eur(f.fee)}. Действует весь сезон.`, {})}
    </Card>
  );
}

function Card({ title, children }: { title?: string; children: ReactNode }) {
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      {title && <h2 className="mb-2 font-display text-base font-bold text-ink-chalk">{title}</h2>}
      {children}
    </section>
  );
}
