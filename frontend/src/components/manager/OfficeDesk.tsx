import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import {
  fetchManagerSummary,
  markManagerAssistantSeen,
  type ManagerAssistantOffice,
  type ManagerTodayTab,
} from "@/api/manager";
import { CarArt } from "@/components/manager/OfficeScene";
import StaffPortrait from "@/components/manager/StaffPortrait";
import { useOfficeStaff } from "@/components/manager/useOfficeStaff";
import { eur } from "@/lib/managerMoney";

function at(iso: string | null | undefined): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric" })}, ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function ago(iso: string): string {
  const min = Math.max(1, Math.round((Date.now() - new Date(iso).getTime()) / 60_000));
  if (min < 60) return `${min} мин назад`;
  if (min < 60 * 24) return `${Math.round(min / 60)} ч назад`;
  return `${Math.round(min / 60 / 24)} дн назад`;
}

/** The assistant at the desk with a speech bubble and the president's car
 * on the floor — overlay of the «Кабинет» hero. */
export function DeskOverlay({ onTab }: { onTab: (t: ManagerTodayTab) => void }) {
  const { staff, assistant } = useOfficeStaff();
  if (!staff) return null;
  const skin = staff.worn.assistant;
  const active = !!assistant?.active;
  const unseen = assistant?.report.unseen ?? 0;
  const line = !active
    ? assistant?.trial ? "Возьмите меня на неделю бесплатно — сделаю всё, пока вас нет" : "Наймите меня — я буду вести дела, пока вас нет"
    : unseen > 0 ? `Шеф, пока вас не было: ${unseen} ${unseen === 1 ? "дело" : unseen < 5 ? "дела" : "дел"}` : "Всё под контролем, шеф";
  return (
    <>
      <div className="pointer-events-none absolute bottom-[-6px] left-2 opacity-90"><CarArt art={staff.worn.car?.art} code={staff.worn.car?.code} width={84} className="ring-2 ring-black/40 shadow-lg" /></div>
      <button onClick={() => onTab("staff")} className="absolute right-1 top-9 flex flex-col items-end" data-testid="desk-assistant">
        <span className="relative mb-1 max-w-[150px] rounded-2xl rounded-br-sm bg-white/95 px-2.5 py-1.5 text-left text-[11px] font-semibold leading-tight text-bg-base shadow-lg">
          {line}
          {unseen > 0 && active && <span className="absolute -left-1.5 -top-1.5 flex h-4 min-w-4 items-center justify-center rounded-full bg-accent-lime px-1 text-[9px] font-black">{unseen}</span>}
        </span>
        <StaffPortrait role="assistant" art={skin?.art} code={skin?.code} size={84} className={active ? "drop-shadow-[0_6px_18px_rgba(0,0,0,0.6)]" : "opacity-60 grayscale-[40%]"} />
      </button>
    </>
  );
}

/** «Пока тебя не было»: what the assistant did. */
export function AwayReport({ onTab }: { onTab: (t: ManagerTodayTab) => void }) {
  const queryClient = useQueryClient();
  const { assistant } = useOfficeStaff();
  const seen = useMutation({
    mutationFn: markManagerAssistantSeen,
    onSuccess: (report) => queryClient.setQueryData<ManagerAssistantOffice>(["manager", "assistant"], (o) => (o ? { ...o, report } : o)),
  });
  if (!assistant?.active) return null;
  const { report } = assistant;
  if (report.entries.length === 0) {
    return (
      <p className="rounded-2xl bg-bg-surface px-3 py-2.5 text-xs text-ink-mist">
        🗂 {assistant.name} на месте: начнёт работу перед закрытием окна. <button onClick={() => onTab("staff")} className="font-bold text-violet-200">Правила →</button>
      </p>
    );
  }
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-violet-500/15 via-bg-surface to-bg-surface p-4 ring-1 ring-violet-300/25" data-testid="away-report">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">🗂 Пока тебя не было</h2>
        {report.unseen > 0 && (
          <button disabled={seen.isPending} onClick={() => seen.mutate()} className="rounded-full bg-violet-400/20 px-2.5 py-0.5 text-micro font-bold text-violet-100">Понятно</button>
        )}
      </div>
      {(report.spent > 0 || report.earned > 0) && (
        <p className="-mt-1 text-micro text-ink-mist">
          {report.earned > 0 && <span className="text-accent-lime">+{eur(report.earned)} </span>}
          {report.spent > 0 && <span className="text-red-300">−{eur(report.spent)} </span>}
          · {assistant.name} в пределах лимита {eur(assistant.rules.limit)}
        </p>
      )}
      <ul className="flex flex-col gap-1.5">
        {report.entries.slice(0, 6).map((e, i) => (
          <li key={`${e.at}-${i}`} className={`flex items-start gap-2 rounded-xl px-2.5 py-1.5 text-xs ${i < report.unseen ? "bg-white/5" : ""}`}>
            <span className="text-base leading-none">{e.icon}</span>
            <span className="min-w-0 flex-1 text-ink-chalk">{e.text}<span className="block text-[10px] text-ink-mist">{ago(e.at)}</span></span>
            {e.eur !== 0 && <span className={`shrink-0 font-mono text-[11px] font-bold ${e.eur > 0 ? "text-accent-lime" : "text-red-300"}`}>{e.eur > 0 ? "+" : ""}{eur(e.eur)}</span>}
          </li>
        ))}
      </ul>
    </section>
  );
}

/** «Ежедневник» of the president: what's next, in order. */
export function Diary({ onTab }: { onTab: (t: ManagerTodayTab) => void }) {
  const { data } = useQuery({ queryKey: ["manager", "summary"], queryFn: fetchManagerSummary, staleTime: 60_000 });
  const { assistant } = useOfficeStaff();
  if (!data?.club) return null;
  const rows: { icon: string; title: string; when?: string; tab?: ManagerTodayTab; hot?: boolean }[] = [];
  const s = data.season;
  if (s.transfers_open) rows.push({ icon: "🔁", title: "Закрытие трансферного окна", when: at(s.preseason_ends_at), tab: "transfers", hot: true });
  const nm = data.club.next_match;
  if (nm) rows.push({ icon: "⚽", title: `${nm.home ? "Дома" : "В гостях"}: «${nm.opponent}»`, when: at(nm.at), tab: "club" });
  else rows.push({ icon: "🏁", title: data.league?.status === "active" ? "Первый тур нового сезона" : "Твой первый тур в лиге", when: at(s.first_round_at), tab: "league" });
  if (!s.transfers_open) rows.push({ icon: "🔓", title: "Трансферное окно откроется после последнего тура сезона" });
  const played = data.league?.status === "active" ? data.league.rounds_played : 0;
  const press = (assistant?.press_rounds ?? []).find((r) => r > played);
  if (press && data.league?.status === "active") rows.push({ icon: "🎙", title: `Пресс-конференция после ${press}-го тура`, when: `через ${press - played} тур.` });
  for (const t of data.today.slice(0, 3)) rows.push({ icon: t.icon, title: t.text, tab: t.tab, hot: t.urgent });
  if (rows.length === 0) return null;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="diary">
      <h2 className="font-display text-base font-bold text-ink-chalk">📒 Ежедневник</h2>
      <ol className="relative flex flex-col gap-1.5 before:absolute before:bottom-2 before:left-[13px] before:top-2 before:w-px before:bg-white/10">
        {rows.map((r, i) => (
          <li key={`${r.title}-${i}`}>
            <button disabled={!r.tab} onClick={() => r.tab && onTab(r.tab)} className="relative flex w-full items-center gap-2.5 rounded-xl py-1 pr-1 text-left">
              <span className={`z-10 flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm ${r.hot ? "bg-amber-400/25 ring-1 ring-amber-300/60" : "bg-bg-raised"}`}>{r.icon}</span>
              <span className="min-w-0 flex-1 text-xs text-ink-chalk">{r.title}</span>
              {r.when && <span className="shrink-0 text-[10px] font-semibold text-ink-mist">{r.when}</span>}
            </button>
          </li>
        ))}
      </ol>
    </section>
  );
}
