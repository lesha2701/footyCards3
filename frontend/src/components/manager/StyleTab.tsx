import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  buyManagerCosmetic,
  fetchManagerChampion,
  setManagerLook,
  setManagerStadiumName,
  type ManagerClub,
  type ManagerCosmetic,
  type ManagerLook,
  type ManagerView,
} from "@/api/manager";
import standsArt from "@/assets/manager/stands.webp";
import LimitedBadge from "@/components/common/LimitedBadge";
import ShareButton from "@/components/common/ShareButton";
import { IconCoin } from "@/components/icons";
import { paintCss } from "@/lib/emblemPaint";
import { FRAME_COLORS, themeClass } from "@/lib/managerLook";
import { payMyPlayerWithStars } from "@/lib/myPlayerStars";
import { hapticNotify } from "@/lib/telegram";

import Emblem, { KitShirt } from "./Emblem";
import SectionTitle from "./SectionTitle";
import Stadium from "./Stadium";

const POSTER_COLORS: Record<string, [string, string]> = { classic: ["#3ed17e", "#c6e63a"], neon: ["#d946ef", "#22d3ee"], gold: ["#d4a017", "#fad65c"] };

const SECTIONS: { kind: ManagerCosmetic["kind"]; field: keyof ManagerLook; title: string }[] = [
  { kind: "shape", field: "shape", title: "Форма эмблемы" },
  { kind: "paint", field: "color", title: "Особый цвет — на эмблему, символ и форму" },
  { kind: "symbol", field: "symbol", title: "Символ" },
  { kind: "finish", field: "finish", title: "Покрытие символа" },
  { kind: "rim", field: "rim", title: "Обводка эмблемы" },
  { kind: "fx", field: "fx", title: "Эффект эмблемы" },
  { kind: "kit", field: "kit", title: "Рисунок формы" },
  { kind: "frame", field: "frame", title: "Рамка карточек «Поделиться»" },
  { kind: "theme", field: "theme", title: "Цветовая тема клуба" },
  { kind: "stands", field: "stands", title: "Трибуны стадиона" },
  { kind: "poster", field: "poster", title: "🏆 Постер чемпиона" },
];

/** Symbols in price order (free, then coins, then Stars — new ones join their price, not
 * the end); the other kinds keep the catalog's order. */
function byPrice(kind: ManagerCosmetic["kind"], items: ManagerCosmetic[]): ManagerCosmetic[] {
  if (kind !== "symbol") return items;
  const rank = (c: ManagerCosmetic) => (c.coins === 0 && c.stars === 0 ? [0, 0] : c.coins > 0 ? [1, c.coins] : [2, c.stars]);
  return [...items].sort((x, y) => {
    const [a, b] = [rank(x), rank(y)];
    return a[0] - b[0] || a[1] - b[1];
  });
}

/** A poster style chip: the frame and the trophy colour. */
function PosterChip({ value }: { value: string }) {
  const [frame, accent] = POSTER_COLORS[value] ?? POSTER_COLORS.classic;
  return (
    <span className="flex h-12 w-10 items-center justify-center rounded-md border-[3px] bg-bg-base text-lg" style={{ borderColor: frame, color: accent }}>
      <svg viewBox="0 0 24 24" width="22" height="22" fill="currentColor" aria-hidden><path d="M6 3h12v3h3v2a5 5 0 0 1-5 5h-.3A5 5 0 0 1 13 15.9V18h3v3H8v-3h3v-2.1A5 5 0 0 1 8.3 13H8a5 5 0 0 1-5-5V6h3V3Zm0 5H5a3 3 0 0 0 1 2.2V8Zm12 0v2.2A3 3 0 0 0 19 8h-1Z" /></svg>
    </span>
  );
}

/** «Стиль» of «Менеджер»: emblem, kit, share-card frame, stadium name and
 * «Менеджер Pro». Cosmetics only — nothing here makes the club stronger. */
export default function StyleTab({ view, club, onView, onError }: {
  view: ManagerView; club: ManagerClub; onView: (v: ManagerView) => void; onError: (e: unknown) => void;
}) {
  const queryClient = useQueryClient();
  const [busy, setBusy] = useState<string | null>(null);
  const [stadium, setStadium] = useState(club.stadium_name ?? "");
  const look = useMutation({ mutationFn: (patch: Partial<ManagerLook>) => setManagerLook(patch), onSuccess: onView, onError });
  const coins = useMutation({
    mutationFn: (code: string) => buyManagerCosmetic(code), onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError,
  });
  const name = useMutation({ mutationFn: () => setManagerStadiumName(stadium), onSuccess: onView, onError });
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
  const shop = view.shop;
  const owns = (code: string) => club.owned_cosmetics.includes(code);
  const stadiumItem = shop.cosmetics.find((c) => c.kind === "stadium_name");
  // A bought «Особый цвет» goes on any colour: the emblem, its symbol and the kit.
  const paints = shop.cosmetics.filter((c) => c.kind === "paint" && c.usable).map((c) => c.value);
  const colours = [...shop.palette, ...paints];

  return (
    <div className="flex flex-col gap-4" data-testid="manager-style">
      <section className={`flex items-center gap-4 rounded-2xl bg-gradient-to-br ${themeClass(club.look.theme)} p-4`}>
        <Emblem look={club.look} size={72} />
        <KitShirt look={club.look} size={56} sponsor={club.kit_sponsor} />
        <KitShirt look={club.look} size={56} back={{ name: club.name, number: 10 }} />
        <span className="min-w-0 flex-1">
          <span className="block truncate font-display text-lg font-bold text-ink-chalk">
            {club.name}
            {club.pro && <span className="ml-1.5 rounded bg-amber-400 px-1.5 py-0.5 align-middle text-micro font-black text-bg-base">PRO</span>}
          </span>
          <span className="block truncate text-xs text-ink-mist">🏟 {club.stadium_name || "Стадион без имени"}</span>
        </span>
      </section>

      {SECTIONS.map(({ kind, field, title }) => (
        <section key={kind} className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          {kind === "stands" ? <h2><SectionTitle art={standsArt}>{title}</SectionTitle></h2>
            : <h2 className="font-display text-sm font-bold text-ink-chalk">{title}</h2>}
          {kind === "poster" && <ChampionShare titles={club.titles} />}
          <div className={`grid gap-2 ${kind === "stands" ? "grid-cols-2" : "grid-cols-3"}`}>
            {byPrice(kind, shop.cosmetics.filter((c) => c.kind === kind)).map((c) => {
              const on = club.look[field] === c.value;
              return (
                <div key={c.code} className={`flex flex-col items-center gap-1 rounded-xl p-2 ${on ? "bg-accent-lime/15 ring-2 ring-accent-lime" : "bg-bg-raised"}`}>
                  <button disabled={!c.usable || look.isPending} onClick={() => look.mutate({ [field]: c.value })}
                    className={`flex w-full items-center justify-center disabled:opacity-50 ${kind === "stands" ? "h-16" : "h-12"}`} aria-label={c.name}>
                    {kind === "stands" && <Stadium look={{ ...club.look, stands: c.value }} height={64} label={c.name} />}
                    {kind === "poster" && <PosterChip value={c.value} />}
                    {kind === "shape" && <Emblem look={{ ...club.look, shape: c.value }} size={40} />}
                    {kind === "paint" && <Emblem look={{ ...club.look, color: c.value }} size={40} />}
                    {kind === "symbol" && <Emblem look={{ ...club.look, symbol: c.value }} size={40} />}
                    {kind === "finish" && <Emblem look={{ ...club.look, finish: c.value }} size={40} />}
                    {kind === "rim" && <Emblem look={{ ...club.look, rim: c.value }} size={40} />}
                    {kind === "fx" && <Emblem look={{ ...club.look, fx: c.value }} size={40} />}
                    {kind === "kit" && <KitShirt look={{ ...club.look, kit: c.value }} size={40} />}
                    {kind === "frame" && <span className="h-10 w-8 rounded-md border-4 bg-bg-base" style={{ borderColor: FRAME_COLORS[c.value] ?? "#fff" }} />}
                    {kind === "theme" && <span className={`h-10 w-full rounded-lg bg-gradient-to-br ${themeClass(c.value)} ring-1 ring-white/10`} />}
                  </button>
                  <span className="text-center text-micro text-ink-chalk">{c.name}</span>
                  {!c.owned && <LimitedBadge until={c.limited_until} />}
                  {!c.usable && (
                    <span className="flex w-full flex-col gap-1">
                      {c.coins > 0 && (
                        <button disabled={coins.isPending} onClick={() => coins.mutate(c.code)}
                          className="flex items-center justify-center gap-1 rounded-lg bg-floodlight py-1 text-micro font-bold text-bg-base">
                          {c.coins} <IconCoin className="h-3 w-3" />
                        </button>
                      )}
                      {c.stars > 0 && (
                        <button disabled={busy === c.code} onClick={() => void stars(c.code)}
                          className="rounded-lg bg-amber-400 py-1 text-micro font-bold text-bg-base">
                          {c.stars} ⭐
                        </button>
                      )}
                    </span>
                  )}
                  {c.code === "frame_gold" && !owns(c.code) && c.usable && <span className="text-[9px] text-amber-300">с Pro</span>}
                </div>
              );
            })}
          </div>
          {kind === "shape" && (
            <Palette label="Цвета эмблемы" palette={colours} a={club.look.color} b={club.look.color2}
              onA={(color) => look.mutate({ color })} onB={(color2) => look.mutate({ color2 })} />
          )}
          {kind === "kit" && (
            <Palette label="Цвета формы" palette={colours} a={club.look.kit_color} b={club.look.kit_color2}
              onA={(kit_color) => look.mutate({ kit_color })} onB={(kit_color2) => look.mutate({ kit_color2 })} />
          )}
        </section>
      ))}

      {stadiumItem && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          <h2 className="font-display text-sm font-bold text-ink-chalk">🏟 Имя стадиона</h2>
          {owns("stadium_name") ? (
            <div className="flex gap-2">
              <input value={stadium} onChange={(e) => setStadium(e.target.value)} maxLength={32} placeholder="Victor Arena"
                className="min-w-0 flex-1 rounded-xl bg-bg-raised px-3 py-2 text-sm text-ink-chalk outline-none" />
              <button disabled={name.isPending} onClick={() => name.mutate()} className="rounded-xl bg-floodlight px-3 text-xs font-bold text-bg-base">
                Сохранить
              </button>
            </div>
          ) : (
            <button disabled={busy === "stadium_name"} onClick={() => void stars("stadium_name")}
              className="rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base">
              Купить права на имя · {stadiumItem.stars} ⭐
            </button>
          )}
          <p className="text-micro text-ink-mist">Имя видят соперники в лиге и на карточке клуба.</p>
        </section>
      )}

      <section className="flex flex-col gap-2 rounded-2xl bg-gradient-to-br from-amber-400/20 to-bg-surface p-4 ring-1 ring-amber-400/40">
        <h2 className="font-display text-base font-bold text-ink-chalk">⭐ Менеджер Pro</h2>
        <ul className="flex flex-col gap-1 text-caption text-ink-mist">
          <li>🔭 Скаут: кто на рынке дорожает быстрее всех</li>
          <li>🥇 Золотая рамка карточек «Поделиться»</li>
          <li>PRO-значок клуба в лиге и на карточке</li>
          <li className="text-micro">Без бонусов к силе — только удобство и стиль.</li>
        </ul>
        {club.pro && club.pro_until && (
          <p className="text-xs text-accent-lime">Активен до {new Date(club.pro_until).toLocaleDateString("ru-RU", { day: "numeric", month: "long" })}</p>
        )}
        {shop.pro_stars > 0 && (
          <button disabled={busy === "pro"} onClick={() => void stars("pro")} className="rounded-xl bg-amber-400 py-2.5 text-sm font-bold text-bg-base">
            {club.pro ? "Продлить" : "Подключить"} на {shop.pro_days} дн. · {shop.pro_stars} ⭐
          </button>
        )}
      </section>


      {shop.my_merch.length > 0 && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          <h2 className="font-display text-sm font-bold text-ink-chalk">Моя коллекция мерча</h2>
          <div className="flex flex-wrap gap-1.5">
            {shop.my_merch.map((m) => (
              <span key={`${m.club_name}-${m.code}`} className="rounded-lg bg-bg-raised px-2 py-1 text-micro text-ink-chalk">{m.emoji} {m.name} · {m.club_name}</span>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}

function Palette({ label, palette, a, b, onA, onB }: {
  label: string; palette: string[]; a: string; b: string; onA: (c: string) => void; onB: (c: string) => void;
}) {
  return (
    <div className="flex flex-col gap-1.5">
      <p className="text-micro text-ink-mist">{label}: основной и второй</p>
      {([[a, onA], [b, onB]] as const).map(([current, pick], row) => (
        <div key={row} className="flex flex-wrap gap-1.5">
          {palette.map((color) => (
            <button key={color} onClick={() => pick(color)} aria-label={color}
              className={`h-6 w-6 rounded-full ${current === color ? "ring-2 ring-white ring-offset-2 ring-offset-bg-surface" : ""}`}
              style={{ background: paintCss(color) }} />
          ))}
        </div>
      ))}
    </div>
  );
}

/** «Постер чемпиона»: share the last title as a picture (champions only). */
function ChampionShare({ titles }: { titles: number }) {
  const { data } = useQuery({ queryKey: ["manager", "champion"], queryFn: fetchManagerChampion, enabled: titles > 0, retry: false });
  if (!data) {
    return <p className="-mt-1 text-micro text-ink-mist">Выиграй лигу — и поделись постером чемпиона. Стиль постера выбирается здесь.</p>;
  }
  return (
    <div className="flex items-center gap-3 rounded-xl bg-amber-300/10 p-2.5 ring-1 ring-amber-300/30">
      <span className="min-w-0 flex-1 text-xs text-ink-chalk">
        🏆 Чемпион {data.league.toLowerCase()} · сезон {data.season_key}
        <span className="block text-micro text-ink-mist">{data.won}–{data.drawn}–{data.lost} · {data.points} очк.</span>
      </span>
      <ShareButton kind="manager_champion" id={0} label="Постер" compact />
    </div>
  );
}
