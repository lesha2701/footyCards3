import { useMutation } from "@tanstack/react-query";

import { checkManagerDeal, type ManagerDealCheck } from "@/api/manager";

const VERDICT: Record<ManagerDealCheck["verdict"], [string, string]> = {
  ok: ["👍 Аналитик: стоит брать", "text-accent-lime bg-accent-lime/10 ring-accent-lime/30"],
  meh: ["🤔 Аналитик: подумай", "text-amber-200 bg-amber-400/10 ring-amber-300/30"],
  bad: ["✋ Аналитик: не советую", "text-red-300 bg-red-500/10 ring-red-400/30"],
};

/** «Аналитик» on a deal before it's sent: a button and the verdict. Shown
 * only with the pass (`enabled`). */
export default function DealCheck({ enabled, kind, targetId, fee = 0, wage = 0, onError }: {
  enabled: boolean; kind: "live" | "npc"; targetId: number; fee?: number; wage?: number; onError: (e: unknown) => void;
}) {
  const check = useMutation({ mutationFn: () => checkManagerDeal({ kind, target_id: targetId, fee, wage }), onError });
  if (!enabled) return null;
  const r = check.data;
  if (!r) {
    return (
      <button disabled={check.isPending} onClick={() => check.mutate()} data-testid="deal-check"
        className="self-start rounded-lg bg-sky-400/15 px-2.5 py-1 text-micro font-bold text-sky-200 ring-1 ring-sky-300/30">
        📊 {check.isPending ? "Считаю…" : "Спросить аналитика"}
      </button>
    );
  }
  const [title, tone] = VERDICT[r.verdict];
  return (
    <div className={`flex flex-col gap-0.5 rounded-xl px-2.5 py-2 text-micro ring-1 ${tone}`} data-testid="deal-verdict">
      <span className="font-bold">{title}</span>
      {r.lines.map((l) => <span key={l} className="text-ink-chalk">• {l}</span>)}
    </div>
  );
}
