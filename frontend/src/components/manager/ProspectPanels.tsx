import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { endManagerContract, setManagerMarket, type ManagerClub, type ManagerProspect, type ManagerView } from "@/api/manager";
import ConfirmDialog from "@/components/common/ConfirmDialog";
import PlayerAvatar from "@/components/myPlayer/PlayerAvatar";
import { eur } from "@/lib/managerMoney";

/** «Воспитанник Академии» in «Менеджер» (backend manager_service, subject
 * "prospect"): he plays for the owner's club once old enough, or signs
 * for another club through the same market as «Мои игроки». */

function Head({ p }: { p: ManagerProspect }) {
  const grad = p.subject === "graduate";
  return (
    <div className="flex items-center gap-3">
      <span className="h-12 w-12 shrink-0 overflow-hidden rounded-full bg-black/30 ring-2 ring-emerald-300">
        <PlayerAvatar appearance={p.appearance} number={p.number} className="h-full w-full" />
      </span>
      <span className="min-w-0 flex-1">
        <span className="block truncate text-sm font-semibold text-ink-chalk">{p.name}</span>
        <span className="block text-micro text-ink-mist">
          {p.position} · {grad ? "🎓 выпускник" : `${p.age} лет · ${p.stage}`} · рейтинг <b className="text-ink-chalk">{p.rating}</b>
        </span>
      </span>
      {p.eligible && (
        <span className="shrink-0 text-right">
          <span className="block font-display text-sm font-bold text-accent-lime">{eur(p.value)}</span>
          {!!p.trend_pct && (
            <span className={`block text-micro ${p.trend_pct > 0 ? "text-accent-lime" : "text-red-300"}`}>
              {p.trend_pct > 0 ? "▲" : "▼"} {Math.abs(p.trend_pct)}%
            </span>
          )}
        </span>
      )}
    </div>
  );
}

function CreateHint() {
  const navigate = useNavigate();
  return (
    <>
      <p className="text-caption text-ink-mist">Вырасти своего футболиста с 6 лет в «Академии» — подростком он сможет играть за клубы.</p>
      <button onClick={() => navigate("/academy/prospect")} className="rounded-xl bg-bg-raised py-2 text-xs font-semibold text-ink-chalk">
        🧒 К воспитаннику
      </button>
    </>
  );
}

/** «Клуб»: my own prospect in my club, «Всегда в старте». */
export function ProspectClubSection({ view, club, busy, onStarts }: {
  view: ManagerView; club: ManagerClub; busy: boolean; onStarts: (on: boolean) => void;
}) {
  const p = view.prospect;
  return (
    <section className="flex flex-col gap-2 rounded-2xl bg-bg-surface p-4" data-testid="manager-prospect-club">
      <h2 className="font-display text-base font-bold text-ink-chalk">🧒 Воспитанник Академии</h2>
      {!p ? <CreateHint /> : (
        <>
          <Head p={p} />
          {!p.eligible ? (
            <p className="text-caption text-ink-mist">Пока мал для клуба: сможет играть с этапа «{p.min_stage}».</p>
          ) : p.contract ? (
            <p className="text-caption text-ink-mist">Сейчас играет за «{p.contract.club_name}» — вернётся, когда закончится контракт.</p>
          ) : (
            <>
              <p className="-mt-1 text-micro text-ink-mist">Играет за твой клуб бесплатно и растёт от матчей лиги. Без галочки выходит в старт, только если сильнее других на своей позиции.</p>
              <label className="flex items-center justify-between rounded-xl bg-bg-raised p-3 text-sm text-ink-chalk">
                Всегда в старте
                <input type="checkbox" checked={!!club.prospect_starts} disabled={busy || club.trade_locked}
                  onChange={(e) => onStarts(e.target.checked)} />
              </label>
              {club.trade_locked && <p className="text-micro text-amber-300">Поменять можно в предсезонку</p>}
            </>
          )}
        </>
      )}
    </section>
  );
}

/** «Я игрок»: my prospect (or my graduate) looks for a club or plays at another one. */
export function ProspectMeSection({ view, onView, onError, subject = "prospect" }: {
  view: ManagerView; onView: (v: ManagerView) => void; onError: (e: unknown) => void; subject?: "prospect" | "graduate";
}) {
  const [leaving, setLeaving] = useState(false);
  const market = useMutation({ mutationFn: (open: boolean) => setManagerMarket(open, subject), onSuccess: onView, onError });
  const leave = useMutation({ mutationFn: (id: number) => endManagerContract(id), onSuccess: onView, onError });
  const grad = subject === "graduate";
  const p = grad ? view.graduate : view.prospect;
  if (p === undefined || (grad && !p)) return null;
  const c = p?.contract;
  const wageMax = view.youth_wage_max ?? view.rules.live_wage_max;
  return (
    <section className={`flex flex-col gap-2 rounded-2xl bg-gradient-to-br ${grad ? "from-amber-400/15" : "from-emerald-400/15"} to-bg-surface p-4`}
      data-testid={grad ? "manager-graduate-me" : "manager-prospect-me"}>
      <p className="font-display text-base font-bold text-ink-chalk">{grad ? "🎓 Мой выпускник" : "🧒 Мой воспитанник"}</p>
      {!p ? <CreateHint /> : (
        <>
          <Head p={{ ...p, subject }} />
          {!p.eligible ? (
            <p className="text-caption text-ink-mist">Клубы возьмут его с этапа «{p.min_stage}».</p>
          ) : c ? (
            <>
              <p className="text-sm text-ink-chalk">
                {c.kind === "loan" ? "В аренде в" : "Играет за"} <b>«{c.club_name}»</b> · менеджер {c.club_owner}
              </p>
              <p className="text-xs text-ink-mist">
                {c.wage} мон./сезон · сезонов {c.seasons_left} · ⚽ {c.goals} · сыграно {c.matches_played}
              </p>
              <button onClick={() => setLeaving(true)} className="rounded-xl bg-bg-raised px-3 py-2 text-xs text-ink-mist">Забрать из клуба</button>
            </>
          ) : (
            <>
              <p className="text-caption text-ink-mist">
                Включи «Ищу клуб» — менеджеры увидят его на рынке рядом с «Моими игроками» и пришлют контракт (до {wageMax} монет
                за сезон). Без контракта он играет за твой клуб{grad ? " с замороженным рейтингом выпуска" : ""}.
              </p>
              <label className="flex items-center justify-between rounded-xl bg-bg-raised p-3 text-sm text-ink-chalk">
                Ищу клуб
                <input type="checkbox" checked={p.market_open} disabled={market.isPending} onChange={(e) => market.mutate(e.target.checked)} />
              </label>
            </>
          )}
        </>
      )}
      <ConfirmDialog
        open={leaving}
        title={grad ? "Забрать выпускника?" : "Забрать воспитанника?"}
        description="Контракт будет расторгнут. Во время сезона уйти нельзя."
        confirmLabel="Забрать"
        danger
        onConfirm={() => { if (c) leave.mutate(c.id); setLeaving(false); }}
        onCancel={() => setLeaving(false)}
      />
    </section>
  );
}
