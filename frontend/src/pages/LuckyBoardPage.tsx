import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { AnimatePresence, motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { createLuckyBoardInvoice, fetchLuckyBoardStatus, spinLuckyBoard } from "@/api/luckyBoard";
import { fetchShopInvoiceStatus } from "@/api/monetization";
import {
  IconBall, IconBoot, IconCoin, IconFlag, IconGloves, IconTrophy, IconWhistle, type IconProps,
} from "@/components/icons";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type {
  LuckyBoardOutcome, LuckyBoardSide, LuckyBoardSpin, LuckyBoardStatus, LuckyBoardSymbol, LuckyBoardToken,
} from "@/types";

// Art lives in public/lucky-board/ (the board's three windows are transparent
// cut-outs; WINDOWS are their boxes in board.webp, 1080×720). A symbol missing
// from SYMBOL_ART falls back to the app's own icon.
const ART = "/lucky-board";
const SYMBOL_ART: Partial<Record<LuckyBoardSymbol, string>> = {
  ball: `${ART}/ball.webp`,
  boot: `${ART}/boot.webp`,
  glove: `${ART}/gloves.webp`,
  cup: `${ART}/trophy.webp`,
  flag: `${ART}/flag.webp`,
  whistle: `${ART}/whistle.webp`,
};
const BOARD = { src: `${ART}/board.webp`, w: 1080, h: 720 };
const WINDOWS = [109, 417, 725].map((x) => ({ x, y: 249, w: 246, h: 228 }));
const MESSAGE_STRIP = { x: 100, y: 530, w: 880, h: 76 };
const pctOf = (v: number, total: number) => `${(v / total) * 100}%`;

const SYMBOL: Record<LuckyBoardSymbol, { name: string; Icon: (p: IconProps) => JSX.Element; tone: string }> = {
  ball: { name: "Мяч", Icon: IconBall, tone: "text-white" },
  boot: { name: "Бутса", Icon: IconBoot, tone: "text-accent-lime" },
  glove: { name: "Перчатки", Icon: IconGloves, tone: "text-accent-cyan" },
  cup: { name: "Кубок", Icon: IconTrophy, tone: "text-amber-300" },
  flag: { name: "Угловой флажок", Icon: IconFlag, tone: "text-rose-400" },
  whistle: { name: "Свисток", Icon: IconWhistle, tone: "text-slate-300" },
};
const ALL: LuckyBoardSymbol[] = ["ball", "boot", "glove", "cup", "flag", "whistle"];

const STOP_MS = [1100, 1550, 2000];

/** `size` in px, or omitted to fill the parent (the reel windows). */
function SymbolArt({ s, size }: { s: LuckyBoardSymbol; size?: number }) {
  const art = SYMBOL_ART[s];
  if (art) {
    return (
      <img
        src={art}
        alt={SYMBOL[s].name}
        draggable={false}
        style={size ? { width: size, height: size } : undefined}
        className={`object-contain drop-shadow-[0_4px_6px_rgba(0,0,0,0.55)] ${size ? "" : "h-[80%] w-[80%]"}`}
      />
    );
  }
  const { Icon, tone, name } = SYMBOL[s];
  return (
    <span className={tone} aria-label={name}>
      <Icon size={size ?? 48} />
    </span>
  );
}

function plural(n: number, one: string, few: string, many: string) {
  const a = Math.abs(n) % 100;
  const b = a % 10;
  if (a > 10 && a < 20) return many;
  if (b === 1) return one;
  if (b >= 2 && b <= 4) return few;
  return many;
}

function sideText(side: LuckyBoardSide, cosmeticsLeft: number): string {
  const parts: string[] = [];
  if (side.coins) parts.push(`${side.coins} ${plural(side.coins, "монета", "монеты", "монет")}`);
  if (side.tokens) parts.push(`${side.tokens} ${plural(side.tokens, "жетон", "жетона", "жетонов")} навыка`);
  if (side.cosmetic && cosmeticsLeft > 0) {
    parts.push(`косметика табло${side.shards ? ` (если собрана — ${side.shards} ${plural(side.shards, "осколок", "осколка", "осколков")})` : ""}`);
  } else if (side.shards) {
    parts.push(`${side.shards} ${plural(side.shards, "осколок", "осколка", "осколков")}`);
  }
  return parts.length ? parts.join(" + ") : "—";
}

function tokensText(tokens: LuckyBoardToken[]) {
  return tokens.map((t) => `${t.skill_icon} ${t.skill_name} ×${t.quantity}`).join(", ");
}

function pct(v: number) {
  return `${v < 1 ? v.toFixed(1) : Math.round(v * 10) / 10}%`.replace(".", ",");
}

/** One window: a strip of symbols that slides down onto `target`. */
function Reel({ target, spinKey, delay }: { target: LuckyBoardSymbol; spinKey: number; delay: number }) {
  const [strip, setStrip] = useState<LuckyBoardSymbol[]>([target]);
  const last = useRef<LuckyBoardSymbol>(target);
  useEffect(() => {
    if (spinKey === 0) return;
    const filler = Array.from({ length: 14 + Math.round(delay / 120) }, () => ALL[Math.floor(Math.random() * ALL.length)]);
    setStrip([last.current, ...filler, target]);
    last.current = target;
  }, [spinKey]); // eslint-disable-line react-hooks/exhaustive-deps
  // The strip is n windows tall; y in % of the strip itself.
  const n = strip.length;
  return (
    <div className="absolute inset-0 overflow-hidden bg-[radial-gradient(circle_at_50%_40%,#123d27_0%,#03140d_75%)]">
      <motion.div
        key={`${spinKey}-${n}`}
        initial={{ y: "0%" }}
        animate={{ y: `${(-(n - 1) / n) * 100}%` }}
        transition={{ duration: spinKey === 0 ? 0 : delay / 1000, ease: [0.15, 0.6, 0.25, 1.02] }}
        className="flex flex-col"
        style={{ height: `${n * 100}%` }}
      >
        {strip.map((s, i) => (
          <div key={i} className="flex items-center justify-center" style={{ height: `${100 / n}%` }}>
            <SymbolArt s={s} />
          </div>
        ))}
      </motion.div>
      {/* Glass shading: dark at the top and bottom edges of the window */}
      <div className="pointer-events-none absolute inset-0 bg-[linear-gradient(180deg,rgba(0,0,0,0.55)_0%,transparent_22%,transparent_78%,rgba(0,0,0,0.55)_100%)]" />
      {/* LED scanlines over the window */}
      <div className="pointer-events-none absolute inset-0 bg-[repeating-linear-gradient(0deg,rgba(0,0,0,0.18)_0px,rgba(0,0,0,0.18)_1px,transparent_1px,transparent_3px)]" />
    </div>
  );
}

function OddsTable({ status, side }: { status: LuckyBoardStatus; side: "free" | "paid" }) {
  return (
    <table className="w-full text-sm">
      <tbody>
        {status.outcomes.map((o: LuckyBoardOutcome) => (
          <tr key={o.code} className="border-t border-white/5 align-middle">
            <td className="py-1.5 pr-2">
              {o.symbol ? (
                <span className="flex gap-0.5">
                  {[0, 1, 2].map((i) => <SymbolArt key={i} s={o.symbol!} size={16} />)}
                </span>
              ) : (
                <span className="text-caption text-ink-mist">{o.code === "pair" ? "две одинаковые" : "все разные"}</span>
              )}
            </td>
            <td className="py-1.5 pr-2 text-ink-chalk">{o.label}</td>
            <td className="py-1.5 pr-2 text-right font-mono font-bold text-ink-chalk">{pct(side === "free" ? o.free_pct : o.paid_pct)}</td>
            <td className="py-1.5 text-right text-caption text-ink-mist">{sideText(o[side], status.cosmetics_left)}</td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}

function PrizeLine({ spin }: { spin: LuckyBoardSpin }) {
  const p = spin.prize;
  if (p.blocked) return <p className="text-sm text-ink-mist">Награды за игры для этого аккаунта отключены.</p>;
  const lines: string[] = [];
  if (p.coins) lines.push(`+${p.coins} ${plural(p.coins, "монета", "монеты", "монет")}`);
  if (p.tokens.length) lines.push(`Жетоны навыка: ${tokensText(p.tokens)}`);
  if (p.cosmetic) lines.push(`Косметика: «${p.cosmetic.name}»`);
  if (p.badge) lines.push(`Значок: «${p.badge.name}»`);
  if (p.shards) lines.push(`+${p.shards} ${plural(p.shards, "осколок", "осколка", "осколков")}`);
  if (p.crafted_tokens.length) lines.push(`Осколки собраны в жетон: ${tokensText(p.crafted_tokens)}`);
  if (!lines.length) return <p className="text-sm text-ink-mist">В этот раз без приза.</p>;
  return (
    <ul className="flex flex-col items-center gap-0.5 text-sm font-semibold text-accent-lime">
      {lines.map((l) => <li key={l}>{l}</li>)}
    </ul>
  );
}

async function waitForPayment(token: string): Promise<void> {
  for (let attempt = 0; attempt < 20; attempt++) {
    if ((await fetchShopInvoiceStatus(token)).status === "completed") return;
    await new Promise((resolve) => setTimeout(resolve, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

function clock(iso: string | null) {
  if (!iso) return "";
  return new Date(iso).toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" });
}

export default function LuckyBoardPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: fetched, isLoading } = useQuery({ queryKey: ["lucky-board-status"], queryFn: fetchLuckyBoardStatus });
  const [status, setStatus] = useState<LuckyBoardStatus | null>(null);
  const [reels, setReels] = useState<LuckyBoardSymbol[]>(["ball", "cup", "ball"]);
  const [spinKey, setSpinKey] = useState(0);
  const [rolling, setRolling] = useState(false);
  const [result, setResult] = useState<LuckyBoardSpin | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [tab, setTab] = useState<"free" | "paid">("free");

  useEffect(() => {
    if (fetched && !rolling) setStatus(fetched);
  }, [fetched]); // eslint-disable-line react-hooks/exhaustive-deps

  const spinMutation = useMutation({
    mutationFn: () => spinLuckyBoard(crypto.randomUUID()),
    onMutate: () => {
      setError(null);
      setResult(null);
      haptic("medium");
    },
    onSuccess: (spin) => {
      setRolling(true);
      setReels(spin.reels);
      setSpinKey((k) => k + 1);
      setTab(spin.source);
      // Everything the spin paid stays hidden until the last window stops.
      window.setTimeout(() => {
        setRolling(false);
        setResult(spin);
        setStatus(spin.status);
        updateBalance(spin.new_balance);
        hapticNotify(spin.outcome === "miss" ? "warning" : "success");
        queryClient.setQueryData(["lucky-board-status"], spin.status);
        queryClient.invalidateQueries({ queryKey: ["game-limits"] });
      }, STOP_MS[2] + 150);
    },
    onError: (err) => setError(formatGameError(err, "Табло не запустилось")),
  });

  const buyMutation = useMutation({
    mutationFn: async () => {
      const invoice = await createLuckyBoardInvoice();
      const paid = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
      if (paid === "cancelled") return "cancelled" as const;
      if (paid === "failed") throw new Error("Платёж не прошёл");
      await waitForPayment(invoice.payload_token);
      return "paid" as const;
    },
    onSuccess: () => {
      setError(null);
      queryClient.invalidateQueries({ queryKey: ["lucky-board-status"] });
    },
    onError: (err) => setError(err instanceof Error ? err.message : formatGameError(err, "Не удалось оплатить")),
  });

  if (isLoading || !status) return null;

  const busy = rolling || spinMutation.isPending;
  const spinsLeft = status.free_remaining + status.paid_spins;
  const paidOn = status.paid_daily_limit > 0;
  const paidLeftToday = Math.max(0, status.paid_daily_limit - status.paid_bought_today);
  const cooling = status.hourly_remaining === 0;
  const shardPct = Math.min(100, (status.shards / Math.max(1, status.shards_per_token)) * 100);
  const won = result && result.outcome !== "miss";

  return (
    <div className="flex flex-col gap-4">
      <div>
        <h1 className="sr-only">Табло удачи</h1>
        <img src={`${ART}/title.webp`} alt="" className="mx-auto -mb-1 w-full max-w-[420px]" />
        <p className="mt-1 text-sm text-ink-mist">
          Запусти стадионное табло: три одинаковых символа — приз. Цена запуска всегда одна, шансы — ниже, честно и полностью.
        </p>
      </div>

      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="font-mono text-base font-bold text-ink-chalk">{status.free_remaining}/{status.free_per_day}</p>
          <p className="text-micro text-ink-mist">бесплатно сегодня</p>
        </div>
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="font-mono text-base font-bold text-ink-chalk">{status.paid_spins}</p>
          <p className="text-micro text-ink-mist">куплено</p>
        </div>
        <div className="rounded-xl bg-bg-surface px-2 py-2">
          <p className="flex items-center justify-center gap-1 font-mono text-base font-bold text-ink-chalk">
            <img src={`${ART}/shard.webp`} alt="" className="h-5 w-5" />
            {status.shards}/{status.shards_per_token}
          </p>
          <p className="text-micro text-ink-mist">осколки жетона</p>
          <div className="mx-auto mt-1 h-1 w-full overflow-hidden rounded-full bg-white/10">
            <div className="h-full rounded-full bg-accent-cyan" style={{ width: `${shardPct}%` }} />
          </div>
        </div>
      </div>

      {/* The scoreboard: the reels sit under the drawn board, seen through its transparent windows. */}
      <div className="flex flex-col gap-2">
        <div className="relative w-full" style={{ aspectRatio: `${BOARD.w} / ${BOARD.h}` }}>
          {WINDOWS.map((win, i) => (
            <div
              key={i}
              className="absolute"
              style={{ left: pctOf(win.x, BOARD.w), top: pctOf(win.y, BOARD.h), width: pctOf(win.w, BOARD.w), height: pctOf(win.h, BOARD.h) }}
            >
              <Reel target={reels[i]} spinKey={spinKey} delay={STOP_MS[i]} />
            </div>
          ))}
          <img src={BOARD.src} alt="" draggable={false} className="pointer-events-none absolute inset-0 h-full w-full select-none" />
          <div
            className="absolute flex items-center justify-center overflow-hidden px-2 text-center"
            style={{
              left: pctOf(MESSAGE_STRIP.x, BOARD.w), top: pctOf(MESSAGE_STRIP.y, BOARD.h),
              width: pctOf(MESSAGE_STRIP.w, BOARD.w), height: pctOf(MESSAGE_STRIP.h, BOARD.h),
            }}
          >
            <AnimatePresence mode="wait">
              <motion.p
                key={result && !rolling ? result.id : busy ? "busy" : "idle"}
                initial={{ opacity: 0, y: 4 }}
                animate={{ opacity: 1, y: 0 }}
                exit={{ opacity: 0 }}
                className={`truncate font-mono text-sm font-bold uppercase tracking-[0.2em] [text-shadow:0_0_8px_rgba(251,191,36,0.8)] ${
                  result && !rolling && !won ? "text-amber-200/70" : "text-amber-300"
                } ${busy ? "animate-pulse" : ""}`}
              >
                {result && !rolling ? `${result.label}${won ? "!" : ""}` : busy ? "Идёт розыгрыш…" : "Жми «Запустить табло»"}
              </motion.p>
            </AnimatePresence>
          </div>
        </div>
        <div className="flex min-h-[24px] justify-center text-center">
          <AnimatePresence mode="wait">
            {result && !rolling && (
              <motion.div key={result.id} initial={{ opacity: 0, y: 6 }} animate={{ opacity: 1, y: 0 }}>
                <PrizeLine spin={result} />
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      </div>

      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}

      {!status.enabled ? (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">Табло временно выключено.</p>
      ) : (
        <div className="flex flex-col gap-2">
          {spinsLeft > 0 ? (
            <button
              onClick={() => spinMutation.mutate()}
              disabled={busy || cooling}
              className="flex w-full flex-col items-center rounded-2xl bg-floodlight py-2.5 text-bg-base active:scale-95 disabled:opacity-50"
            >
              <span className="font-display text-base font-bold">
                {cooling ? "Табло остывает" : busy ? "Крутится…" : "Запустить табло"}
              </span>
              <span className="text-caption font-semibold opacity-80">
                {cooling
                  ? `снова можно в ${clock(status.hour_resets_at)}`
                  : status.free_remaining > 0
                    ? `бесплатно · осталось ${status.free_remaining}`
                    : `куплено · осталось ${status.paid_spins}`}
              </span>
            </button>
          ) : (
            <p className="text-center text-sm text-ink-mist">Бесплатные запуски вернутся завтра.</p>
          )}
          {paidOn && status.free_remaining === 0 && (
            <button
              onClick={() => buyMutation.mutate()}
              disabled={buyMutation.isPending || paidLeftToday === 0 || busy}
              className="w-full rounded-xl bg-white/5 py-3 text-sm font-bold text-ink-chalk active:scale-95 disabled:opacity-40"
            >
              {buyMutation.isPending
                ? "Ждём оплату…"
                : paidLeftToday === 0
                  ? "Лимит покупок на сегодня исчерпан"
                  : `Купить запуск за ⭐ ${status.stars_cost} · осталось ${paidLeftToday}`}
            </button>
          )}
        </div>
      )}

      <div className="rounded-2xl bg-bg-surface px-4 py-3">
        <div className="mb-2 flex flex-col gap-2">
          <p className="font-display text-sm font-bold text-ink-chalk">Шансы и призы</p>
          <div className="grid grid-cols-2 rounded-lg bg-white/5 p-0.5 text-caption font-semibold">
            {(["free", "paid"] as const).map((t) => (
              <button
                key={t}
                onClick={() => setTab(t)}
                className={`rounded-md px-2.5 py-1.5 ${tab === t ? "bg-white/15 text-ink-chalk" : "text-ink-mist"}`}
              >
                {t === "free" ? "Бесплатный" : `Платный · ⭐ ${status.stars_cost}`}
              </button>
            ))}
          </div>
        </div>
        <OddsTable status={status} side={tab} />
        <p className="mt-2 text-caption text-ink-mist">
          {tab === "free"
            ? "Это точные шансы: сервер разыгрывает запуск по этой же таблице."
            : `Платный запуск всегда что-то даёт. Его призы остаются на твоём аккаунте — их нельзя обменять, продать или выставить на рынок. ${status.shards_per_token} осколков сами собираются в жетон навыка.`}
        </p>
      </div>

      <details className="rounded-2xl bg-bg-surface px-4 py-3 text-sm text-ink-mist">
        <summary className="cursor-pointer font-display font-bold text-ink-chalk">Правила</summary>
        <ul className="mt-2 list-disc space-y-1 pl-4">
          <li>{status.free_per_day} {plural(status.free_per_day, "бесплатный запуск", "бесплатных запуска", "бесплатных запусков")} в день, сначала тратятся они.</li>
          {paidOn && (
            <li>Дальше — запуск за ⭐ {status.stars_cost}, не больше {status.paid_daily_limit} покупок в день. Ставок нет: цена всегда одна.</li>
          )}
          <li>Не больше {status.hourly_limit} запусков в час.</li>
          <li>Исход решает сервер; табло только показывает его.</li>
          <li>Жетон навыка выпадает на случайный доступный навык.</li>
          <li className="flex items-center gap-1">Монеты бывают только в бесплатных запусках <IconCoin size={14} /></li>
        </ul>
      </details>
    </div>
  );
}
