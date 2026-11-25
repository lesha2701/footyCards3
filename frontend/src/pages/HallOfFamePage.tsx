import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate, useParams } from "react-router-dom";

import { fetchHall, fetchPublicProfile, type Hall } from "@/api/profile";
import { RespectBar } from "@/components/profile/ProfileSocial";
import { IconChevronLeft } from "@/components/icons";
import { staticUrl } from "@/lib/api";
import { asFinish, FINISH_ICONS, FINISH_LABELS } from "@/lib/finish";
import {
  CAB_COLS, CAB_H, CAB_TOP, CAB_U, CAB_W, FRAME_H, FRAME_SLOTS, FRAME_W, PEDESTALS, cabinetSlot, frameOrigin, leftWall, rightWall,
} from "@/lib/hall";
import { RARITY_LABELS } from "@/lib/rarity";
import { SPECIAL_LABELS, type SpecialSerial } from "@/lib/giftSerial";
import { useAuthStore } from "@/store/authStore";
import type { Rarity } from "@/types";

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

const pts = (list: [number, number][]) => list.map((p) => p.join(",")).join(" ");
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

function Room({ hall, isMe, onPick }: { hall: Hall; isMe: boolean; onPick: (p: Plaque) => void }) {
  const floor: [number, number][] = [[200, 200], [380, 290], [200, 380], [20, 290]];
  const lw: [number, number][] = [[200, 40], [20, 130], [20, 290], [200, 200]];
  const rw: [number, number][] = [[200, 40], [380, 130], [380, 290], [200, 200]];
  const cab: [number, number][] = [rightWall(CAB_U, CAB_TOP), rightWall(CAB_U + CAB_W, CAB_TOP), rightWall(CAB_U + CAB_W, CAB_TOP + CAB_H), rightWall(CAB_U, CAB_TOP + CAB_H)];
  return (
    <svg viewBox="0 0 400 400" className="block w-full">
      <defs>
        <linearGradient id="hall-lw" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#173226" />
          <stop offset="1" stopColor="#21412f" />
        </linearGradient>
        <linearGradient id="hall-rw" x1="0" y1="0" x2="1" y2="0">
          <stop offset="0" stopColor="#1a3628" />
          <stop offset="1" stopColor="#12281d" />
        </linearGradient>
        <radialGradient id="hall-spot" cx="0.5" cy="0" r="1">
          <stop offset="0" stopColor="#fde68a" stopOpacity="0.35" />
          <stop offset="1" stopColor="#fde68a" stopOpacity="0" />
        </radialGradient>
        <pattern id="hall-tiles" width="20" height="20" patternUnits="userSpaceOnUse" patternTransform="matrix(1,0.5,-1,0.5,0,0)">
          <rect width="20" height="20" fill="#e9dfc8" />
          <rect width="10" height="10" fill="#d9ccb0" />
          <rect x="10" y="10" width="10" height="10" fill="#d9ccb0" />
        </pattern>
      </defs>

      {/* Walls and floor */}
      <polygon points={pts(lw)} fill="url(#hall-lw)" />
      <polygon points={pts(rw)} fill="url(#hall-rw)" />
      <polyline points={pts([leftWall(180, 8), leftWall(0, 8), rightWall(180, 8)])} fill="none" stroke="#caa349" strokeWidth="1.5" />
      <polyline points={pts([leftWall(180, 140), leftWall(0, 140), rightWall(180, 140)])} fill="none" stroke="#caa349" strokeOpacity="0.5" />
      <polygon points={pts(floor)} fill="url(#hall-tiles)" />
      <polygon points={pts(floor)} fill="#000" fillOpacity="0.12" />
      <polygon points={pts([[200, 214], [236, 232], [200, 366], [164, 348]])} fill="#8f1d24" opacity="0.9" />
      <polygon points={pts([[200, 220], [228, 234], [200, 358], [172, 344]])} fill="none" stroke="#e2b85a" strokeOpacity="0.6" />
      <line x1="200" y1="40" x2="200" y2="200" stroke="#0a1a12" strokeWidth="1.5" />

      {/* Frames on the left wall: the «Витрина» cards */}
      {FRAME_SLOTS.map((slot, i) => {
        const card = hall.frames[i];
        const [x0, y0] = frameOrigin(slot.x0);
        const color = card ? FRAME_COLORS[card.player.rarity] : "#3a5a48";
        const finish = card ? asFinish(card.finish) : null;
        return (
          <g
            key={i}
            transform={`matrix(1,-0.5,0,1,${x0},${y0})`}
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
            <ellipse cx={FRAME_W / 2} cy={-14} rx="26" ry="9" fill="url(#hall-spot)" />
            <rect x="-4" y="-4" width={FRAME_W + 8} height={FRAME_H + 8} rx="2" fill={card ? "#b8902e" : "#24402f"} stroke={color} strokeWidth="2" />
            <rect x="0" y="0" width={FRAME_W} height={FRAME_H} fill="#0c1712" />
            {card?.player.image_path ? (
              <image href={staticUrl(card.player.image_path) ?? undefined} x="0" y="0" width={FRAME_W} height={FRAME_H} preserveAspectRatio="xMidYMid slice" />
            ) : (
              isMe && !card && <text x={FRAME_W / 2} y={FRAME_H / 2 + 5} textAnchor="middle" fontSize="16" fill="#4f7a62">+</text>
            )}
            {card && (
              <>
                <rect x="1" y="1" width="18" height="11" rx="2" fill="#000" fillOpacity="0.6" />
                <text x="10" y="9.5" textAnchor="middle" fontSize="8" fontWeight="800" fill={color}>{card.player.rating}</text>
                {finish && <text x={FRAME_W - 2} y="10" textAnchor="end" fontSize="8">{FINISH_ICONS[finish]}</text>}
              </>
            )}
          </g>
        );
      })}

      {/* Cabinet on the right wall: trophies, then collections */}
      <polygon points={pts(cab)} fill="#3b2414" stroke="#c99a3e" strokeWidth="2" />
      <polygon
        points={pts([rightWall(CAB_U + 5, CAB_TOP + 5), rightWall(CAB_U + CAB_W - 5, CAB_TOP + 5), rightWall(CAB_U + CAB_W - 5, CAB_TOP + CAB_H - 5), rightWall(CAB_U + 5, CAB_TOP + CAB_H - 5)])}
        fill="#1d130b"
      />
      {[58, 118].map((v) => (
        <polygon key={v} points={pts([rightWall(CAB_U + 5, CAB_TOP + v), rightWall(CAB_U + CAB_W - 5, CAB_TOP + v), rightWall(CAB_U + CAB_W - 5, CAB_TOP + v + 4), rightWall(CAB_U + 5, CAB_TOP + v + 4)])} fill="#c99a3e" />
      ))}
      {Array.from({ length: CAB_COLS * 2 }, (_, i) => {
        const [x, y] = cabinetSlot(i);
        return (
          <g key={`l${i}`}>
            <polygon points={pts([[x - 3, y - 54], [x + 3, y - 54], [x + 15, y], [x - 15, y]])} fill="#ffd98a" fillOpacity="0.07" />
            <circle cx={x} cy={y - 54} r="2" fill="#ffe8a3" />
          </g>
        );
      })}
      {Array.from({ length: CAB_COLS * 2 }, (_, i) => {
        const item = hall.cabinet[i];
        const [x, y] = cabinetSlot(i);
        if (!item) return null;
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
            {art ? (
              <image href={art} x={x - 17} y={y - 38} width="34" height="38" preserveAspectRatio="xMidYMax meet" />
            ) : (
              <text x={x} y={y - 6} textAnchor="middle" fontSize="26">{item.icon}</text>
            )}
          </g>
        );
      })}
      <polygon points={pts(cab)} fill="#bfe8ff" fillOpacity="0.06" pointerEvents="none" />

      {/* Pedestals on the floor: the gift shelf */}
      {PEDESTALS.map(([x, y], i) => {
        const gift = hall.pedestals[i];
        const special = gift?.special as SpecialSerial | null | undefined;
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
            <ellipse cx={x} cy={y + 16} rx="22" ry="10" fill="#000" fillOpacity="0.25" />
            <path d={`M${x - 18} ${y} L${x - 18} ${y + 14} A18 9 0 0 0 ${x + 18} ${y + 14} L${x + 18} ${y} Z`} fill="#cfcac0" />
            <ellipse cx={x} cy={y} rx="18" ry="9" fill="#f5f2ea" stroke={special ? "#fcd34d" : "#bdb6a6"} strokeWidth={special ? 1.5 : 0.8} />
            {gift ? (
              gift.gift_set.image_path ? (
                <image href={staticUrl(gift.gift_set.image_path) ?? undefined} x={x - 16} y={y - 30} width="32" height="32" preserveAspectRatio="xMidYMax meet" />
              ) : (
                <text x={x} y={y - 4} textAnchor="middle" fontSize="20">🎁</text>
              )
            ) : (
              isMe && <text x={x} y={y + 4} textAnchor="middle" fontSize="12" fill="#a8a092">+</text>
            )}
            {gift?.serial_number != null && (
              <text x={x} y={y + 13} textAnchor="middle" fontSize="7" fontWeight="700" fill={special ? "#a16207" : "#6b6457"}>№{gift.serial_number}</text>
            )}
          </g>
        );
      })}
    </svg>
  );
}
