import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchHall, fetchPublicProfile, type Hall } from "@/api/profile";
import { RespectBar } from "@/components/profile/ProfileSocial";
import { IconChevronLeft } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { asFinish, FINISH_ICONS, FINISH_LABELS } from "@/lib/finish";
import {
  BANNER, CAB_ITEM_H, CAB_ITEM_W, CARPET, FLOOR, FRAMES, FRAME_IN_H, FRAME_IN_W, HALL_TOP, HALL_VIEW, NICHE, PEDESTALS, PILASTER, PLANT, ROPES,
  WALL_LEFT, WALL_RIGHT, cabinetSlot, rect, type Placed,
} from "@/lib/hall";
import { RARITY_LABELS } from "@/lib/rarity";
import { SPECIAL_LABELS, type SpecialSerial } from "@/lib/giftSerial";
import { useAuthStore } from "@/store/authStore";
import type { Rarity } from "@/types";

import bannerArt from "@/assets/hall/banner.webp";
import nicheArt from "@/assets/hall/cabinet_niche.webp";
import carpetArt from "@/assets/hall/carpet.webp";
import floorArt from "@/assets/hall/floor.webp";
import frameArt from "@/assets/hall/frame.webp";
import pedestalArt from "@/assets/hall/pedestal.webp";
import plantArt from "@/assets/hall/plant.webp";
import ropeArt from "@/assets/hall/rope.webp";
import spotlightArt from "@/assets/hall/spotlight.webp";
import wallLeftArt from "@/assets/hall/wall_left.webp";
import wallRightArt from "@/assets/hall/wall_right.webp";
import cupArt from "@/assets/trophies/champion.webp";

/** Trophy art by code (assets/trophies/<code>.webp), the champion cup otherwise. */
const TROPHY_ART: Record<string, string> = Object.fromEntries(
  Object.entries(import.meta.glob("../assets/trophies/*.webp", { eager: true, import: "default" }) as Record<string, string>).map(
    ([path, url]) => [path.split("/").pop()!.replace(".webp", ""), url],
  ),
);

const FRAME_COLORS: Record<Rarity, string> = {
  common: "#94a3b8", rare: "#38bdf8", epic: "#c084fc", legendary: "#facc15", diamond: "#7dd3fc",
};

type Plaque = { title: string; lines: string[]; image?: string | null };

const date = (at: string) => new Date(at).toLocaleDateString("ru-RU");

/** «Зал славы»: an isometric room — «Витрина» cards in the frames on the
 * left wall, trophies and completed collections in the cabinet on the right
 * wall, the gift shelf on the pedestals. Tap an exhibit for its plaque. */
export default function HallOfFamePage() {
  const { userId } = useParams<{ userId: string }>();
  const id = Number(userId);
  const navigate = useNavigate();
  const me = useAuthStore((s) => s.user);
  const isMe = me?.id === id;
  const { data: profile } = useQuery({ queryKey: ["public-profile", userId], queryFn: () => fetchPublicProfile(id) });
  const { data: hall } = useQuery({ queryKey: ["hall", id], queryFn: () => fetchHall(id) });
  const [plaque, setPlaque] = useState<Plaque | null>(null);
  const [arrange, setArrange] = useState(false);
  const name = profile ? [profile.first_name, profile.last_name].filter(Boolean).join(" ") || profile.username : "";

  return (
    <div className="flex flex-col gap-3">
      <button onClick={() => navigate(-1)} className="flex items-center gap-1 self-start text-sm text-accent-lime">
        <IconChevronLeft size={16} />
        Назад
      </button>
      <div className="text-center">
        <p className="text-micro font-bold uppercase tracking-[0.25em] text-amber-200/80">🏛 Зал славы</p>
        <p className="font-display text-xl font-bold text-ink-chalk">{name}</p>
      </div>

      <div className="relative overflow-hidden rounded-3xl bg-[#0c1712] ring-1 ring-amber-300/15" data-testid="hall-room">
        {hall ? <Room hall={hall} isMe={isMe} onPick={setPlaque} /> : <div className="aspect-square animate-pulse" />}
      </div>

      <section className="min-h-[84px] rounded-2xl border border-amber-300/25 bg-gradient-to-b from-amber-300/10 to-transparent p-3" data-testid="hall-plaque">
        {plaque ? (
          <div className="flex items-center gap-3">
            {plaque.image && <img src={plaque.image} className="h-14 w-14 shrink-0 rounded-xl object-cover" />}
            <div className="min-w-0">
              <p className="font-display text-sm font-bold text-amber-100">{plaque.title}</p>
              {plaque.lines.map((l, i) => (
                <p key={i} className="text-caption text-ink-mist">{l}</p>
              ))}
            </div>
          </div>
        ) : (
          <p className="pt-4 text-center text-caption text-ink-mist">
            {hall && !hall.frames.length && !hall.cabinet.length && !hall.pedestals.length
              ? isMe
                ? "Зал пока пустой: добавь карты в «Витрину», закрепи подарки — и получай трофеи"
                : "Зал пока пустой — экспонаты появятся с трофеями, подарками и картами в витрине"
              : "Нажми на экспонат — здесь появится его табличка"}
          </p>
        )}
      </section>

      {hall && (
        <div className="grid grid-cols-5 gap-1.5 text-center">
          {[
            ["🏆", hall.totals.trophies, "трофеи"],
            ["📖", hall.totals.collections, "коллекции"],
            ["🎁", hall.totals.gifts, "подарки"],
            ["✨", hall.totals.rare_prints, "редкие"],
            ["👍", hall.totals.respects, "респекты"],
          ].map(([icon, n, label]) => (
            <div key={label as string} className="rounded-xl bg-bg-surface px-1 py-2">
              <p className="text-sm font-bold text-ink-chalk">{icon} {n}</p>
              <p className="text-[10px] text-ink-mist-dim">{label}</p>
            </div>
          ))}
        </div>
      )}

      <RespectBar userId={id} isMe={isMe} />

      {isMe && (
        <button onClick={() => setArrange((v) => !v)} className="rounded-xl bg-bg-surface py-2.5 text-sm font-bold text-ink-chalk active:scale-95" data-testid="hall-arrange">
          🧩 Расставить экспонаты
        </button>
      )}
      {isMe && arrange && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3 text-caption text-ink-mist">
          <ArrangeRow icon="🖼" title="Картины на стене" text="Три карты из «Витрины» — отметь их в карточке «В витрину»." cta="К картам" onClick={() => navigate("/collection")} />
          <ArrangeRow icon="🎁" title="Постаменты" text="Закреплённые подарки, потом самые редкие номера." cta="К подаркам" onClick={() => navigate("/gifts")} />
          <ArrangeRow icon="🏆" title="Шкаф трофеев" text="Встают сами: трофеи и собранные коллекции, новые — первыми." />
        </section>
      )}
    </div>
  );
}

function ArrangeRow({ icon, title, text, cta, onClick }: { icon: string; title: string; text: string; cta?: string; onClick?: () => void }) {
  return (
    <div className="flex items-center gap-2.5">
      <span className="text-xl">{icon}</span>
      <span className="min-w-0 flex-1">
        <span className="block text-sm font-semibold text-ink-chalk">{title}</span>
        {text}
      </span>
      {cta && (
        <button onClick={onClick} className="shrink-0 rounded-full bg-floodlight px-3 py-1.5 text-micro font-bold text-bg-base active:scale-95">
          {cta}
        </button>
      )}
    </div>
  );
}

/** A placed sprite as an SVG <image> (mirrored when the placement says so). */
function Sprite({ p, src, opacity }: { p: Placed; src: string; opacity?: number }) {
  const r = rect(p);
  return (
    <image
      href={src}
      {...r}
      opacity={opacity}
      preserveAspectRatio="none"
      transform={p.flip ? `translate(${2 * r.x + r.width} 0) scale(-1 1)` : undefined}
    />
  );
}

function Room({ hall, isMe, onPick }: { hall: Hall; isMe: boolean; onPick: (p: Plaque) => void }) {
  return (
    <svg viewBox={`0 ${HALL_TOP} ${HALL_VIEW} ${HALL_VIEW - HALL_TOP}`} className="block w-full">
      <defs>
        <linearGradient id="hall-ceiling" x1="0" y1="0" x2="0" y2="1">
          <stop offset="0" stopColor="#050b08" />
          <stop offset="1" stopColor="#0c1712" />
        </linearGradient>
        <linearGradient id="hall-pilaster" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#5e4314" />
          <stop offset="0.45" stopColor="#d8b25a" />
          <stop offset="0.6" stopColor="#c89a3c" />
          <stop offset="1" stopColor="#5e4314" />
        </linearGradient>
      </defs>
      <rect width={HALL_VIEW} height={HALL_VIEW} fill="url(#hall-ceiling)" />

      {/* The room: floor, carpet, walls */}
      <Sprite p={FLOOR} src={floorArt} />
      <Sprite p={CARPET} src={carpetArt} />
      <Sprite p={WALL_LEFT} src={wallLeftArt} />
      <Sprite p={WALL_RIGHT} src={wallRightArt} />
      <rect {...PILASTER} rx="1.5" fill="url(#hall-pilaster)" />
      <Sprite p={BANNER} src={bannerArt} />

      {/* Frames on the left wall: the «Витрина» cards */}
      {FRAMES.map(({ frame, inner, lamp }, i) => {
        const card = hall.frames[i];
        const finish = card ? asFinish(card.finish) : null;
        const color = card ? FRAME_COLORS[card.player.rarity] : null;
        return (
          <g
            key={i}
            className={card ? "cursor-pointer" : undefined}
            data-testid="hall-frame"
            onClick={() =>
              card &&
              onPick({
                title: card.player.display_name,
                lines: [
                  `${RARITY_LABELS[card.player.rarity]} · рейтинг ${card.player.rating}${finish ? ` · ${FINISH_ICONS[finish]} ${FINISH_LABELS[finish]}` : ""}`,
                  `В коллекции с ${date(card.acquired_at)} · №${card.serial_number}`,
                ],
                image: staticUrl(card.player.image_path ?? undefined),
              })
            }
          >
            <Sprite p={frame} src={frameArt} />
            <g transform={`matrix(1,-0.5,0,1,${inner[0]},${inner[1]})`}>
              {card?.player.image_path ? (
                <image href={staticUrl(card.player.image_path) ?? undefined} width={FRAME_IN_W} height={FRAME_IN_H} preserveAspectRatio="xMidYMid slice" />
              ) : (
                isMe && !card && <text x={FRAME_IN_W / 2} y={FRAME_IN_H / 2 + 6} textAnchor="middle" fontSize="18" fill="#c9a24a" fillOpacity="0.7">+</text>
              )}
              {card && color && (
                <>
                  <rect x="1" y="1" width="18" height="11" rx="2" fill="#000" fillOpacity="0.65" />
                  <text x="10" y="9.5" textAnchor="middle" fontSize="8" fontWeight="800" fill={color}>{card.player.rating}</text>
                  {finish && <text x={FRAME_IN_W - 2} y="10" textAnchor="end" fontSize="8">{FINISH_ICONS[finish]}</text>}
                </>
              )}
            </g>
            <Sprite p={lamp} src={spotlightArt} opacity={card ? 1 : 0.55} />
          </g>
        );
      })}


      {/* The niche in the right wall: trophies, then collections */}
      <Sprite p={NICHE} src={nicheArt} />
      {Array.from({ length: 6 }, (_, i) => {
        const item = hall.cabinet[i];
        if (!item) return null;
        const [x, y] = cabinetSlot(i);
        const art = item.image_path ? staticUrl(item.image_path) : item.kind === "trophy" ? (TROPHY_ART[item.code ?? ""] ?? cupArt) : null;
        return (
          <g
            key={i}
            className="cursor-pointer"
            data-testid="hall-cabinet-item"
            onClick={() =>
              onPick({
                title: item.kind === "trophy" ? `${item.icon} ${item.name}` : `📖 Коллекция «${item.name}»`,
                lines: [item.description, `Получен ${date(item.at)}`].filter(Boolean),
                image: art,
              })
            }
          >
            <ellipse cx={x} cy={y} rx="11" ry="3" fill="#000" fillOpacity="0.35" />
            {art ? (
              <image href={art} x={x - CAB_ITEM_W / 2} y={y - CAB_ITEM_H} width={CAB_ITEM_W} height={CAB_ITEM_H} preserveAspectRatio="xMidYMax meet" />
            ) : (
              <text x={x} y={y - 4} textAnchor="middle" fontSize="24">{item.icon}</text>
            )}
          </g>
        );
      })}

      {/* Decor in the right corner */}
      <Sprite p={PLANT} src={plantArt} />

      {/* Pedestals on the floor: the gift shelf */}
      {PEDESTALS.map(({ sprite, top }, i) => {
        const gift = hall.pedestals[i];
        const special = gift?.special as SpecialSerial | null | undefined;
        const [x, y] = top;
        return (
          <g
            key={i}
            className={gift ? "cursor-pointer" : undefined}
            data-testid="hall-pedestal"
            onClick={() =>
              gift &&
              onPick({
                title: `🎁 ${gift.gift_set.name}`,
                lines: [
                  gift.serial_number != null ? `Экземпляр №${gift.serial_number}${special ? ` · ${SPECIAL_LABELS[special] ?? ""}` : ""}` : "Подарок",
                  gift.is_pinned ? "Закреплён владельцем" : "Один из самых редких в коллекции",
                ],
                image: staticUrl(gift.gift_set.image_path ?? undefined),
              })
            }
          >
            <Sprite p={sprite} src={pedestalArt} />
            {special && <ellipse cx={x} cy={y} rx="17" ry="7" fill="none" stroke="#fcd34d" strokeWidth="1.5" />}
            {gift ? (
              gift.gift_set.image_path ? (
                <image href={staticUrl(gift.gift_set.image_path) ?? undefined} x={x - 15} y={y - 28} width="30" height="30" preserveAspectRatio="xMidYMax meet" />
              ) : (
                <text x={x} y={y - 2} textAnchor="middle" fontSize="18">🎁</text>
              )
            ) : (
              isMe && <text x={x} y={y + 4} textAnchor="middle" fontSize="12" fill="#8a8270">+</text>
            )}
            {gift?.serial_number != null && (
              <text x={x} y={y + 22} textAnchor="middle" fontSize="6.5" fontWeight="800" fill={special ? "#7c4a03" : "#5b4a1c"}>№{gift.serial_number}</text>
            )}
          </g>
        );
      })}

      {/* Velvet ropes along the front */}
      {ROPES.map((p, i) => (
        <Sprite key={i} p={p} src={ropeArt} />
      ))}
    </svg>
  );
}
