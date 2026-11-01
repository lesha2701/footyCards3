import { useQuery } from "@tanstack/react-query";

import { fetchManagerCup, fetchManagerNews, type ManagerCupMatch } from "@/api/manager";
import ShareButton from "@/components/common/ShareButton";
import { eur } from "@/lib/managerMoney";

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { weekday: "short" })} ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function Score({ m }: { m: ManagerCupMatch }) {
  if (m.bye) return <span className="text-micro text-ink-mist">проходит без игры</span>;
  if (m.hs == null) return <span className="text-micro text-ink-mist">—</span>;
  return (
    <span className="font-mono text-xs font-bold text-ink-chalk">
      {m.hs}:{m.as}{m.pens && <span className="font-normal text-ink-mist"> (пен. {m.pens[0]}:{m.pens[1]})</span>}
    </span>
  );
}

/** «Кубок менеджеров»: my path, the last rounds, prizes and past winners. */
export function CupPanel() {
  const { data } = useQuery({ queryKey: ["manager", "cup"], queryFn: fetchManagerCup, refetchInterval: 120_000 });
  if (!data?.enabled || !data.cup) return null;
  const cup = data.cup;
  const mine = cup.mine;
  return (
    <section className="flex flex-col gap-2.5 rounded-2xl bg-gradient-to-br from-amber-400/25 via-bg-surface to-bg-surface p-4 ring-1 ring-amber-300/40" data-testid="manager-cup">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">🏆 Кубок менеджеров</h2>
        <span className="shrink-0 rounded-full bg-black/30 px-2 py-0.5 text-micro font-bold text-amber-100">{cup.clubs} клубов</span>
      </div>
      <p className="-mt-1 text-xs text-ink-mist">
        {cup.status === "finished"
          ? `Кубок разыгран. Победитель — «${cup.winner}»`
          : mine?.alive ? `Твой клуб в игре. Следующий круг — ${when(cup.next_at)}`
            : mine ? `Твой клуб выбыл (${mine.stage}). Следующий круг — ${when(cup.next_at)}`
              : `Играют клубы сезона, следующий круг — ${when(cup.next_at)}`}
      </p>
      {cup.rounds.filter((r) => r.matches.length > 0).map((r) => (
        <div key={r.index} className="flex flex-col gap-1">
          <p className="text-micro font-bold uppercase tracking-wider text-amber-200">{r.name || `Круг ${r.index + 1}`} · {when(r.at)}</p>
          {r.matches.map((m, i) => (
            <div key={i} className={`flex items-center gap-2 rounded-xl px-2.5 py-1.5 text-xs ${m.mine ? "bg-amber-300/15 ring-1 ring-amber-300/40" : "bg-black/20"}`}>
              <span className={`min-w-0 flex-1 truncate ${m.winner === m.a && m.winner ? "font-bold text-ink-chalk" : "text-ink-mist"}`}>{m.a}</span>
              <Score m={m} />
              <span className={`min-w-0 flex-1 truncate text-right ${m.winner === m.b && m.winner ? "font-bold text-ink-chalk" : "text-ink-mist"}`}>{m.b ?? ""}</span>
            </div>
          ))}
        </div>
      ))}
      {data.prizes.length > 0 && (
        <p className="text-micro text-ink-mist">
          Призовые: {data.prizes.map((p) => `${p.stage} ${eur(p.amount)}`).join(" · ")}
        </p>
      )}
      {data.history.length > 0 && (
        <p className="text-micro text-ink-mist">Прошлые победители: {data.history.map((h) => `«${h.winner}»`).join(", ")}</p>
      )}
    </section>
  );
}

/** «Газета лиги»: the last match day as a front page, shareable as a picture. */
export function NewsPanel() {
  const { data } = useQuery({ queryKey: ["manager", "news"], queryFn: fetchManagerNews, retry: false, refetchInterval: 300_000 });
  if (!data) return null;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-[#f3eee2] p-4 text-[#1b1a17] shadow-[0_10px_30px_-12px_rgba(0,0,0,0.8)]" data-testid="manager-news">
      <div className="flex items-baseline justify-between border-b-2 border-[#1b1a17] pb-1">
        <span className="font-display text-lg font-black tracking-tight">ГАЗЕТА ЛИГИ</span>
        <span className="text-micro font-semibold">{data.league} · {data.date}</span>
      </div>
      <p className="font-display text-xl font-black leading-tight">{data.headline}</p>
      <div className="grid grid-cols-2 gap-x-3 gap-y-1 border-t border-[#1b1a17]/30 pt-2 text-[11px] leading-snug">
        {data.leader && <p><b>Лидер:</b> «{data.leader.name}», {data.leader.points} очк.</p>}
        {data.my_place && <p><b>Наше место:</b> {data.my_place}</p>}
        <p className="col-span-2"><b>Крупнейшая победа:</b> {data.biggest.home} {data.biggest.hs}:{data.biggest.as} {data.biggest.away}</p>
        {data.scorer && <p className="col-span-2"><b>Бомбардир:</b> {data.scorer.name} ({data.scorer.team}) — {data.scorer.goals}</p>}
        {data.transfer && <p className="col-span-2"><b>Трансфер недели:</b> {data.transfer.who} → «{data.transfer.to}», {eur(data.transfer.fee)}</p>}
        {data.cup && <p className="col-span-2"><b>Кубок:</b> {data.cup.replace(/^Кубок: /, "")}</p>}
      </div>
      <details className="text-[11px]">
        <summary className="cursor-pointer font-semibold">Все матчи дня ({data.matches.length})</summary>
        <div className="mt-1 flex flex-col gap-0.5">
          {data.matches.map((m, i) => (
            <p key={i} className={m.mine ? "font-bold" : ""}>Т{m.round}: {m.home} {m.hs}:{m.as} {m.away}</p>
          ))}
        </div>
      </details>
      <ShareButton kind="manager_news" id={0} label="Поделиться газетой" className="mt-1" />
    </section>
  );
}
