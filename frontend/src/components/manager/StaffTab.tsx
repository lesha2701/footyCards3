import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  buyManagerStaffItem,
  fetchManagerAssistant,
  fetchManagerStaff,
  fireManagerStaff,
  hireManagerStaff,
  renameManagerVip,
  setManagerAssistantRules,
  startManagerAssistantTrial,
  wearManagerStaffItem,
  type ManagerAssistantRules,
  type ManagerRarity,
  type ManagerStaffItem,
  type ManagerStaffRole,
  type ManagerStaffView,
  type ManagerVip,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import { ListSkeleton } from "@/components/common/Skeleton";
import OfficeScene, { CarArt } from "@/components/manager/OfficeScene";
import StaffPortrait from "@/components/manager/StaffPortrait";
import { staticUrl } from "@/lib/api";
import { eur } from "@/lib/managerMoney";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify, hapticSelection } from "@/lib/telegram";

const RARITY: Record<ManagerRarity, { label: string; ring: string; text: string }> = {
  common: { label: "обычный", ring: "ring-white/15", text: "text-ink-mist" },
  rare: { label: "редкий", ring: "ring-sky-400/60", text: "text-sky-300" },
  epic: { label: "эпический", ring: "ring-fuchsia-400/60", text: "text-fuchsia-300" },
  legendary: { label: "легендарный", ring: "ring-amber-300/80", text: "text-amber-300" },
};

const until = (iso: string | null) => iso ? new Date(iso).toLocaleDateString("ru-RU", { day: "numeric", month: "long" }) : "";

/** «👥 Штаб» of «Менеджер»: the VIP «Помощник» and «Аналитик» (Stars, their
 * skins and names, the assistant's rules), the club staff hired from the
 * owner's «Жители города» and the president's car and office. */
export default function StaffTab({ onError }: { onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["manager", "staff"], queryFn: fetchManagerStaff });
  const [pick, setPick] = useState<"assistant" | "analyst">("assistant");
  const [busy, setBusy] = useState<string | null>(null);
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
  const vip = data.vip.find((v) => v.role === pick) ?? data.vip[0];
  const none = data.vip.every((v) => !v.active);
  const takeItem = (i: ManagerStaffItem) => {
    if (i.owned) item.mutate({ code: i.code, buy: false });
    else if (i.stars > 0) void stars(i.code);
    else item.mutate({ code: i.code, buy: true });
  };

  return (
    <div className="flex flex-col gap-4" data-testid="staff-tab">
      <section className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-[#1b1530] via-[#13202b] to-[#0d1a14] p-4 ring-1 ring-violet-300/25">
        <p className="text-micro font-bold uppercase tracking-[0.2em] text-violet-200">👥 Штаб президента</p>
        <p className="mt-1 text-xs text-ink-mist">Двое VIP за звёзды работают на тебя, а штат из жителей города усиливает клуб.</p>
        <div className="mt-3 grid grid-cols-2 gap-2.5">
          {data.vip.map((v) => <VipCard key={v.code} vip={v} on={v.role === pick} onPick={() => { hapticSelection(); setPick(v.role); }} />)}
        </div>
        {none && data.bundle_stars > 0 && (
          <button disabled={busy === "staff_bundle"} onClick={() => void stars("staff_bundle")} data-testid="staff-bundle"
            className="mt-3 flex w-full items-center justify-between gap-2 rounded-2xl bg-gradient-to-r from-amber-300 to-amber-500 px-3.5 py-2.5 text-left text-bg-base shadow-[0_8px_24px_-10px_rgba(251,191,36,0.9)]">
            <span className="min-w-0">
              <span className="block text-sm font-black">Оба сразу</span>
              <span className="block text-micro font-semibold opacity-80">Аналитик + помощник на {vip.days} дн. — выгоднее</span>
            </span>
            <span className="shrink-0 rounded-xl bg-black/20 px-2.5 py-1 text-sm font-black">{data.bundle_stars} ⭐</span>
          </button>
        )}
      </section>

      <VipDetails key={vip.role} vip={vip} data={data} busy={busy === vip.code || trial.isPending} onStars={() => void stars(vip.code)}
        onTrial={() => trial.mutate()} onDone={done} onError={onError} onItem={takeItem} itemBusy={item.isPending || !!busy} />

      <ClubStaff data={data} onDone={done} onError={onError} />

      <Status data={data} onItem={takeItem} busy={item.isPending || !!busy} />
      <p className="px-1 text-micro text-ink-mist">VIP-персонал, скины, машины и кабинеты — удобство и стиль. Сила клуба зависит от штата из жителей и решений президента.</p>
    </div>
  );
}

function VipCard({ vip, on, onPick }: { vip: ManagerVip; on: boolean; onPick: () => void }) {
  return (
    <button onClick={onPick} data-testid={`vip-${vip.role}`}
      className={`relative flex flex-col items-center overflow-hidden rounded-2xl px-2 pb-2.5 pt-1 text-center transition ${on
        ? "bg-white/10 ring-2 ring-violet-300" : "bg-black/25 ring-1 ring-white/10"}`}>
      <StaffPortrait role={vip.role} art={vip.skin?.art} size={92} className={vip.active ? "" : "opacity-70 grayscale-[35%]"} />
      <span className="-mt-1 text-sm font-black text-ink-chalk">{vip.name}</span>
      <span className="text-micro font-semibold text-ink-mist">{vip.emoji} {vip.title}</span>
      <span className={`mt-1 rounded-full px-2 py-0.5 text-[10px] font-bold ${vip.active ? "bg-accent-lime/15 text-accent-lime" : "bg-amber-400/15 text-amber-200"}`}>
        {vip.active ? `работает до ${until(vip.until)}` : vip.trial ? "неделя бесплатно" : `${vip.stars} ⭐ / ${vip.days} дн.`}
      </span>
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
        <StaffPortrait role={vip.role} art={vip.skin?.art} size={64} />
        <div className="min-w-0 flex-1">
          <p className="font-display text-base font-bold text-ink-chalk">{vip.emoji} {vip.title}</p>
          <p className="text-micro text-ink-mist">{vip.about}</p>
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
              <StaffPortrait role={vip.role} art={s.art} size={58} />
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
    </div>
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

// --- the club staff from «Жители города» -------------------------------------------------------

function ClubStaff({ data, onDone, onError }: { data: ManagerStaffView; onDone: (v: ManagerStaffView) => void; onError: (e: unknown) => void }) {
  const [role, setRole] = useState<ManagerStaffRole | null>(null);
  const [fire, setFire] = useState<number | null>(null);
  const hire = useMutation({
    mutationFn: ({ resident, r }: { resident: number; r: ManagerStaffRole }) => hireManagerStaff(resident, r),
    onSuccess: (v) => { setRole(null); onDone(v); }, onError,
  });
  const out = useMutation({ mutationFn: (id: number) => fireManagerStaff(id), onSuccess: onDone, onError });
  const taken = new Set(data.staff.map((s) => s.role));
  const free = data.roles.filter((r) => !taken.has(r.code));
  const roleInfo = data.roles.find((r) => r.code === role);
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="club-staff">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">🏢 Штат клуба</h2>
        <span className="rounded-full bg-bg-raised px-2 py-0.5 text-micro font-bold text-ink-mist">{data.staff.length}/{data.slots} · {eur(data.wages)}/сезон</span>
      </div>
      <p className="-mt-2 text-micro text-ink-mist">Жители твоего города на должностях. Чем реже житель, тем сильнее эффект и выше зарплата.</p>
      <div className="grid grid-cols-2 gap-2">
        {data.staff.map((s) => (
          <div key={s.id} className={`flex flex-col gap-1 rounded-xl bg-bg-raised p-2.5 ring-1 ${RARITY[s.rarity].ring}`}>
            <div className="flex items-center gap-2">
              {s.image ? <img src={staticUrl(s.image)} alt="" className="h-9 w-9 rounded-lg object-cover" /> : <span className="text-2xl">{s.icon}</span>}
              <span className="min-w-0">
                <span className="block truncate text-xs font-bold text-ink-chalk">{s.name}</span>
                <span className="block truncate text-[10px] text-ink-mist">{s.emoji} {s.role_name}</span>
              </span>
            </div>
            <span className="text-[10px] font-semibold text-accent-lime">{s.effect_text}</span>
            <div className="flex items-center justify-between text-[10px] text-ink-mist">
              <span>{eur(s.wage)}/сезон</span>
              <button onClick={() => setFire(s.id)} className="font-bold text-red-300">Уволить</button>
            </div>
          </div>
        ))}
        {data.staff.length < data.slots && free.map((r) => (
          <button key={r.code} disabled={!data.window} onClick={() => setRole(r.code)}
            className="flex flex-col items-start gap-0.5 rounded-xl border border-dashed border-white/15 p-2.5 text-left disabled:opacity-50">
            <span className="text-xs font-bold text-ink-chalk">{r.emoji} {r.name}</span>
            <span className="text-[10px] text-ink-mist">{r.effects.common === r.effects.legendary ? r.effects.common : `${r.effects.common} … ${r.effects.legendary}`}</span>
            <span className="text-[10px] font-bold text-violet-200">+ Нанять</span>
          </button>
        ))}
      </div>
      {!data.window && <p className="text-micro text-amber-200">⏳ Нанимать — в межсезонье.</p>}
      {role && roleInfo && (
        <div className="flex flex-col gap-2 rounded-xl bg-black/25 p-3" data-testid="hire-sheet">
          <div className="flex items-center justify-between">
            <p className="text-xs font-bold text-ink-chalk">{roleInfo.emoji} {roleInfo.name}: кого назначить?</p>
            <button onClick={() => setRole(null)} className="text-micro text-ink-mist">Закрыть</button>
          </div>
          {data.candidates.length === 0 && <p className="text-micro text-ink-mist">Нет свободных жителей — выбивай их в паках «Жители города».</p>}
          <div className="flex flex-col gap-1.5">
            {data.candidates.map((c) => (
              <button key={c.resident_id} disabled={hire.isPending} onClick={() => hire.mutate({ resident: c.resident_id, r: role })}
                className={`flex items-center gap-2 rounded-xl bg-bg-raised p-2 text-left ring-1 ${RARITY[c.rarity].ring}`}>
                {c.image ? <img src={staticUrl(c.image)} alt="" className="h-8 w-8 rounded-lg object-cover" /> : <span className="text-xl">{c.icon}</span>}
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-bold text-ink-chalk">{c.name}</span>
                  <span className={`block text-[10px] font-semibold ${RARITY[c.rarity].text}`}>{RARITY[c.rarity].label} · {roleInfo.effects[c.rarity]}</span>
                </span>
                <span className="shrink-0 text-[10px] text-ink-mist">{eur(c.wage)}</span>
              </button>
            ))}
          </div>
        </div>
      )}
      <ConfirmDialog open={fire !== null} title="Уволить сотрудника?" description="Житель останется в городе, должность освободится."
        confirmLabel="Уволить" onConfirm={() => { if (fire !== null) out.mutate(fire); setFire(null); }} onCancel={() => setFire(null)} />
    </section>
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
              ? <span className="flex h-12 items-end"><CarArt art={i.art} width={110} /></span>
              : <OfficeScene room={i.art} className="h-14 w-full rounded-lg" />}
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
