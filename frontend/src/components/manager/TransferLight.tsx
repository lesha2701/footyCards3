import transfersArt from "@/assets/manager/transfers.webp";
import { managerIcon } from "@/lib/managerIcons";

/** Is my club's transfer window open now: the season's window, and my league isn't running. */
export function windowOpen(season: { transfers_open: boolean }, club?: { trade_locked: boolean } | null): boolean {
  return season.transfers_open && !club?.trade_locked;
}

/** «45 ч», «2 д», «30 мин» until `iso`. */
export function timeLeft(iso: string | null | undefined, now = Date.now()): string {
  if (!iso) return "";
  const min = Math.max(0, Math.round((new Date(iso).getTime() - now) / 60_000));
  if (min < 60) return `${min} мин`;
  const h = Math.round(min / 60);
  return h < 48 ? `${h} ч` : `${Math.round(h / 24)} д`;
}

/** The transfer window as a light: a pulsing green «Live» while deals are
 * open (with the time left), red «Закрыто» during the season. */
export default function TransferLight({ open, until, compact = false, className = "" }: {
  open: boolean; until?: string | null; compact?: boolean; className?: string;
}) {
  const icon = managerIcon("tab_transfers") ?? transfersArt;
  return (
    <span
      data-testid="transfer-light"
      aria-label={open ? "Трансферное окно открыто" : "Трансферное окно закрыто"}
      className={`inline-flex shrink-0 items-center gap-1.5 rounded-full bg-black/60 py-1 pl-1 pr-2 ring-1${open ? "ring-emerald-400/50" : "ring-red-500/40"} ${className}`}
    >
      {!compact && <img src={icon} alt="" className="h-6 w-6 rounded-md object-contain" />}
      <span className={`relative flex h-2 w-2 ${compact ? "ml-1" : ""}`}>
        {open && <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-400 opacity-75" />}
        <span className={`relative inline-flex h-2 w-2 rounded-full ${open ? "bg-emerald-400" : "bg-red-500"}`} />
      </span>
      <span className="flex flex-col leading-none">
        <span className={`text-[10px] font-black uppercase tracking-wide ${open ? "text-emerald-300" : "text-red-300"}`}>{open ? "Live" : "Закрыто"}</span>
        {!compact && <span className="mt-0.5 text-[9px] font-semibold text-ink-mist">{open && until ? `трансферы · ${timeLeft(until)}` : "трансферы"}</span>}
      </span>
    </span>
  );
}
