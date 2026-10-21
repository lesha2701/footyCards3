import { keepPreviousData, useInfiniteQuery, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState, type ReactNode } from "react";
import { useNavigate } from "react-router-dom";

import {
  cancelManagerOffer,
  endManagerContract,
  fetchManager,
  fetchManagerCatalog,
  fetchManagerMarket,
  fetchManagerPopular,
  fetchManagerScout,
  foundManagerClub,
  offerManagerContract,
  releaseManagerNpc,
  respondManagerOffer,
  setManagerMarket,
  signManagerNpc,
  updateManagerClub,
  type ManagerCatalogFilter,
  type ManagerCatalogPlayer,
  type ManagerClub,
  type ManagerLeague,
  type ManagerLine,
  type ManagerMarketPlayer,
  type ManagerView,
} from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import EmptyState from "@/components/common/EmptyState";
import ShareButton from "@/components/common/ShareButton";
import { ListSkeleton } from "@/components/common/Skeleton";
import { IconCoin, IconProfile, IconSearch, IconTrophy } from "@/components/icons";
import ClubCardSheet from "@/components/manager/ClubCardSheet";
import Emblem, { KitShirt } from "@/components/manager/Emblem";
import ManagerPitch from "@/components/manager/ManagerPitch";
import StyleTab from "@/components/manager/StyleTab";
import TacticsPanel from "@/components/manager/TacticsPanel";
import { formatGameError } from "@/lib/errors";
import { themeClass } from "@/lib/managerLook";
import { eur, trend } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";

const LINE_LABEL: Record<ManagerLine, string> = { GK: "Вратари", DEF: "Защита", MID: "Полузащита", FWD: "Атака" };

function when(iso: string | null): string {
  if (!iso) return "";
  const d = new Date(iso);
  return `${d.toLocaleDateString("ru-RU", { weekday: "short", day: "numeric", month: "short" })} в ${d.toLocaleTimeString("ru-RU", { hour: "2-digit", minute: "2-digit" })}`;
}

function Coins({ n, className = "" }: { n: number; className?: string }) {
  return <span className={`inline-flex items-center gap-1 whitespace-nowrap ${className}`}>{n.toLocaleString("ru-RU")} <IconCoin className="h-3.5 w-3.5 shrink-0" /></span>;
}

function Trend({ pct }: { pct: number | null | undefined }) {
  if (!pct) return null;
  return <span className={`text-micro font-bold ${pct >= 0 ? "text-emerald-400" : "text-red-400"}`}>{trend(pct)}</span>;
}

type Tab = "club" | "transfers" | "league" | "me" | "style";

/** «Менеджер»: your own club — your «Мой игрок» and an academy card always
 * start, other users' players (transfers, loans, contracts for seasons) and
 * catalog footballers; club money in euros; a 10-division pyramid with weekly
 * seasons (preseason transfer window + 15 rounds). */
export default function ManagerPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data, isLoading } = useQuery({ queryKey: ["manager"], queryFn: fetchManager, refetchInterval: 60_000 });
  const [tab, setTab] = useState<Tab>("club");
  const [error, setError] = useState<string | null>(null);
  const onView = (v: ManagerView) => { setError(null); queryClient.setQueryData(["manager"], v); updateBalance(v.balance); };
  const onError = (err: unknown) => setError(formatGameError(err, "Не получилось"));

  if (isLoading || !data) return <ListSkeleton />;
  if (!data.enabled) return <EmptyState icon={IconTrophy} title="«Менеджер» скоро вернётся" />;
  if (!data.has_player) {
    return (
      <EmptyState
        icon={IconProfile}
        title="Сначала создай своего игрока"
        description="«Мой игрок» — первый футболист твоего клуба, а ещё его могут купить другие менеджеры."
        action={<button onClick={() => navigate("/my-player")} className="rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base">Создать игрока</button>}
      />
    );
  }

  const club = data.club;
  const tabs: [Tab, string, boolean][] = [
    ["club", "Мой клуб", !!club && club.incoming.length > 0],
    ["transfers", "Трансферы", false],
    ["league", "Лига", false],
    ["me", "Я игрок", data.offers.length > 0],
    ...(club ? [["style", "Стиль", false] as [Tab, string, boolean]] : []),
  ];
  const props = { view: data, onView, onError };
  return (
    <div className="flex flex-col gap-4" data-testid="manager-page">
      <h1 className="font-display text-xl font-bold text-ink-chalk">Менеджер</h1>
      <SeasonBanner view={data} />
      {error && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{error}</p>}
      <div className="-mx-4 flex gap-1.5 overflow-x-auto px-4 pb-1">
        {tabs.map(([id, label, dot]) => (
          <button
            key={id}
            onClick={() => setTab(id)}
            className={`relative shrink-0 rounded-full px-3.5 py-2 text-xs font-semibold ${tab === id ? "bg-floodlight text-bg-base" : "bg-bg-surface text-ink-mist"}`}
          >
            {label}
            {dot && tab !== id && <span className="absolute right-1 top-1 h-2 w-2 rounded-full bg-accent-lime" />}
          </button>
        ))}
      </div>
      {tab === "club" && (club ? <ClubTab {...props} club={club} /> : <FoundClub {...props} />)}
      {tab === "transfers" && (club ? <TransfersTab {...props} club={club} /> : (
        <EmptyState icon={IconProfile} title="Сначала основай клуб" description="На рынке — «Мои игроки» других пользователей и футболисты игры." />
      ))}
      {tab === "league" && <LeagueTab view={data} onError={onError} />}
      {tab === "me" && <MeTab {...props} />}
      {tab === "style" && club && <StyleTab {...props} club={club} />}
    </div>
  );
}

interface TabProps {
  view: ManagerView;
  onView: (v: ManagerView) => void;
  onError: (err: unknown) => void;
}

function SeasonBanner({ view }: { view: ManagerView }) {
  const playing = view.club?.playing;
  const pre = view.season.phase === "preseason" && !playing;
  const slots = view.season.slots.join(", ");
  return (
    <section className={`flex items-center gap-3 rounded-2xl p-3 ${pre ? "bg-accent-lime/15 ring-1 ring-accent-lime/40" : "bg-bg-surface"}`} data-testid="season-banner">
      <span className="text-2xl">{pre ? "🔁" : "⚽"}</span>
      <span className="min-w-0 flex-1 text-xs text-ink-mist">
        {pre ? (
          <><b className="block text-sm text-ink-chalk">Трансферное окно открыто</b>Закрывается {when(view.season.preseason_ends_at)}, первый тур — {when(view.season.first_round_at)}. Успей собрать состав</>
        ) : playing ? (
          <><b className="block text-sm text-ink-chalk">Идёт сезон · {view.season.rounds} туров</b>По 3 тура в день ({slots}). Трансферы — в предсезонку</>
        ) : (
          <><b className="block text-sm text-ink-chalk">Межсезонье</b>Трансферы открыты до {when(view.season.preseason_ends_at)}, первый тур — {when(view.season.first_round_at)}</>
        )}
      </span>
    </section>
  );
}

function FoundClub({ view, onView, onError }: TabProps) {
  const [name, setName] = useState("");
  const found = useMutation({ mutationFn: () => foundManagerClub(name), onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError });
  const rules = view.rules;
  const canFound = view.level >= rules.min_level;
  const bottom = view.pyramid[view.pyramid.length - 1];
  return (
    <div className="flex flex-col gap-4">
      <section className="rounded-2xl bg-gradient-to-br from-accent-lime/20 via-bg-surface to-bg-surface p-4">
        <p className="font-display text-lg font-bold text-ink-chalk">🏟 Свой клуб</p>
        <ul className="mt-2 flex flex-col gap-1.5 text-caption text-ink-mist">
          <li>⭐ Твой «Мой игрок» и игрок академии — всегда в стартовом составе.</li>
          <li>🤝 До {rules.max_live} «Моих игроков» других пользователей: подписывай свободных, покупай и бери в аренду у других клубов.</li>
          <li>📋 Остальных ищи среди футболистов игры: покупка на 1–3 сезона или аренда на сезон.</li>
          <li>💶 Бюджет в евро: грант дивизиона + «Клубная база» (стадион, маркетинг, магазин, бухгалтерия).</li>
          <li>🏆 {rules.divisions} дивизионов. Старт — {bottom?.name}, за сезон можно подняться на один. Сезон — неделя, {rules.rounds} туров.</li>
        </ul>
      </section>
      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">Основать клуб</h2>
        <input
          value={name}
          onChange={(e) => setName(e.target.value)}
          maxLength={32}
          placeholder="Название клуба"
          className="rounded-xl bg-bg-raised px-3 py-2.5 text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim"
        />
        {!canFound && <p className="text-caption text-amber-300">Нужен {rules.min_level} уровень «Моего игрока» (сейчас {view.level})</p>}
        <button
          disabled={!canFound || name.trim().length < 3 || found.isPending}
          onClick={() => found.mutate()}
          className="flex items-center justify-center gap-1.5 rounded-2xl bg-floodlight py-3 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          Основать за <Coins n={rules.found_cost} />
        </button>
      </section>
    </div>
  );
}

// --- club ---------------------------------------------------------------------------

function ClubTab({ view, club, onView, onError }: TabProps & { club: ManagerClub }) {
  const [confirm, setConfirm] = useState<{ title: string; text: string; run: () => void } | null>(null);
  const patch = useMutation({ mutationFn: updateManagerClub, onSuccess: onView, onError });
  const release = useMutation({ mutationFn: (id: number) => endManagerContract(id), onSuccess: onView, onError });
  const cancel = useMutation({ mutationFn: (id: number) => cancelManagerOffer(id), onSuccess: onView, onError });
  const respond = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) => respondManagerOffer(id, accept), onSuccess: onView, onError,
  });
  const sellNpc = useMutation({ mutationFn: (id: number) => releaseManagerNpc(id), onSuccess: onView, onError });
  const locked = club.playing;
  const rules = view.rules;
  const base = club.base;
  return (
    <div className="flex flex-col gap-4" data-testid="manager-club">
      <section className={`rounded-2xl bg-gradient-to-br ${themeClass(club.look.theme)} p-4`}>
        <div className="flex items-center gap-3">
          <Emblem look={club.look} size={56} />
          <span className="min-w-0 flex-1">
            <span className="flex items-center gap-1.5">
              <span className="truncate font-display text-lg font-bold text-ink-chalk">{club.name}</span>
              {club.pro && <span className="rounded bg-amber-400 px-1.5 py-0.5 text-micro font-black text-bg-base">PRO</span>}
            </span>
            <span className="block text-xs text-ink-mist">
              {club.division_name} · сезонов {club.seasons_played}{club.titles > 0 && <> · 🏆 {club.titles}</>}
            </span>
            {club.stadium_name && <span className="block truncate text-xs text-ink-mist">🏟 {club.stadium_name}</span>}
          </span>
          <KitShirt look={club.look} size={36} />
        </div>
        <div className="mt-3 grid grid-cols-3 gap-2 text-center">
          <Stat label="бюджет" value={<span className="text-accent-lime">{eur(club.budget)}</span>} />
          <Stat label="рейтинг состава" value={club.squad.rating} />
          <Stat label="стоимость состава" value={eur(club.squad_value)} />
        </div>
        <div className="mt-3 rounded-xl bg-bg-base/40 p-3 text-micro text-ink-mist">
          <p className="mb-1 text-xs font-bold text-ink-chalk">Бюджет на сезон: {eur(club.next_grant.total)}</p>
          <p>Грант {club.division_name.toLowerCase()} {eur(club.next_grant.grant)} + «Клубная база» {eur(club.next_grant.bonus)}
            {club.next_grant.bonus < club.next_grant.bonus_raw && " (потолок)"}</p>
          <p>🏟 Стадион ур. {base.stadium}: {eur(club.ticket_per_home_match)} за домашний матч · 📣 маркетинг ур. {base.marketing} · 👕 магазин ур. {base.shop}
            {base.discount_pct > 0 && ` · 🧮 −${base.discount_pct}% к зарплатам`}</p>
          <p>Зарплаты за сезон: {eur(club.wages_per_season)}. Мерч болельщиков в этом сезоне: {eur(club.merch.eur_season)}.</p>
        </div>
      </section>

      <ManagerPitch xi={club.squad.xi} formation={club.squad.formation} />
      {club.squad.kids > 0 && (
        <p className="-mt-2 rounded-xl bg-amber-400/10 px-3 py-2 text-caption text-amber-300">
          {club.squad.kids} мест пустует. Не успеешь — при старте сезона система сама возьмёт в аренду средних футболистов на эти места.
        </p>
      )}
      {club.squad.bench.length > 0 && (
        <section className="rounded-2xl bg-bg-surface p-3">
          <p className="mb-1.5 text-micro font-bold uppercase tracking-wide text-ink-mist">Запас</p>
          <div className="flex flex-wrap gap-1.5">
            {club.squad.bench.map((p) => (
              <span key={p.key} className="rounded-lg bg-bg-raised px-2 py-1 text-micro text-ink-chalk">{p.position} {p.name} · <b>{p.rating}</b></span>
            ))}
          </div>
        </section>
      )}

      {club.incoming.length > 0 && (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 ring-1 ring-accent-lime/50">
          <h2 className="font-display text-base font-bold text-ink-chalk">💰 Запросы на твоих игроков</h2>
          {club.incoming.map((o) => (
            <div key={o.id} className="flex flex-col gap-2 rounded-xl bg-bg-raised p-3">
              <p className="text-sm text-ink-chalk">
                «{o.club_name}» хочет <b>{o.player_name}</b> {o.kind === "loan" ? "в аренду на сезон" : "насовсем"} за <b>{eur(o.fee)}</b>
              </p>
              <p className="text-micro text-ink-mist">
                Стоимость игрока {eur(o.value ?? 0)} · {o.player_agreed ? "игрок уже согласен" : "игрок ещё не ответил"}
              </p>
              {o.club_agreed ? (
                <p className="text-micro text-accent-lime">Ты согласился — ждём игрока</p>
              ) : locked ? (
                <p className="text-micro text-amber-300">Ответить можно в предсезонку</p>
              ) : (
                <div className="grid grid-cols-2 gap-2">
                  <button disabled={respond.isPending} onClick={() => respond.mutate({ id: o.id, accept: true })} className="rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base">Отпустить</button>
                  <button disabled={respond.isPending} onClick={() => respond.mutate({ id: o.id, accept: false })} className="rounded-lg bg-bg-surface py-2 text-xs text-ink-mist">Отказать</button>
                </div>
              )}
            </div>
          ))}
        </section>
      )}

      <TacticsPanel
        style={club.style} formation={club.formation} rules={rules.tactics} busy={patch.isPending} onChange={(p) => patch.mutate(p)}
        next={club.next_match && {
          ...club.next_match,
          detail: [club.next_match.owner_name, club.next_match.rating != null ? `рейтинг ${club.next_match.rating}` : null].filter(Boolean).join(" · "),
        }}
        note="Тактику можно менять и во время сезона — она действует со следующего тура."
        help={<>
          <p>1. <b className="text-ink-chalk">Состав.</b> 11 игроков по схеме: твой «Мой игрок» и игрок академии всегда в старте, остальные — сильнейшие по позиции. Игрок не на своей позиции играет слабее.</p>
          <p>2. <b className="text-ink-chalk">Тактика.</b> Стиль даёт % к рейтингу своих линий, схема — небольшой крен в атаку или защиту. Если твой стиль бьёт стиль соперника, все твои игроки получают +{rules.tactics.edge_pct}%.</p>
          <p>3. <b className="text-ink-chalk">Игра.</b> Движок разыгрывает владение и моменты: полузащита борется за мяч, нападающие — с защитниками в дуэлях, удары — против вратаря. Чем выше рейтинги в нужной зоне, тем больше и опаснее моменты. Навыки и артефакты «Моих игроков» тоже работают.</p>
          <p>4. <b className="text-ink-chalk">Случай.</b> Футбол есть футбол: слабый иногда побеждает, но на дистанции сезона решает сила и тактика.</p>
          <p>5. <b className="text-ink-chalk">Итог.</b> 3 очка за победу, 1 за ничью. Клуб получает € за результат и билеты на домашних матчах, «Мои игроки» — опыт и статистику для «Золотого мяча».</p>
        </>}
      />

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">🎓 Игрок академии</h2>
        <p className="-mt-1 text-micro text-ink-mist">Всегда в стартовом составе, как и твой «Мой игрок».</p>
        {club.academy_options.length === 0 ? (
          <p className="text-caption text-ink-mist">В коллекции нет карточек «Академии». Они выпадают в паке «Академия».</p>
        ) : (
          <div className="flex flex-col gap-1.5">
            {club.academy_options.map((o) => {
              const on = club.academy_card_id === o.card_id;
              return (
                <button key={o.card_id} disabled={locked || patch.isPending}
                  onClick={() => patch.mutate(on ? { clear_academy: true } : { academy_card_id: o.card_id })}
                  className={`flex items-center gap-2 rounded-xl p-2.5 text-left disabled:opacity-60 ${on ? "bg-violet-400/15 ring-2 ring-violet-400" : "bg-bg-raised"}`}>
                  <span className="w-10 font-mono text-micro text-ink-mist">{o.position}</span>
                  <span className="min-w-0 flex-1 truncate text-sm text-ink-chalk">{o.name}</span>
                  <b className="text-sm text-violet-300">{o.rating}</b>
                  <span className="w-5 text-right text-xs text-violet-300">{on ? "✓" : ""}</span>
                </button>
              );
            })}
          </div>
        )}
      </section>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">🤝 Игроки пользователей · {club.live_count}/{rules.max_live}</h2>
        {club.contracts.length === 0 && club.offers_sent.length === 0 && (
          <p className="text-caption text-ink-mist">Пока никого. Ищи во вкладке «Трансферы».</p>
        )}
        {club.contracts.map((c) => (
          <div key={c.id} className="flex flex-col gap-2 rounded-xl bg-bg-raised p-2.5">
            <div className="flex items-center gap-2">
              <span className="min-w-0 flex-1">
                <span className="block truncate text-sm font-semibold text-ink-chalk">
                  {c.player_name} <span className="font-normal text-ink-mist">· {c.position} · {c.rating}</span>
                  {c.kind === "loan" && <span className="ml-1 rounded bg-white/10 px-1 text-micro text-ink-mist">аренда</span>}
                  {c.status === "on_loan" && <span className="ml-1 rounded bg-white/10 px-1 text-micro text-ink-mist">в аренде</span>}
                </span>
                <span className="block truncate text-micro text-ink-mist">
                  {c.owner_name} · {eur(c.value ?? 0)} · {c.wage} мон./сезон · сезонов {c.seasons_left} · ⚽ {c.goals} 🅰️ {c.assists}
                </span>
              </span>
              {!locked && c.status === "active" && (
                <button onClick={() => setConfirm({ title: `Отпустить ${c.player_name}?`, text: "Контракт будет расторгнут, игрок станет свободным.", run: () => release.mutate(c.id) })}
                  className="shrink-0 rounded-lg bg-bg-surface px-2.5 py-1.5 text-micro text-ink-mist">Отпустить</button>
              )}
            </div>
            {c.status === "active" && <ShareButton kind="manager_transfer" id={c.id} label="Here we go! — поделиться" compact />}
          </div>
        ))}
        {club.offers_sent.map((c) => (
          <div key={c.id} className="flex items-center gap-2 rounded-xl border border-dashed border-white/10 p-2.5">
            <span className="min-w-0 flex-1 text-micro text-ink-mist">
              ✉️ <b className="text-ink-chalk">{c.player_name}</b> · {c.kind === "sign" ? "контракт" : c.kind === "loan" ? "аренда" : "трансфер"}
              {c.fee > 0 && <> за {eur(c.fee)}</>} · {c.wage} мон./сезон × {c.seasons_total}
              <span className="block">
                {c.kind !== "sign" && (c.club_agreed ? "клуб согласен ✓" : "ждём клуб")}{c.kind !== "sign" && " · "}{c.player_agreed ? "игрок согласен ✓" : "ждём игрока"}
              </span>
            </span>
            <button onClick={() => cancel.mutate(c.id)} className="shrink-0 text-micro text-ink-mist underline">Отозвать</button>
          </div>
        ))}
      </section>

      <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
        <h2 className="font-display text-base font-bold text-ink-chalk">📋 Футболисты</h2>
        {club.npcs.length === 0 && <p className="text-caption text-ink-mist">Купи или арендуй во вкладке «Трансферы».</p>}
        {club.npcs.map((n) => (
          <div key={n.id} className="flex items-center gap-2 rounded-xl bg-bg-raised p-2.5">
            <span className="w-9 font-mono text-micro text-ink-mist">{n.position}</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm text-ink-chalk">
                {n.name}
                <span className="ml-1 rounded bg-white/10 px-1 text-micro text-ink-mist">{n.kind === "loan" ? (n.auto ? "авто-аренда" : "аренда") : `контракт ${n.seasons_left} сез.`}</span>
              </span>
              <span className="block text-micro text-ink-mist">{eur(n.value)} · зарплата {eur(n.wage)}/сезон{n.goals > 0 && ` · ⚽ ${n.goals}`}</span>
            </span>
            <b className="text-sm text-ink-chalk">{n.rating}</b>
            {!locked && (
              <button
                onClick={() => setConfirm({
                  title: n.kind === "buy" ? `Продать ${n.name}?` : `Вернуть ${n.name} из аренды?`,
                  text: n.kind === "buy" ? `В бюджет вернётся ${eur(n.sell_back)}.` : "Деньги за аренду не возвращаются.",
                  run: () => sellNpc.mutate(n.id),
                })}
                className="shrink-0 rounded-lg bg-bg-surface px-2 py-1.5 text-micro text-ink-mist"
              >
                {n.kind === "buy" ? "Продать" : "Вернуть"}
              </button>
            )}
          </div>
        ))}
      </section>

      <ConfirmDialog
        open={!!confirm}
        title={confirm?.title ?? ""}
        description={confirm?.text}
        confirmLabel="Да"
        danger
        onConfirm={() => { confirm?.run(); setConfirm(null); }}
        onCancel={() => setConfirm(null)}
      />
    </div>
  );
}

function Stat({ label, value }: { label: string; value: ReactNode }) {
  return (
    <span className="rounded-xl bg-bg-base/40 p-2">
      <span className="flex items-center justify-center whitespace-nowrap font-display text-sm font-bold text-ink-chalk">{value}</span>
      <span className="block text-micro text-ink-mist">{label}</span>
    </span>
  );
}

// --- transfers ------------------------------------------------------------------------

function TransfersTab({ view, club, onView, onError }: TabProps & { club: ManagerClub }) {
  const [section, setSection] = useState<"users" | "catalog" | "scout">("users");
  const sections: [typeof section, string][] = [["users", `🤝 Игроки (${club.live_count}/${view.rules.max_live})`], ["catalog", "📋 Футболисты"], ["scout", "🔭 Скаут"]];
  return (
    <div className="flex flex-col gap-3" data-testid="manager-transfers">
      <div className="grid grid-cols-3 gap-1 rounded-xl bg-bg-surface p-1">
        {sections.map(([id, label]) => (
          <button key={id} onClick={() => setSection(id)}
            className={`rounded-lg py-2 text-xs font-semibold ${section === id ? "bg-floodlight text-bg-base" : "text-ink-mist"}`}>{label}</button>
        ))}
      </div>
      <p className="flex items-center justify-between rounded-xl bg-bg-surface px-3 py-2 text-xs text-ink-mist">
        Бюджет клуба <b className="text-sm text-accent-lime">{eur(club.budget)}</b>
      </p>
      {club.playing && <p className="rounded-xl bg-amber-400/10 px-3 py-2 text-caption text-amber-300">Идёт сезон — сделки откроются в предсезонку.</p>}
      {section === "users" && <UsersMarket view={view} club={club} onView={onView} onError={onError} />}
      {section === "catalog" && <Catalog club={club} onView={onView} onError={onError} />}
      {section === "scout" && <Scout club={club} />}
    </div>
  );
}

function MarketRow({ p, children }: { p: ManagerMarketPlayer; children?: ReactNode }) {
  return (
    <div className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-3">
      <div className="flex items-center gap-2">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-accent-cyan font-display text-sm font-black text-bg-base">{p.rating}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink-chalk">{p.player_name} <span className="font-normal text-ink-mist">· {p.position}</span></span>
          <span className="block truncate text-micro text-ink-mist">
            {p.owner_name} · ур. {p.level}{p.is_friend && " · 🤝"}{" · "}
            {p.club ? `${p.club.on_loan ? "в аренде в " : ""}«${p.club.name}», ${p.club.seasons_left} сез.` : p.looking ? "ищет клуб" : "без клуба"}
          </span>
        </span>
        <span className="text-right">
          <span className="block font-display text-sm font-bold text-accent-lime">{eur(p.value)}</span>
          <Trend pct={p.trend_pct} />
        </span>
      </div>
      {children}
    </div>
  );
}

function UsersMarket({ view, club, onView, onError }: TabProps & { club: ManagerClub }) {
  const queryClient = useQueryClient();
  const { data, isLoading } = useQuery({ queryKey: ["manager", "market"], queryFn: fetchManagerMarket });
  const [open, setOpen] = useState<number | null>(null);
  if (isLoading || !data) return <ListSkeleton />;
  if (data.players.length === 0) {
    return <EmptyState icon={IconProfile} title="На рынке пока пусто" description="Позови друзей: их «Мои игроки» появятся здесь." />;
  }
  return (
    <div className="flex flex-col gap-2">
      {data.players.map((p) => (
        <MarketRow key={p.user_id} p={p}>
          {p.offered ? (
            <p className="text-micro text-ink-mist">Предложение отправлено</p>
          ) : !p.club?.on_loan && !club.playing && (
            <button onClick={() => setOpen(open === p.user_id ? null : p.user_id)} className="rounded-lg bg-bg-raised py-1.5 text-xs font-semibold text-ink-chalk">
              {p.club ? "Купить или арендовать" : "Предложить контракт"}
            </button>
          )}
          {open === p.user_id && (
            <OfferForm player={p} view={view} club={club}
              onDone={(v) => { onView(v); setOpen(null); void queryClient.invalidateQueries({ queryKey: ["manager", "market"] }); }}
              onError={onError} />
          )}
        </MarketRow>
      ))}
    </div>
  );
}

function OfferForm({ player, view, club, onDone, onError }: {
  player: ManagerMarketPlayer; view: ManagerView; club: ManagerClub; onDone: (v: ManagerView) => void; onError: (e: unknown) => void;
}) {
  const inClub = !!player.club;
  const [kind, setKind] = useState<"sign" | "transfer" | "loan">(inClub ? "transfer" : "sign");
  const low = kind === "transfer" ? Math.floor(player.value / 2) : 0;
  const high = kind === "transfer" ? player.value * 3 : kind === "loan" ? player.value : 0;
  const step = Math.max(1000, Math.round(player.value / 100 / 1000) * 1000);
  const [fee, setFee] = useState(kind === "sign" ? 0 : player.value);
  const [wage, setWage] = useState(Math.round(view.rules.live_wage_max / 3 / 50) * 50);
  const [seasons, setSeasons] = useState(view.rules.contract_seasons[0]);
  useEffect(() => { setFee(kind === "transfer" ? player.value : kind === "loan" ? Math.floor(player.value / 5) : 0); }, [kind, player.value]);
  const offer = useMutation({
    mutationFn: () => offerManagerContract({ user_id: player.user_id, wage, seasons: kind === "loan" ? 1 : seasons, fee, kind }),
    onSuccess: (v) => { hapticNotify("success"); onDone(v); },
    onError,
  });
  const total = fee + wage * view.rules.wage_eur_per_coin;
  return (
    <div className="flex flex-col gap-2.5 rounded-xl bg-bg-raised p-3">
      {inClub && (
        <div className="grid grid-cols-2 gap-1.5">
          {(["transfer", "loan"] as const).map((k) => (
            <button key={k} onClick={() => setKind(k)}
              className={`rounded-lg py-1.5 text-xs font-semibold ${kind === k ? "bg-accent-lime text-bg-base" : "bg-bg-surface text-ink-mist"}`}>
              {k === "transfer" ? "Трансфер" : "Аренда на сезон"}
            </button>
          ))}
        </div>
      )}
      {kind !== "sign" && (
        <label className="flex flex-col gap-1 text-xs text-ink-mist">
          <span className="flex justify-between">Клубу «{player.club?.name}» <b className="text-ink-chalk">{eur(fee)}</b></span>
          <input type="range" min={low} max={high} step={step} value={fee} onChange={(e) => setFee(Number(e.target.value))} />
        </label>
      )}
      <label className="flex flex-col gap-1 text-xs text-ink-mist">
        <span className="flex justify-between">Зарплата игроку за сезон <b className="text-ink-chalk"><Coins n={wage} /></b></span>
        <input type="range" min={0} max={view.rules.live_wage_max} step={50} value={wage} onChange={(e) => setWage(Number(e.target.value))} />
      </label>
      {kind !== "loan" && (
        <div className="flex gap-1.5">
          {view.rules.contract_seasons.map((n) => (
            <button key={n} onClick={() => setSeasons(n)}
              className={`flex-1 rounded-lg py-1.5 text-xs font-semibold ${seasons === n ? "bg-accent-cyan text-bg-base" : "bg-bg-surface text-ink-mist"}`}>
              {n} {n === 1 ? "сезон" : "сезона"}
            </button>
          ))}
        </div>
      )}
      <p className={`text-micro ${total > club.budget ? "text-red-400" : "text-ink-mist"}`}>
        Из бюджета {eur(total)} (сумма + зарплата за сезон, 1 монета = {eur(view.rules.wage_eur_per_coin)}) из {eur(club.budget)}.{" "}
        {kind === "sign" ? "Игрок решает сам." : "Сделка — когда согласятся и клуб, и игрок."}
      </p>
      <button disabled={offer.isPending || total > club.budget} onClick={() => offer.mutate()}
        className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40">
        Отправить предложение
      </button>
    </div>
  );
}

function Scout({ club }: { club: ManagerClub }) {
  const { data, isLoading } = useQuery({ queryKey: ["manager", "scout"], queryFn: fetchManagerScout, enabled: club.pro, retry: false });
  if (!club.pro) {
    return <EmptyState icon={IconSearch} title="Скаут — в «Менеджер Pro»" description="Покажет, кто на рынке дорожает быстрее всех. Подключить можно во вкладке «Стиль»." />;
  }
  if (isLoading || !data) return <ListSkeleton />;
  if (data.players.length === 0) return <EmptyState icon={IconSearch} title="Пока нет данных" description="Тренд стоимости появится после первого сезона." />;
  return <div className="flex flex-col gap-2">{data.players.map((p) => <MarketRow key={p.user_id} p={p} />)}</div>;
}

const AFFORD: [ManagerCatalogFilter["afford"], string][] = [["loan", "💶 По карману: аренда"], ["buy", "💶 По карману: покупка"], [null, "Все цены"]];

function Catalog({ club, onView, onError }: { club: ManagerClub; onView: (v: ManagerView) => void; onError: (e: unknown) => void }) {
  const queryClient = useQueryClient();
  const [line, setLine] = useState<ManagerLine | null>(null);
  const [q, setQ] = useState("");
  const [query, setQuery] = useState("");
  const [afford, setAfford] = useState<ManagerCatalogFilter["afford"]>("loan");
  const [sort, setSort] = useState<ManagerCatalogFilter["sort"]>("rating");
  const [freeOnly, setFreeOnly] = useState(true);
  const [open, setOpen] = useState<number | null>(null);
  const [seasons, setSeasons] = useState(1);
  useEffect(() => { const t = setTimeout(() => setQuery(q), 350); return () => clearTimeout(t); }, [q]);
  const filter: ManagerCatalogFilter = { line, q: query, afford, sort, freeOnly };
  const { data, isLoading, fetchNextPage, hasNextPage, isFetchingNextPage } = useInfiniteQuery({
    queryKey: ["manager", "catalog", filter, club.budget],
    queryFn: ({ pageParam }) => fetchManagerCatalog(filter, pageParam),
    initialPageParam: 0,
    getNextPageParam: (last, pages) => (last.more ? pages.reduce((n, p) => n + p.players.length, 0) : undefined),
    placeholderData: keepPreviousData,
  });
  const sign = useMutation({
    mutationFn: ({ id, kind }: { id: number; kind: "buy" | "loan" }) => signManagerNpc(id, kind, seasons),
    onSuccess: (v) => { hapticNotify("success"); onView(v); setOpen(null); void queryClient.invalidateQueries({ queryKey: ["manager", "catalog"] }); },
    onError,
  });
  const players = data?.pages.flatMap((p) => p.players) ?? [];
  const maxRating = data?.pages[0]?.max_rating;
  const chip = (on: boolean) => `shrink-0 rounded-full px-3 py-1.5 text-xs font-semibold ${on ? "bg-accent-cyan text-bg-base" : "bg-bg-surface text-ink-mist"}`;
  return (
    <div className="flex flex-col gap-2" data-testid="catalog">
      <label className="flex items-center gap-2 rounded-xl bg-bg-surface px-3 py-2">
        <IconSearch className="h-4 w-4 text-ink-mist" />
        <input value={q} onChange={(e) => setQ(e.target.value)} placeholder="Имя футболиста"
          className="min-w-0 flex-1 bg-transparent text-sm text-ink-chalk outline-none placeholder:text-ink-mist-dim" />
      </label>
      <div className="flex gap-1.5 overflow-x-auto">
        {([null, "GK", "DEF", "MID", "FWD"] as const).map((l) => (
          <button key={l ?? "all"} onClick={() => setLine(l)} className={chip(line === l)}>{l ? LINE_LABEL[l] : "Все"}</button>
        ))}
      </div>
      <div className="flex gap-1.5 overflow-x-auto">
        {AFFORD.map(([value, label]) => (
          <button key={value ?? "any"} onClick={() => setAfford(value)} className={chip(afford === value)}>{label}</button>
        ))}
      </div>
      <div className="flex gap-1.5 overflow-x-auto">
        <button onClick={() => setSort("rating")} className={chip(sort === "rating")}>Сильнейшие</button>
        <button onClick={() => setSort("cheap")} className={chip(sort === "cheap")}>Дешёвые</button>
        <button onClick={() => setFreeOnly(!freeOnly)} className={chip(freeOnly)}>{freeOnly ? "✓ " : ""}Только свободные</button>
      </div>
      {afford && maxRating != null && (
        <p className="px-1 text-micro text-ink-mist">
          {maxRating > 0
            ? <>Бюджет {eur(club.budget)} — {afford === "loan" ? "аренда" : "покупка"} с зарплатой за сезон до рейтинга <b className="text-ink-chalk">{maxRating}</b></>
            : <>Бюджета {eur(club.budget)} не хватает ни на кого — дождись бюджета нового сезона или продай игрока.</>}
        </p>
      )}
      {isLoading || !data ? <ListSkeleton /> : players.length === 0 ? (
        <p className="py-6 text-center text-sm text-ink-mist">Никого не нашлось — смени фильтры</p>
      ) : players.map((p) => (
        <CatalogRow key={p.player_id} p={p} club={club} open={open === p.player_id} seasons={seasons} busy={sign.isPending}
          onToggle={() => setOpen(open === p.player_id ? null : p.player_id)} onSeasons={setSeasons}
          onSign={(kind) => sign.mutate({ id: p.player_id, kind })} />
      ))}
      {hasNextPage && (
        <button disabled={isFetchingNextPage} onClick={() => void fetchNextPage()}
          className="rounded-xl bg-bg-surface py-2.5 text-sm font-semibold text-ink-chalk disabled:opacity-50">
          {isFetchingNextPage ? "Загрузка…" : "Показать ещё"}
        </button>
      )}
    </div>
  );
}

function CatalogRow({ p, club, open, seasons, busy, onToggle, onSeasons, onSign }: {
  p: ManagerCatalogPlayer; club: ManagerClub; open: boolean; seasons: number; busy: boolean;
  onToggle: () => void; onSeasons: (n: number) => void; onSign: (kind: "buy" | "loan") => void;
}) {
  const free = !p.taken_by;
  return (
    <div className={`flex flex-col gap-2 rounded-2xl p-3 ${free ? "bg-bg-surface" : "bg-bg-surface/50"}`}>
      <button onClick={onToggle} disabled={!free || club.playing} className="flex items-center gap-2 text-left disabled:cursor-default">
        <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-white/90 font-display text-sm font-black text-bg-base">{p.rating}</span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-sm font-semibold text-ink-chalk">{p.name} <span className="font-normal text-ink-mist">· {p.position}</span></span>
          <span className="block truncate text-micro text-ink-mist">
            {p.taken_by ? (p.mine ? "уже в твоём клубе" : `играет за «${p.taken_by}»`) : `${p.club} · зарплата ${eur(p.wage_now)}/сезон`}
          </span>
        </span>
        <span className="text-right">
          <span className="block font-display text-sm font-bold text-accent-lime">{eur(p.value)}</span>
          <span className="block text-[9px] text-ink-mist">аренда {eur(p.loan_fee)}</span>
        </span>
      </button>
      {open && free && (
        <div className="flex flex-col gap-2 rounded-xl bg-bg-raised p-3">
          <div className="flex gap-1.5">
            {[1, 2, 3].map((n) => (
              <button key={n} onClick={() => onSeasons(n)}
                className={`flex-1 rounded-lg py-1.5 text-xs font-semibold ${seasons === n ? "bg-accent-cyan text-bg-base" : "bg-bg-surface text-ink-mist"}`}>
                {n} сез.
              </button>
            ))}
          </div>
          <div className="grid grid-cols-2 gap-2">
            <button disabled={busy || p.value + p.wage_now > club.budget} onClick={() => onSign("buy")}
              className="rounded-lg bg-floodlight py-2 text-xs font-bold text-bg-base disabled:opacity-40">
              Купить · {eur(p.value)}
            </button>
            <button disabled={busy || p.loan_fee + p.wage_now > club.budget} onClick={() => onSign("loan")}
              className="rounded-lg bg-bg-surface py-2 text-xs font-bold text-ink-chalk disabled:opacity-40">
              Аренда · {eur(p.loan_fee)}
            </button>
          </div>
          <p className="text-micro text-ink-mist">+ зарплата {eur(p.wage_now)} за каждый сезон, списывается при старте сезона.</p>
        </div>
      )}
    </div>
  );
}

// --- league --------------------------------------------------------------------------

function LeagueTab({ view, onError }: { view: ManagerView; onError: (e: unknown) => void }) {
  const [clubId, setClubId] = useState<number | null>(null);
  const league = view.league;
  const { data: popular } = useQuery({ queryKey: ["manager", "popular"], queryFn: fetchManagerPopular });
  return (
    <div className="flex flex-col gap-3">
      {league ? <LeagueTable league={league} onClub={setClubId} /> : (
        <EmptyState icon={IconTrophy} title="Лиги пока нет" description="Лиги собираются, когда закрывается трансферное окно." />
      )}
      <section className="flex flex-col gap-1.5 rounded-2xl bg-bg-surface p-4" data-testid="pyramid">
        <h2 className="mb-1 font-display text-sm font-bold text-ink-chalk">Пирамида дивизионов</h2>
        {view.pyramid.map((d) => {
          const mine = view.club?.division === d.division;
          const fill = d.capacity ? Math.min(100, Math.round((d.clubs * 100) / d.capacity)) : 100;
          return (
            <div key={d.division} className={`flex items-center gap-2 text-xs ${mine ? "text-accent-lime" : "text-ink-mist"}`}>
              <span className="w-24 shrink-0 font-semibold">{d.name}{mine && " · ты"}</span>
              <span className="h-2 flex-1 overflow-hidden rounded-full bg-bg-raised">
                <span className="block h-full rounded-full bg-accent-cyan/70" style={{ width: `${fill}%` }} />
              </span>
              <span className="w-20 shrink-0 text-right">{d.clubs}{d.capacity ? `/${d.capacity}` : ""}</span>
              <span className="w-16 shrink-0 text-right text-micro">{eur(d.grant)}</span>
            </div>
          );
        })}
        <p className="mt-1 text-micro text-ink-mist">
          Из каждой лиги вверх уходят {view.rules.promote}, вниз — {view.rules.promote * 2}; пока выше есть места — поднимается больше.
          За повышение +{view.rules.promotion_bonus_pct}% гранта, за вылет компенсация.
        </p>
      </section>
      {popular && popular.clubs.length > 0 && (
        <section className="flex flex-col gap-1.5 rounded-2xl bg-bg-surface p-4">
          <h2 className="mb-1 font-display text-sm font-bold text-ink-chalk">❤️ Клубы с самыми большими фанатами</h2>
          {popular.clubs.slice(0, 10).map((c, i) => (
            <button key={c.id} onClick={() => setClubId(c.id)} className="flex items-center gap-2 text-left text-xs text-ink-chalk">
              <span className="w-5 text-ink-mist">{i + 1}</span>
              <Emblem look={c.look} size={22} />
              <span className="min-w-0 flex-1 truncate">{c.name}</span>
              <span className="text-ink-mist">{c.fans} фанатов</span>
            </button>
          ))}
        </section>
      )}
      <ClubCardSheet clubId={clubId} onClose={() => setClubId(null)} onError={onError} />
    </div>
  );
}

function LeagueTable({ league, onClub }: { league: ManagerLeague; onClub: (id: number) => void }) {
  return (
    <section className="flex flex-col gap-3 rounded-2xl bg-bg-surface p-4" data-testid="manager-league">
      <div className="flex items-center justify-between gap-2">
        <h2 className="font-display text-base font-bold text-ink-chalk">
          {league.status === "finished" ? `Сезон завершён${league.champion ? ` · 🏆 ${league.champion}` : ""}` : `Тур ${league.rounds_played + 1} из ${league.total_rounds}`}
        </h2>
        <span className="shrink-0 rounded-full bg-white/10 px-2 py-0.5 text-micro font-bold text-ink-chalk">{league.division_name}</span>
      </div>
      {league.status === "active" && league.next_round_at && (
        <p className="text-sm text-ink-mist">Следующий тур: <b className="text-ink-chalk">{when(league.next_round_at)}</b></p>
      )}
      <table className="w-full text-left text-xs">
        <thead className="text-ink-mist">
          <tr><th className="py-1">#</th><th>Клуб</th><th className="text-center">И</th><th className="text-center">Р</th><th className="text-center">О</th></tr>
        </thead>
        <tbody>
          {league.table.map((row, i) => (
            <tr key={row.team_index}
              onClick={() => row.club_id && onClub(row.club_id)}
              className={`${row.club_id ? "cursor-pointer" : ""} ${row.is_mine ? "font-bold text-accent-lime" : row.is_live ? "text-ink-chalk" : "text-ink-mist"} ${row.zone === "up" ? "bg-emerald-500/10" : row.zone === "down" ? "bg-red-500/10" : ""}`}>
              <td className="py-1.5 pl-1">{i + 1}{row.zone === "up" ? " ⬆" : row.zone === "down" ? " ⬇" : ""}</td>
              <td className="max-w-[11rem] truncate">{row.is_live && "👤 "}{row.name}{row.owner_name && <span className="font-normal text-ink-mist-dim"> · {row.owner_name}</span>}</td>
              <td className="text-center">{row.played}</td>
              <td className="text-center">{row.gf - row.ga}</td>
              <td className="text-center">{row.points}</td>
            </tr>
          ))}
        </tbody>
      </table>
      <p className="-mt-1 text-micro text-ink-mist">Нажми на клуб с 👤 — откроется его карточка и мерч.</p>
      <div className="flex flex-col gap-2">
        {league.rounds.map((r) => {
          const mine = r.matches.find((m) => m.mine);
          if (!mine) return null;
          return (
            <div key={r.index} className={`rounded-xl p-2 text-xs ${mine.live ? "bg-fuchsia-500/15" : "bg-bg-raised"}`}>
              <div className="flex items-center gap-2">
                <span className="w-8 font-mono text-ink-mist">Т{r.index + 1}</span>
                <span className="min-w-0 flex-1 truncate text-ink-chalk">{mine.home} — {mine.away}{mine.live && " · 👤 менеджеры"}</span>
                <span className="font-mono font-bold text-ink-chalk">{mine.hs != null ? `${mine.hs}:${mine.away_score}` : when(r.at)}</span>
              </div>
              {mine.goals && mine.goals.length > 0 && (
                <div className="mt-1 flex flex-col gap-0.5 pl-10 text-micro text-ink-mist">
                  {([[true, mine.home], [false, mine.away]] as const).map(([home, team]) => {
                    const goals = mine.goals!.filter((g) => g.home === home);
                    return goals.length > 0 && (
                      <p key={team} className="truncate">
                        <span className="text-ink-chalk">{team}:</span> {goals.map((g) => `${g.minute ?? ""}' ${g.name || "гол"}`).join(", ")}
                      </p>
                    );
                  })}
                </div>
              )}
            </div>
          );
        })}
      </div>
      {league.players.length > 0 && (
        <div className="rounded-xl bg-bg-raised p-3">
          <p className="mb-1 text-xs font-bold text-ink-chalk">«Мои игроки» в лиге</p>
          {league.players.map((p) => (
            <p key={`${p.name}-${p.team}`} className="flex justify-between gap-2 text-xs text-ink-chalk">
              <span className="truncate">{p.name} · <span className="text-ink-mist">{p.team}</span></span>
              <span className="shrink-0">⚽ {p.goals} · 🅰️ {p.assists}{p.avg_rating != null ? ` · ${p.avg_rating}` : ""}</span>
            </p>
          ))}
        </div>
      )}
    </section>
  );
}

// --- me as a player ------------------------------------------------------------------------

function MeTab({ view, onView, onError }: TabProps) {
  const [leaving, setLeaving] = useState(false);
  const respond = useMutation({
    mutationFn: ({ id, accept }: { id: number; accept: boolean }) => respondManagerOffer(id, accept),
    onSuccess: (v) => { hapticNotify("success"); onView(v); }, onError,
  });
  const market = useMutation({ mutationFn: (open: boolean) => setManagerMarket(open), onSuccess: onView, onError });
  const leave = useMutation({ mutationFn: (id: number) => endManagerContract(id), onSuccess: onView, onError });
  const c = view.contract;
  return (
    <div className="flex flex-col gap-3" data-testid="manager-me">
      {view.my_value != null && (
        <section className="flex flex-col gap-3 rounded-2xl bg-gradient-to-r from-accent-lime/20 to-bg-surface p-4" data-testid="my-value">
          <div className="flex items-center gap-3">
            <span className="flex h-12 w-12 shrink-0 items-center justify-center rounded-full bg-accent-lime font-display text-lg font-black text-bg-base">
              {view.my_rating}
            </span>
            <span className="min-w-0 flex-1">
              <span className="block text-micro uppercase tracking-wide text-ink-mist">Трансферная стоимость</span>
              <span className="flex items-baseline gap-2">
                <span className="font-display text-2xl font-bold text-ink-chalk">{eur(view.my_value)}</span>
                <Trend pct={view.my_trend_pct} />
              </span>
              <span className="block text-micro text-ink-mist">Растёт с рейтингом и за голы и передачи в клубе</span>
            </span>
          </div>
          <ShareButton kind="manager_player" id={0} label="Поделиться стоимостью" />
        </section>
      )}
      {c ? (
        <section className="rounded-2xl bg-gradient-to-br from-accent-cyan/20 to-bg-surface p-4">
          <p className="text-micro uppercase tracking-wide text-ink-mist">{c.kind === "loan" ? "Я в аренде" : "Мой клуб"}</p>
          <p className="font-display text-lg font-bold text-ink-chalk">{c.club_name}</p>
          <p className="text-xs text-ink-mist">Менеджер {c.club_owner}</p>
          <div className="mt-2 grid grid-cols-3 gap-2 text-center">
            <Stat label="за сезон" value={<Coins n={c.wage} />} />
            <Stat label="сезонов" value={c.seasons_left} />
            <Stat label="заработано" value={<Coins n={c.earned} />} />
          </div>
          <p className="mt-2 text-xs text-ink-mist">⚽ {c.goals} · 🅰️ {c.assists} · сыграно {c.matches_played}</p>
          <div className="mt-3 grid grid-cols-2 gap-2">
            <ShareButton kind="manager_transfer" id={c.id} label="Here we go!" compact />
            <button onClick={() => setLeaving(true)} className="rounded-xl bg-bg-raised px-3 py-2 text-xs text-ink-mist">Уйти из клуба</button>
          </div>
        </section>
      ) : (
        <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4">
          <p className="font-display text-base font-bold text-ink-chalk">Ты свободный агент</p>
          <p className="text-caption text-ink-mist">
            Твой «Мой игрок» играет за твой клуб, если он есть. Включи «Ищу клуб» — тебя увидят менеджеры, пришлют контракт с зарплатой
            (до {view.rules.live_wage_max} монет за сезон), а ты решишь.
          </p>
          <label className="flex items-center justify-between rounded-xl bg-bg-raised p-3 text-sm text-ink-chalk">
            Ищу клуб
            <input type="checkbox" checked={view.market_open} disabled={market.isPending} onChange={(e) => market.mutate(e.target.checked)} />
          </label>
        </section>
      )}
      {view.offers.map((o) => (
        <section key={o.id} className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4 ring-1 ring-accent-lime/40">
          <p className="text-sm text-ink-chalk">
            ✍️ <b>{o.club_name}</b> ({o.club_owner}) — {o.kind === "sign" ? "контракт" : o.kind === "loan" ? "аренда на сезон" : "переход"}
          </p>
          <p className="text-xs text-ink-mist">
            {o.wage} монет за сезон · {o.seasons_total} {o.seasons_total === 1 ? "сезон" : "сезона"}
            {o.fee > 0 && <> · клубу {eur(o.fee)}</>}
            {o.kind !== "sign" && <> · {o.club_agreed ? "твой клуб согласен" : "ждём ответ твоего клуба"}</>}
          </p>
          {o.player_agreed ? (
            <p className="text-micro text-accent-lime">Ты согласился — ждём твой клуб</p>
          ) : (
            <div className="grid grid-cols-2 gap-2">
              <button disabled={respond.isPending} onClick={() => respond.mutate({ id: o.id, accept: true })} className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base">Согласен</button>
              <button disabled={respond.isPending} onClick={() => respond.mutate({ id: o.id, accept: false })} className="rounded-xl bg-bg-raised py-2.5 text-sm text-ink-mist">Отказать</button>
            </div>
          )}
        </section>
      ))}
      <ConfirmDialog
        open={leaving}
        title="Уйти из клуба?"
        description="Контракт будет расторгнут. Во время сезона уйти нельзя."
        confirmLabel="Уйти"
        danger
        onConfirm={() => { if (c) leave.mutate(c.id); setLeaving(false); }}
        onCancel={() => setLeaving(false)}
      />
    </div>
  );
}
