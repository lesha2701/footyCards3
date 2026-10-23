import type { ManagerSquadPlayer } from "@/api/manager";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { staticUrl } from "@/lib/api";
import { pitchRows, inRow } from "@/lib/formationLayout";
import { eur } from "@/lib/managerMoney";

const KIND_LABEL: Record<ManagerSquadPlayer["kind"], string> = {
  own: "Мой игрок", academy: "Академия", live: "Игрок", npc: "Футболист", kid: "Воспитанник",
};
const KIND_RING: Record<ManagerSquadPlayer["kind"], string> = {
  own: "ring-accent-lime", live: "ring-accent-cyan", academy: "ring-violet-400", npc: "ring-white/80", kid: "ring-white/20",
};
const KIND_BADGE: Record<ManagerSquadPlayer["kind"], string> = {
  own: "bg-accent-lime text-bg-base", live: "bg-accent-cyan text-bg-base", academy: "bg-violet-400 text-bg-base",
  npc: "bg-white text-bg-base", kid: "bg-bg-base text-ink-mist",
};

function Face({ p }: { p: ManagerSquadPlayer }) {
  if ((p.kind === "own" || p.kind === "live") && p.appearance) {
    return <PlayerAvatar appearance={p.appearance} number={p.number} className="h-full w-full" />;
  }
  const photo = p.photo ? staticUrl(p.photo) : undefined;
  if (photo) return <img src={photo} alt="" loading="lazy" className="h-full w-full object-cover object-top" />;
  const initials = p.name.split(/\s+/).map((w) => w[0]).join("").slice(0, 2);
  return <span className="flex h-full w-full items-center justify-center bg-bg-base/70 text-xs font-bold text-white/60">{initials}</span>;
}

/** The XI on a pitch in the club's formation, with faces: avatars of the
 * «Мои игроки», card photos of footballers and academy players. */
export default function ManagerPitch({ xi, formation }: { xi: ManagerSquadPlayer[]; formation: string }) {
  const rows = pitchRows(formation, xi.map((p) => p.slot ?? ""));
  const slots = xi.map((p) => ({ ...p, code: p.slot ?? "" }));
  return (
    <section className="relative overflow-hidden rounded-2xl bg-gradient-to-b from-emerald-700 to-emerald-900 px-1 py-4" data-testid="pitch">
      <div className="pointer-events-none absolute inset-0 opacity-20"
        style={{ backgroundImage: "repeating-linear-gradient(0deg, transparent 0 28px, rgba(255,255,255,.25) 28px 56px)" }} />
      <div className="pointer-events-none absolute inset-x-6 top-1/2 h-px bg-white/40" />
      <div className="pointer-events-none absolute left-1/2 top-1/2 h-20 w-20 -translate-x-1/2 -translate-y-1/2 rounded-full border border-white/40" />
      <div className="pointer-events-none absolute bottom-0 left-1/2 h-10 w-36 -translate-x-1/2 border border-b-0 border-white/40" />
      <div className="relative flex flex-col gap-3">
        {rows.map((row) => (
          <div key={row.key} className="flex justify-around">
            {inRow(row, slots).map((p) => (
              <div key={p.code} className="flex w-[4.4rem] flex-col items-center gap-0.5">
                <span className="relative">
                  <span className={`block h-12 w-12 overflow-hidden rounded-full bg-black/30 shadow-lg ring-2 ${KIND_RING[p.kind]} ${p.kind === "kid" ? "opacity-70" : ""}`}>
                    <Face p={p} />
                  </span>
                  <span className={`absolute -left-1.5 -top-1 rounded-md px-1 font-display text-[11px] font-black leading-4 shadow ${KIND_BADGE[p.kind]}`}>
                    {p.rating}
                  </span>
                </span>
                <span className="w-full truncate rounded bg-black/45 px-1 text-center text-micro font-semibold text-white">{p.name}</span>
                <span className="text-[9px] uppercase leading-3 tracking-wide text-white/70">{p.loan ? "аренда" : KIND_LABEL[p.kind]}</span>
                {p.value != null && <span className="text-[9px] font-bold leading-3 text-white/90">{eur(p.value)}</span>}
              </div>
            ))}
          </div>
        ))}
      </div>
    </section>
  );
}
