import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { chooseManagerEvent, fetchManagerEvents, setManagerPlan, type ManagerEventOption, type ManagerEvents } from "@/api/manager";
import { eur } from "@/lib/managerMoney";
import { hapticNotify, hapticSelection } from "@/lib/telegram";

const LINE_LABEL: Record<string, string> = { GK: "ВРТ", DEF: "ЗАЩ", MID: "ПЗ", FWD: "НАП" };

function signed(n: number, unit = "%"): string {
  return `${n > 0 ? "+" : n < 0 ? "−" : ""}${Math.abs(n)}${unit}`;
}

/** What an event option does, in short chips. */
function effects(o: ManagerEventOption): { text: string; good: boolean }[] {
  const out: { text: string; good: boolean }[] = [];
  if (o.money) out.push({ text: `${o.money > 0 ? "+" : "−"}${eur(Math.abs(o.money))}`, good: o.money > 0 });
  if (o.fans) out.push({ text: `${signed(o.fans, "")} фанатов`, good: o.fans > 0 });
  if (o.form_pct && o.form_rounds) out.push({ text: `форма ${signed(o.form_pct)} на ${o.form_rounds} тур${o.form_rounds === 1 ? "" : "а"}`, good: o.form_pct > 0 });
  if (out.length === 0) out.push({ text: "ничего не меняется", good: true });
  return out;
}

/** «Установка на матч» for the next league match and «События клуба» waiting for a decision. */
export default function MatchPlanPanel({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "events"], queryFn: fetchManagerEvents, refetchInterval: 60_000 });
  const onData = (v: ManagerEvents) => {
    queryClient.setQueryData(["manager", "events"], v);
    queryClient.invalidateQueries({ queryKey: ["manager", "summary"] });
    queryClient.invalidateQueries({ queryKey: ["manager"], exact: true });
  };
  const plan = useMutation({ mutationFn: setManagerPlan, onSuccess: (v) => { hapticSelection(); onData(v); }, onError });
  const choose = useMutation({
    mutationFn: ({ id, option }: { id: number; option: string }) => chooseManagerEvent(id, option),
    onSuccess: (v) => { hapticNotify("success"); onData(v); },
    onError,
  });
  if (!data) return null;
  const last = data.recent.find((e) => e.status === "chosen");
  return (
    <>
      {data.events.map((e) => (
        <section key={e.id} data-testid={e.press ? "press-conference" : "club-event"}
          className={`flex flex-col gap-2.5 rounded-2xl p-4 ring-1 ${e.press
            ? "bg-gradient-to-br from-sky-500/25 via-bg-surface to-bg-surface ring-sky-300/40"
            : "bg-gradient-to-br from-fuchsia-500/25 via-bg-surface to-bg-surface ring-fuchsia-400/40"}`}>
          <p className={`text-micro font-bold uppercase tracking-[0.18em] ${e.press ? "text-sky-200" : "text-fuchsia-200"}`}>
            {e.press ? "🎙 Пресс-конференция · микрофоны включены" : "Событие клуба"}
          </p>
          <p className="font-display text-base font-bold text-ink-chalk">{e.emoji} {e.title}</p>
          <p className="-mt-1 text-xs text-ink-mist">{e.text}</p>
          <div className="grid grid-cols-2 gap-2">
            {e.options.map((o) => (
              <button key={o.code} disabled={choose.isPending} onClick={() => choose.mutate({ id: e.id, option: o.code })}
                className="flex flex-col gap-1 rounded-xl bg-black/30 p-2.5 text-left ring-1 ring-white/10 active:scale-[0.97] disabled:opacity-50">
                <span className="text-xs font-bold text-ink-chalk">{o.label}</span>
                {effects(o).map((x) => (
                  <span key={x.text} className={`text-micro font-semibold ${x.good ? "text-accent-lime" : "text-red-300"}`}>{x.text}</span>
                ))}
              </button>
            ))}
          </div>
        </section>
      ))}
      {data.can_plan && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="match-plan">
          <div className="flex items-center justify-between gap-2">
            <h2 className="font-display text-base font-bold text-ink-chalk">🎯 Установка на матч</h2>
            {data.form_pct !== 0 && (
              <span className={`rounded-full px-2 py-0.5 text-micro font-bold ${data.form_pct > 0 ? "bg-accent-lime/15 text-accent-lime" : "bg-red-500/15 text-red-300"}`}>
                форма {signed(data.form_pct)}
              </span>
            )}
          </div>
          <p className="-mt-1 text-micro text-ink-mist">Только на ближайший матч, потом — обычная игра.</p>
          <div className="grid grid-cols-2 gap-2">
            {[{ code: "normal", name: "Обычная игра", emoji: "⚖️", about: "Как в тактике, без сюрпризов", mods: null, injury_x: 1 }, ...data.plans].map((p) => {
              const on = data.plan === p.code;
              return (
                <button key={p.code} disabled={plan.isPending} onClick={() => !on && plan.mutate(p.code)}
                  className={`flex flex-col gap-0.5 rounded-xl p-2.5 text-left active:scale-[0.97] ${on ? "bg-floodlight/15 ring-2 ring-floodlight" : "bg-bg-raised ring-1 ring-white/5"}`}>
                  <span className="text-xs font-bold text-ink-chalk">{p.emoji} {p.name}</span>
                  <span className="text-micro leading-tight text-ink-mist">{p.about}</span>
                  {p.mods && (
                    <span className="mt-0.5 flex flex-wrap gap-x-1.5 text-micro font-semibold">
                      {Object.entries(p.mods).filter(([, v]) => v).map(([line, v]) => (
                        <span key={line} className={v > 0 ? "text-accent-lime" : "text-red-300"}>{LINE_LABEL[line]} {signed(v)}</span>
                      ))}
                      {p.injury_x !== 1 && <span className={p.injury_x < 1 ? "text-accent-lime" : "text-red-300"}>травмы {p.injury_x === 0 ? "нет" : `×${p.injury_x}`}</span>}
                    </span>
                  )}
                </button>
              );
            })}
          </div>
        </section>
      )}
      {last?.result && (
        <p className="-mt-2 px-1 text-micro text-ink-mist">
          Последнее решение: {last.emoji} {last.title} — {last.options.find((o) => o.code === last.choice)?.label}
          {last.by === "assistant" && " · решил помощник"}
        </p>
      )}
    </>
  );
}
