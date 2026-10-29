import { useQuery } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";

import EmptyState from "@/components/common/EmptyState";
import { ListSkeleton } from "@/components/common/Skeleton";
import CardSkillBadge from "@/components/cards/CardSkillBadge";
import { IconClock, IconCoin, IconPlus, IconSearch, IconTag } from "@/components/icons";
import CardsSectionTabs from "@/components/layout/CardsSectionTabs";
import AgentBadge, { AgentIcon } from "@/components/market/AgentBadge";
import {
  fetchAuctionInfo,
  fetchAuctionLots,
  fetchMyAuctionBids,
  fetchMyAuctionLots,
  formatTimeLeft,
  LOT_STATUS_LABELS,
  serverOffsetMs,
  type AuctionLot,
  type AuctionLotFilters,
} from "@/api/auction";
import { staticUrl } from "@/lib/api";
import { useSkillCatalog } from "@/lib/cardSkills";
import { useNow } from "@/lib/useNow";
import { POSITION_LABELS, RARITY_LABELS, RARITY_TEXT } from "@/lib/rarity";
import type { Rarity } from "@/types";

type Tab = "market" | "lots" | "bids";

const SORTS: { value: NonNullable<AuctionLotFilters["sort"]>; label: string }[] = [
  { value: "ending", label: "Скоро конец" },
  { value: "newest", label: "Новые" },
  { value: "price_asc", label: "Дешевле" },
  { value: "price_desc", label: "Дороже" },
];

const PAGE = 30;
const POLL_MS = 10_000;

export default function MarketPage() {
  const navigate = useNavigate();
  const [params, setParams] = useSearchParams();
  const tab = (params.get("tab") as Tab) || "market";
  const setTab = (t: Tab) => setParams(t === "market" ? {} : { tab: t }, { replace: true });

  const { data: info } = useQuery({ queryKey: ["auction", "info"], queryFn: fetchAuctionInfo });

  return (
    <div className="flex flex-col gap-4">
      <div className="flex items-center justify-between">
        <h1 className="font-display text-xl font-bold text-ink-chalk">Трансферный рынок</h1>
        {info?.enabled && (
          <button
            onClick={() => navigate(info.license.active ? "/market/new" : "/market/license")}
            className="flex items-center gap-1 rounded-full bg-floodlight px-4 py-2 text-xs font-bold text-bg-base active:scale-95"
          >
            <IconPlus size={13} />
            Выставить
          </button>
        )}
      </div>

      <CardsSectionTabs />

      {info && !info.enabled && (
        <p className="rounded-xl bg-white/5 px-3 py-2 text-sm text-ink-mist">
          Рынок сейчас закрыт: новые лоты и ставки недоступны. Свои лоты без ставок можно снять.
        </p>
      )}
      {info?.enabled && !info.license.active && (
        <button
          onClick={() => navigate("/market/license")}
          className="flex items-center gap-3 rounded-2xl bg-amber-400/10 p-3 text-left active:scale-[0.99]"
        >
          <AgentIcon size={32} />
          <span className="flex-1 text-caption text-ink-mist">
            <b className="text-amber-300">Выставлять на рынок могут только агенты.</b> Купи «Агентскую лицензию» за{" "}
            {info.license.stars} ⭐ на {info.license.days} дн. Ставить и покупать можно и без неё.
          </span>
        </button>
      )}
      {info?.enabled && info.license.active && info.license.expires_at && (
        <button onClick={() => navigate("/market/license")} className="flex items-center gap-2 text-caption text-ink-mist-dim">
          <AgentBadge /> лицензия до {new Date(info.license.expires_at).toLocaleDateString("ru-RU")}
        </button>
      )}
      {info?.enabled && info.restriction && (
        <p className="rounded-xl bg-amber-500/10 px-3 py-2 text-sm text-amber-300">{info.restriction}</p>
      )}

      <div className="flex gap-2">
        <TabButton active={tab === "market"} label="Рынок" onClick={() => setTab("market")} />
        <TabButton active={tab === "lots"} label="Мои лоты" onClick={() => setTab("lots")} />
        <TabButton active={tab === "bids"} label="Мои ставки" onClick={() => setTab("bids")} />
      </div>

      {tab === "market" && <MarketList />}
      {tab === "lots" && <MyList kind="lots" />}
      {tab === "bids" && <MyList kind="bids" />}

      {info && (
        <p className="text-caption text-ink-mist-dim">
          Комиссия рынка {info.fee_pct}% сгорает с каждой продажи. Ставка сразу списывается с баланса и возвращается, если её
          перебьют. Ставка в последние {Math.round(info.snipe_window_seconds / 60)} мин продлевает торги.
        </p>
      )}
    </div>
  );
}

function MarketList() {
  const navigate = useNavigate();
  const [search, setSearch] = useState("");
  const [debounced, setDebounced] = useState("");
  const [rarity, setRarity] = useState("");
  const [position, setPosition] = useState("");
  const [skill, setSkill] = useState("");
  const [minStars, setMinStars] = useState(0);
  const [minPrice, setMinPrice] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [sort, setSort] = useState<NonNullable<AuctionLotFilters["sort"]>>("ending");
  const [showFilters, setShowFilters] = useState(false);
  const [limit, setLimit] = useState(PAGE);
  const skills = useSkillCatalog().data?.skills;

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(search.trim()), 350);
    return () => window.clearTimeout(id);
  }, [search]);

  const filters: AuctionLotFilters = {
    search: debounced || undefined,
    rarity: rarity || undefined,
    position: position || undefined,
    skill: skill || undefined,
    min_stars: minStars || undefined,
    min_price: minPrice ? Number(minPrice) : undefined,
    max_price: maxPrice ? Number(maxPrice) : undefined,
    sort,
    limit,
  };
  const { data, isLoading } = useQuery({
    queryKey: ["auction", "lots", filters],
    queryFn: () => fetchAuctionLots(filters),
    refetchInterval: POLL_MS,
    placeholderData: (prev) => prev,
  });
  const activeFilters = [rarity, position, skill, minStars, minPrice, maxPrice].filter(Boolean).length;
  const now = useNow();

  const selectClass = "w-full rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-chalk outline-none";

  return (
    <div className="flex flex-col gap-3">
      <div className="flex gap-2">
        <div className="flex flex-1 items-center gap-2 rounded-xl bg-bg-surface px-3">
          <IconSearch size={14} className="text-ink-mist-dim" />
          <input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder="Игрок..."
            className="w-full bg-transparent py-2.5 text-sm text-ink-chalk placeholder:text-ink-mist-dim outline-none"
          />
        </div>
        <button
          onClick={() => setShowFilters((v) => !v)}
          className={`rounded-xl px-3 text-xs font-semibold ${showFilters || activeFilters ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
        >
          Фильтры{activeFilters ? ` · ${activeFilters}` : ""}
        </button>
      </div>

      {showFilters && (
        <div className="grid grid-cols-2 gap-2 rounded-2xl bg-white/5 p-3">
          <select value={rarity} onChange={(e) => setRarity(e.target.value)} className={selectClass} aria-label="Редкость">
            <option value="">Любая редкость</option>
            {(Object.keys(RARITY_LABELS) as Rarity[]).map((r) => (
              <option key={r} value={r}>{RARITY_LABELS[r]}</option>
            ))}
          </select>
          <select value={position} onChange={(e) => setPosition(e.target.value)} className={selectClass} aria-label="Позиция">
            <option value="">Любая позиция</option>
            {Object.entries(POSITION_LABELS).map(([code, label]) => (
              <option key={code} value={code}>{code} — {label}</option>
            ))}
          </select>
          <select value={skill} onChange={(e) => setSkill(e.target.value)} className={selectClass} aria-label="Навык">
            <option value="">Навык: не важен</option>
            <option value="any">С любым навыком</option>
            {skills?.map((s) => (
              <option key={s.code} value={s.code}>{s.icon} {s.name}</option>
            ))}
          </select>
          <select value={minStars} onChange={(e) => setMinStars(Number(e.target.value))} className={selectClass} aria-label="Звёзды">
            <option value={0}>Звёзды: любые</option>
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>от {"★".repeat(n)}</option>
            ))}
          </select>
          <input
            inputMode="numeric"
            value={minPrice}
            onChange={(e) => setMinPrice(e.target.value.replace(/\D/g, ""))}
            placeholder="Цена от"
            className={selectClass}
          />
          <input
            inputMode="numeric"
            value={maxPrice}
            onChange={(e) => setMaxPrice(e.target.value.replace(/\D/g, ""))}
            placeholder="Цена до"
            className={selectClass}
          />
          {activeFilters > 0 && (
            <button
              onClick={() => { setRarity(""); setPosition(""); setSkill(""); setMinStars(0); setMinPrice(""); setMaxPrice(""); }}
              className="col-span-2 rounded-xl bg-white/5 py-2 text-xs text-ink-mist"
            >
              Сбросить фильтры
            </button>
          )}
        </div>
      )}

      <div className="flex gap-1 overflow-x-auto">
        {SORTS.map((s) => (
          <button
            key={s.value}
            onClick={() => setSort(s.value)}
            className={`shrink-0 rounded-full px-3 py-1 text-caption font-semibold ${sort === s.value ? "bg-white/15 text-ink-chalk" : "text-ink-mist-dim"}`}
          >
            {s.label}
          </button>
        ))}
      </div>

      {isLoading && <ListSkeleton />}
      {data && !data.items.length && (
        <EmptyState icon={IconTag} title="Лотов нет" description="Попробуй изменить фильтры или выставь свою карточку" />
      )}
      <div className="flex flex-col gap-2">
        {data?.items.map((lot) => (
          <LotRow key={lot.id} lot={lot} now={now} onOpen={() => navigate(`/market/${lot.id}`)} />
        ))}
      </div>
      {data && data.total > data.items.length && (
        <button onClick={() => setLimit((l) => l + PAGE)} className="rounded-xl bg-white/5 py-2.5 text-xs font-semibold text-ink-mist">
          Показать ещё ({data.total - data.items.length})
        </button>
      )}
    </div>
  );
}

function MyList({ kind }: { kind: "lots" | "bids" }) {
  const navigate = useNavigate();
  const { data, isLoading } = useQuery({
    queryKey: ["auction", kind === "lots" ? "my-lots" : "my-bids"],
    queryFn: kind === "lots" ? fetchMyAuctionLots : fetchMyAuctionBids,
    refetchInterval: POLL_MS,
  });
  const now = useNow();
  if (isLoading) return <ListSkeleton />;
  if (!data?.length) {
    return kind === "lots"
      ? <EmptyState icon={IconTag} title="Лотов пока нет" description="Выставь карточку — её смогут купить другие игроки" />
      : <EmptyState icon={IconCoin} title="Ставок пока нет" description="Найди карточку на рынке и сделай ставку" />;
  }
  return (
    <div className="flex flex-col gap-2">
      {data.map((lot) => (
        <LotRow key={lot.id} lot={lot} now={now} onOpen={() => navigate(`/market/${lot.id}`)} showStatus />
      ))}
    </div>
  );
}

export function LotRow({ lot, now, onOpen, showStatus = false }: { lot: AuctionLot; now: number; onOpen: () => void; showStatus?: boolean }) {
  const p = lot.card.player;
  const offset = serverOffsetMs(lot.server_now);
  const left = new Date(lot.ends_at).getTime() - (now + offset);
  const price = lot.current_bid ?? lot.start_price;
  const active = lot.status === "active";

  let tag: { text: string; className: string } | null = null;
  if (active && lot.i_am_leading) tag = { text: "Ты лидер", className: "bg-accent-green/20 text-accent-green" };
  else if (active && lot.my_max_bid && !lot.i_am_leading) tag = { text: "Перебили", className: "bg-red-500/20 text-red-300" };
  else if (lot.i_won) tag = { text: "Выигран", className: "bg-accent-green/20 text-accent-green" };
  else if (showStatus && !active) tag = { text: LOT_STATUS_LABELS[lot.status], className: "bg-white/5 text-ink-mist-dim" };

  return (
    <button onClick={onOpen} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-3 text-left active:scale-[0.99]">
      <img
        decoding="async"
        loading="lazy"
        src={staticUrl(p.image_path ?? undefined) ?? staticUrl("players/placeholder/player_placeholder.webp")}
        alt={p.display_name}
        className="h-14 w-14 shrink-0 rounded-xl object-cover"
      />
      <div className="min-w-0 flex-1">
        <p className="flex items-center gap-1 truncate text-sm font-semibold text-ink-chalk">
          <span className="truncate">{p.display_name}</span>
          <CardSkillBadge code={lot.card.skill_code} level={lot.card.skill_level} />
        </p>
        <p className="text-caption text-ink-mist">
          <span className={RARITY_TEXT[p.rarity]}>{RARITY_LABELS[p.rarity]}</span> · {p.position} · {p.rating}
          {lot.card.stars ? ` · ${"★".repeat(lot.card.stars)}` : ""} · #{lot.card.serial_number}
        </p>
        <p className="mt-0.5 flex items-center gap-1 text-caption text-ink-mist-dim">
          <IconClock size={10} />
          {active ? formatTimeLeft(left) : LOT_STATUS_LABELS[lot.status]}
          {lot.bid_count > 0 && ` · ставок: ${lot.bid_count}`}
        </p>
      </div>
      <div className="flex shrink-0 flex-col items-end gap-1">
        <span className="flex items-center gap-0.5 font-mono text-sm font-bold text-accent-lime">
          {(lot.final_price ?? price).toLocaleString("ru-RU")}
          <IconCoin size={11} />
        </span>
        {active && lot.buy_now_price && (
          <span className="text-micro text-ink-mist-dim">сразу {lot.buy_now_price.toLocaleString("ru-RU")}</span>
        )}
        {tag && <span className={`rounded-full px-2 py-0.5 text-micro font-semibold ${tag.className}`}>{tag.text}</span>}
      </div>
    </button>
  );
}

function TabButton({ active, label, onClick }: { active: boolean; label: string; onClick: () => void }) {
  return (
    <button
      onClick={onClick}
      className={`flex-1 rounded-xl py-2 text-xs font-semibold ${active ? "bg-floodlight text-bg-base" : "bg-white/5 text-ink-mist"}`}
    >
      {label}
    </button>
  );
}
