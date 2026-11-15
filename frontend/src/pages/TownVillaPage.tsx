import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";

import {
  buyVillaItem, chooseVillaCar, createVillaInvoice, fetchTownInvoiceStatus, fetchVilla, saveVillaLayout, setVillaStaff,
  upgradeVilla, type VillaItem, type VillaShopItem, type VillaState,
} from "@/api/town";
import { IconCoin } from "@/components/icons";
import VillaPlot from "@/components/town/VillaPlot";
import { staticUrl } from "@/lib/api";
import { formatGameError } from "@/lib/errors";
import { hapticNotify, openTelegramInvoice } from "@/lib/telegram";
import { KIND_LABEL, checkLayout, footprint } from "@/lib/villa";
import { useAuthStore } from "@/store/authStore";

const fmt = (n: number) => n.toLocaleString("ru-RU");
type Tab = "plot" | "shop" | "staff" | "garage";
type Draft = Record<number, { x: number | null; y: number | null; rot: number }>;

/** «Моя вилла» (/town/villa): the player's own plot — place, turn and store
 * things, buy them, level the villa and the garage, hire residents. */
export default function TownVillaPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [tab, setTab] = useState<Tab>("plot");
  const [message, setMessage] = useState<{ ok: boolean; text: string } | null>(null);
  const { data, error } = useQuery({ queryKey: ["town-villa"], queryFn: fetchVilla });

  const apply = (text?: string) => (res: VillaState | null) => {
    if (!res) return;
    hapticNotify("success");
    if (res.new_balance != null) updateBalance(res.new_balance);
    queryClient.setQueryData(["town-villa"], res);
    void queryClient.invalidateQueries({ queryKey: ["town"] });
    if (text) setMessage({ ok: true, text });
  };
  const fail = (err: unknown) => { hapticNotify("error"); setMessage({ ok: false, text: formatGameError(err, "Не получилось") }); };

  return (
    <div className="flex flex-col gap-3">
      <div className="flex items-center gap-3 px-1">
        <span className="text-4xl" aria-hidden>🏡</span>
        <div className="min-w-0 flex-1">
          <h1 className="truncate font-display text-xl font-bold leading-tight text-ink-chalk">Моя вилла</h1>
          <p className="truncate text-xs text-ink-mist">
            {data ? `Престиж ${fmt(data.prestige)} · +${data.prestige_pct}% к ренте · ❤️ ${fmt(data.likes_total)}` : "Загрузка…"}
          </p>
        </div>
        <Link to="/town" className="shrink-0 rounded-full bg-white/5 px-3 py-1.5 text-xs font-bold text-ink-mist">🏘️ Город</Link>
      </div>
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-xs text-red-400">{formatGameError(error, "Вилла не открылась")}</p>}
      {message && (
        <p className={`rounded-xl px-3 py-2 text-xs ${message.ok ? "bg-accent-lime/10 text-accent-lime" : "bg-red-500/10 text-red-400"}`} role="status">
          {message.text}
        </p>
      )}
      {data && (
        <>
          <div className="grid grid-cols-4 gap-1 rounded-2xl bg-white/5 p-1" role="tablist">
            {([["plot", "🏡 Участок"], ["shop", "🛒 Магазин"], ["staff", "👥 Персонал"], ["garage", "🚗 Гараж"]] as [Tab, string][]).map(([key, title]) => (
              <button
                key={key} type="button" role="tab" aria-selected={tab === key} onClick={() => { setTab(key); setMessage(null); }}
                className={`min-h-[40px] rounded-xl text-[11px] font-bold ${tab === key ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}
              >
                {title}
              </button>
            ))}
          </div>
          {tab === "plot" && <PlotEditor key={JSON.stringify(data.items)} data={data} onSaved={apply("Участок сохранён ✨")} onError={fail} />}
          {tab === "shop" && <Shop data={data} onDone={apply} onError={fail} />}
          {tab === "staff" && <Staff data={data} onDone={apply} onError={fail} />}
          {tab === "garage" && <Garage data={data} onDone={apply} onError={fail} />}
        </>
      )}
    </div>
  );
}

/** The plot in edit mode: tap a thing (or one in storage), then a cell. */
function PlotEditor({ data, onSaved, onError }: { data: VillaState; onSaved: (res: VillaState) => void; onError: (e: unknown) => void }) {
  const [draft, setDraft] = useState<Draft>({});
  const [selected, setSelected] = useState<number | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const items: VillaItem[] = useMemo(
    () => data.items.map((i) => (draft[i.id] ? { ...i, ...draft[i.id] } : i)),
    [data.items, draft],
  );
  const dirty = Object.keys(draft).length > 0;
  const current = items.find((i) => i.id === selected) ?? null;
  const stored = items.filter((i) => i.x == null);
  const save = useMutation({
    mutationFn: () => saveVillaLayout(Object.entries(draft).map(([id, v]) => ({ id: Number(id), ...v }))),
    onSuccess: (res) => { setDraft({}); setSelected(null); onSaved(res); },
    onError,
  });

  const tryMove = (id: number, patch: { x: number | null; y: number | null; rot: number }) => {
    const next = items.map((i) => (i.id === id ? { ...i, ...patch } : i));
    const why = checkLayout(data.grid, next);
    if (why) { hapticNotify("error"); setHint(why); return false; }
    setDraft((d) => ({ ...d, [id]: patch }));
    setHint(null);
    return true;
  };
  const onCell = (x: number, y: number) => {
    if (!current) { setHint("Выбери предмет на участке или на складе"); return; }
    if (tryMove(current.id, { x, y, rot: current.rot })) hapticNotify("success");
  };
  const onItem = (item: VillaItem) => {
    if (current && current.id !== item.id && current.x == null) {
      setHint("Эта клетка занята — выбери свободную");
      return;
    }
    setSelected(item.id === selected ? null : item.id);
    setHint(null);
  };

  return (
    <section className="flex flex-col gap-2">
      <div className="overflow-hidden rounded-3xl border border-white/10 bg-gradient-to-b from-sky-400/25 to-sky-900/10">
        <VillaPlot
          grid={data.grid}
          items={items}
          selectedId={selected}
          onCell={onCell}
          onItem={onItem}
          label={`Участок ${data.grid}×${data.grid}`}
        />
      </div>
      <p className="px-1 text-center text-[11px] text-ink-mist">
        {hint ?? (current ? `«${current.name}» — нажми на клетку, куда поставить` : `Участок ${data.grid}×${data.grid}. Нажми на предмет, потом на клетку`)}
      </p>
      {current && (
        <div className="grid grid-cols-3 gap-2">
          <button
            type="button" onClick={() => tryMove(current.id, { x: current.x, y: current.y, rot: current.rot ? 0 : 1 })}
            disabled={current.x == null}
            className="min-h-[44px] rounded-2xl bg-white/10 text-xs font-bold text-ink-chalk disabled:opacity-40"
          >
            ↻ Повернуть
          </button>
          <button
            type="button"
            onClick={() => { if (tryMove(current.id, { x: null, y: null, rot: current.rot })) setSelected(null); }}
            disabled={current.kind === "villa" || current.kind === "garage" || current.x == null}
            className="min-h-[44px] rounded-2xl bg-white/10 text-xs font-bold text-ink-chalk disabled:opacity-40"
          >
            📦 На склад
          </button>
          <button type="button" onClick={() => setSelected(null)} className="min-h-[44px] rounded-2xl bg-white/5 text-xs font-bold text-ink-mist">
            Готово
          </button>
        </div>
      )}
      {dirty && (
        <div className="grid grid-cols-2 gap-2">
          <button type="button" onClick={() => { setDraft({}); setSelected(null); setHint(null); }} className="min-h-[48px] rounded-2xl bg-white/5 text-sm font-bold text-ink-mist">
            Отменить
          </button>
          <button
            type="button" onClick={() => save.mutate()} disabled={save.isPending}
            className="min-h-[48px] rounded-2xl bg-floodlight text-sm font-bold text-bg-base"
          >
            💾 Сохранить
          </button>
        </div>
      )}
      <div className="rounded-2xl border border-white/10 bg-bg-surface p-3" aria-label="Склад">
        <p className="mb-2 text-xs font-bold text-ink-chalk">📦 Склад {stored.length ? `· ${stored.length}` : ""}</p>
        {stored.length === 0 ? (
          <p className="text-[11px] text-ink-mist">Всё расставлено. Новые вещи — в «Магазине».</p>
        ) : (
          <div className="flex flex-wrap gap-2">
            {stored.map((i) => (
              <button
                key={i.id} type="button" onClick={() => { setSelected(i.id === selected ? null : i.id); setHint(null); }}
                className={`flex min-h-[44px] items-center gap-1 rounded-xl px-2 text-xs font-semibold ${selected === i.id ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-chalk"}`}
                aria-pressed={selected === i.id}
              >
                <span className="text-lg" aria-hidden>{i.emoji}</span>
                {i.name}
                <span className="text-[10px] opacity-70">{footprint(i).join("×")}</span>
              </button>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

async function payWithStars(code: string): Promise<VillaState | null> {
  const invoice = await createVillaInvoice(code);
  const status = await openTelegramInvoice(invoice.invoice_link, invoice.payload_token);
  if (status === "cancelled") return null;
  if (status === "failed") throw new Error("Платёж не прошёл");
  for (let i = 0; i < 20; i++) {
    if ((await fetchTownInvoiceStatus(invoice.payload_token)).status === "completed") return fetchVilla();
    await new Promise((r) => setTimeout(r, 1000));
  }
  throw new Error("Оплата ещё обрабатывается — загляни через минуту");
}

type Handlers = { data: VillaState; onDone: (text?: string) => (res: VillaState | null) => void; onError: (e: unknown) => void };

function Shop({ data, onDone, onError }: Handlers) {
  const buy = useMutation({
    mutationFn: (item: VillaShopItem) => (item.stars ? payWithStars(item.code) : buyVillaItem(item.code, crypto.randomUUID())),
    onSuccess: (res, item) => onDone(`«${item.name}» на складе — поставь на участок 📦`)(res),
    onError,
  });
  const upgrade = useMutation({
    mutationFn: (target: "villa" | "garage") => upgradeVilla(target, crypto.randomUUID()),
    onSuccess: (res, target) => onDone(target === "villa" ? "Вилла стала больше 🏡" : "Гараж готов 🅿️")(res),
    onError,
  });
  return (
    <section className="flex flex-col gap-3">
      <div className="grid grid-cols-2 gap-2">
        <UpgradeCard
          title={`🏡 Вилла · ${data.villa_level} ур.`}
          next={data.next_villa ? `${data.next_villa.level} ур. · участок ${data.next_villa.grid}×${data.next_villa.grid}` : null}
          price={data.next_villa?.price ?? 0}
          busy={upgrade.isPending}
          onBuy={() => upgrade.mutate("villa")}
        />
        <UpgradeCard
          title={data.garage_level ? `🅿️ Гараж · ${data.garage_level} ур.` : "🅿️ Гаража нет"}
          next={data.next_garage ? `${data.next_garage.level} ур. · мест ${data.next_garage.slots}` : null}
          price={data.next_garage?.price ?? 0}
          busy={upgrade.isPending}
          onBuy={() => upgrade.mutate("garage")}
        />
      </div>
      {(["car", "yard", "premium"] as const).map((kind) => (
        <div key={kind} className="rounded-2xl border border-white/10 bg-bg-surface p-3">
          <p className="mb-2 text-xs font-bold text-ink-chalk">{KIND_LABEL[kind]}</p>
          <div className="flex flex-col gap-2">
            {data.shop.filter((s) => s.kind === kind).map((s) => (
              <div key={s.code} className="flex items-center gap-2">
                <span className="grid h-10 w-10 shrink-0 place-items-center rounded-xl bg-white/5 text-xl" aria-hidden>{s.emoji}</span>
                <div className="min-w-0 flex-1">
                  <p className="truncate text-xs font-semibold text-ink-chalk">{s.name}</p>
                  <p className="truncate text-[10px] text-ink-mist">
                    {s.w}×{s.h} · престиж +{s.prestige}
                    {s.owned ? ` · у тебя ${s.owned}` : ""}
                    {s.supply ? ` · осталось ${fmt(Math.max(0, s.supply - s.sold))} из ${fmt(s.supply)}` : ""}
                    {!s.can_buy && s.reason ? ` · ${s.reason}` : ""}
                  </p>
                </div>
                <button
                  type="button" disabled={!s.can_buy || buy.isPending} onClick={() => buy.mutate(s)}
                  aria-label={`Купить: ${s.name}`}
                  className={`flex shrink-0 items-center gap-0.5 rounded-lg px-2 py-1.5 text-[11px] font-bold ${s.can_buy ? (s.stars ? "bg-sky-400 text-bg-base" : "bg-floodlight text-bg-base") : "bg-white/5 text-ink-mist"}`}
                >
                  {s.stars ? `⭐ ${fmt(s.stars)}` : <><IconCoin size={11} /> {fmt(s.coins)}</>}
                </button>
              </div>
            ))}
          </div>
        </div>
      ))}
      <p className="px-1 text-center text-[11px] text-ink-mist">
        Каждые {fmt(data.prestige_per_pct)} престижа — +1% к ренте домов города (до {data.prestige_max_pct}%). Вид предмета считается один раз.
      </p>
    </section>
  );
}

function UpgradeCard({ title, next, price, busy, onBuy }: { title: string; next: string | null; price: number; busy: boolean; onBuy: () => void }) {
  return (
    <div className="flex flex-col gap-1 rounded-2xl border border-white/10 bg-bg-surface p-3">
      <p className="text-xs font-bold text-ink-chalk">{title}</p>
      <p className="min-h-[28px] text-[10px] text-ink-mist">{next ? `Дальше: ${next}` : "Максимальный уровень"}</p>
      {next && (
        <button type="button" onClick={onBuy} disabled={busy} className="flex min-h-[36px] items-center justify-center gap-1 rounded-xl bg-floodlight text-xs font-bold text-bg-base">
          <IconCoin size={12} /> {fmt(price)}
        </button>
      )}
    </div>
  );
}

function Staff({ data, onDone, onError }: Handlers) {
  const hire = useMutation({
    mutationFn: ({ post, id }: { post: string; id: number | null }) => setVillaStaff(post, id),
    onSuccess: (res) => onDone()(res),
    onError,
  });
  return (
    <section className="flex flex-col gap-2">
      <p className="px-1 text-[11px] text-ink-mist">
        Жители работают на вилле по профессии. Каждый на посту даёт престиж. Жителей собирают в паках и в магазине города.
      </p>
      {data.posts.map((p) => {
        const on = data.staff.find((s) => s.post === p.post);
        const fits = data.candidates.filter((c) => c.posts.includes(p.post));
        return (
          <div key={p.post} className="flex items-center gap-2 rounded-2xl border border-white/10 bg-bg-surface p-2">
            <span className="grid h-12 w-12 shrink-0 place-items-center overflow-hidden rounded-xl bg-white/5 text-2xl">
              {on?.resident.image_path ? <img src={staticUrl(on.resident.image_path)} alt="" className="h-full w-full object-cover" /> : p.emoji}
            </span>
            <div className="min-w-0 flex-1">
              <p className="truncate text-xs font-bold text-ink-chalk">{p.emoji} {p.name}</p>
              <select
                aria-label={`Пост: ${p.name}`}
                value={on?.resident.id ?? ""}
                disabled={hire.isPending || (fits.length === 0 && !on)}
                onChange={(e) => hire.mutate({ post: p.post, id: e.target.value ? Number(e.target.value) : null })}
                className="mt-1 w-full rounded-lg bg-white/5 px-2 py-1.5 text-xs text-ink-chalk"
              >
                <option value="">{fits.length ? "— свободно —" : "Нет подходящих жителей"}</option>
                {fits.map((c) => <option key={c.id} value={c.id}>{c.name} · {c.title}</option>)}
              </select>
            </div>
          </div>
        );
      })}
    </section>
  );
}

function Garage({ data, onDone, onError }: Handlers) {
  const choose = useMutation({
    mutationFn: (id: number | null) => chooseVillaCar(id),
    onSuccess: (res) => onDone("Машина выехала в город 🚗")(res),
    onError,
  });
  const cars = data.items.filter((i) => i.kind === "car");
  return (
    <section className="flex flex-col gap-2">
      <p className="px-1 text-[11px] text-ink-mist">
        {data.garage_level
          ? `Гараж ${data.garage_level} ур. · машин ${data.cars} из ${data.garage_slots}. Выбранная машина ездит по карте твоего города — её видят гости.`
          : "Гаража пока нет — построй его в «Магазине»."}
      </p>
      {cars.map((c) => (
        <button
          key={c.id} type="button" onClick={() => choose.mutate(data.car?.id === c.id ? null : c.id)} disabled={choose.isPending}
          aria-pressed={data.car?.id === c.id}
          className={`flex min-h-[52px] items-center gap-2 rounded-2xl border p-2 text-left ${data.car?.id === c.id ? "border-floodlight bg-floodlight/10" : "border-white/10 bg-bg-surface"}`}
        >
          <span className="text-3xl" aria-hidden>{c.emoji}</span>
          <span className="min-w-0 flex-1">
            <span className="block truncate text-xs font-bold text-ink-chalk">{c.name}{c.serial ? ` · № ${c.serial}` : ""}</span>
            <span className="block text-[10px] text-ink-mist">{data.car?.id === c.id ? "Ездит по городу" : "Нажми, чтобы выехать в город"}</span>
          </span>
          {data.car?.id === c.id && <span className="text-sm font-bold text-floodlight">✓</span>}
        </button>
      ))}
      {data.garage_level > 0 && cars.length === 0 && <p className="px-1 text-xs text-ink-mist">Машин пока нет — загляни в «Магазин».</p>}
    </section>
  );
}
