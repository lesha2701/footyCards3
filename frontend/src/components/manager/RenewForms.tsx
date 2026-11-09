import { useMutation } from "@tanstack/react-query";
import { useState } from "react";

import {
  extendManagerNpc, renewManagerContract,
  type ManagerClub, type ManagerContract, type ManagerNpc, type ManagerView,
} from "@/api/manager";
import { eur } from "@/lib/managerMoney";
import { hapticNotify } from "@/lib/telegram";

type Done = { onDone: (v: ManagerView) => void; onError: (e: unknown) => void };

const seasonWord = (n: number) => (n === 1 ? "сезон" : "сезона");

/** The club's new contract for its user's player: new wage and a term not
 * shorter than what is left. The player answers it in «Я». */
export function RenewContractForm({ contract, view, club, onDone, onError }: Done & {
  contract: ManagerContract; view: ManagerView; club: ManagerClub;
}) {
  const options = view.rules.contract_seasons.filter((n) => n >= contract.seasons_left);
  const [seasons, setSeasons] = useState(options.find((n) => n > contract.seasons_left) ?? options[0]);
  const [wage, setWage] = useState(contract.wage);
  const send = useMutation({
    mutationFn: () => renewManagerContract(contract.id, wage, seasons),
    onSuccess: (v) => { hapticNotify("success"); onDone(v); },
    onError,
  });
  const rate = view.rules.wage_eur_per_coin;
  // The next start already pays the old wage, unless the contract runs out now.
  const extra = Math.max(0, wage * rate - (contract.seasons_left > 0 ? contract.wage * rate : 0));
  const same = seasons === contract.seasons_left && wage === contract.wage;
  return (
    <div className="flex flex-col gap-2.5 rounded-xl bg-bg-surface p-3" data-testid="renew-form">
      <p className="text-micro text-ink-mist">
        Сейчас: {contract.wage} мон./сезон, осталось {contract.seasons_left} сез. Новый контракт начнётся сразу, если игрок согласится.
      </p>
      <label className="flex flex-col gap-1 text-xs text-ink-mist">
        <span className="flex justify-between gap-2">Зарплата за сезон <b className="shrink-0 text-ink-chalk">{wage} мон. · {eur(wage * rate)}</b></span>
        <input type="range" min={0} max={view.rules.live_wage_max} step={50} value={wage} onChange={(e) => setWage(Number(e.target.value))} />
      </label>
      <div className="grid grid-cols-3 gap-1.5">
        {view.rules.contract_seasons.map((n) => (
          <button key={n} onClick={() => setSeasons(n)} disabled={n < contract.seasons_left}
            className={`rounded-lg py-1.5 text-xs font-semibold disabled:opacity-30 ${seasons === n ? "bg-accent-cyan text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
            {n} {seasonWord(n)}
          </button>
        ))}
      </div>
      <p className={`text-micro ${extra > club.free_budget ? "text-red-400" : "text-ink-mist"}`}>
        {extra > 0 ? `Зарплаты клуба вырастут на ${eur(extra)} за сезон` : "Зарплаты клуба не вырастут"}, свободно {eur(club.free_budget)}.
      </p>
      <button disabled={send.isPending || same || extra > club.free_budget} onClick={() => send.mutate()}
        className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40">
        Предложить новый контракт
      </button>
    </div>
  );
}

/** A catalog footballer: a bought one gets a longer contract, a loan one
 * more season for a new fee. */
export function ExtendNpcForm({ npc, club, onDone, onError }: Done & { npc: ManagerNpc; club: ManagerClub }) {
  const loanFee = npc.loan_fee;
  const wageNow = npc.wage;
  const loan = npc.kind === "loan";
  const options = [1, 2, 3].filter((n) => n > npc.seasons_left);
  const [seasons, setSeasons] = useState(options[options.length - 1] ?? 3);
  const send = useMutation({
    mutationFn: () => extendManagerNpc(npc.id, loan ? 1 : seasons),
    onSuccess: (v) => { hapticNotify("success"); onDone(v); },
    onError,
  });
  const cost = (loan ? loanFee : 0) + (npc.seasons_left <= 0 ? wageNow : 0);
  return (
    <div className="flex flex-col gap-2.5 rounded-xl bg-bg-surface p-3" data-testid="extend-form">
      {loan ? (
        <p className="text-micro text-ink-mist">Ещё один сезон аренды: {eur(loanFee)} сейчас + зарплата {eur(wageNow)} при старте сезона.</p>
      ) : (
        <>
          <p className="text-micro text-ink-mist">Новый контракт с этого окна, зарплата та же — {eur(wageNow)} за сезон. Без платы за переход.</p>
          <div className="grid grid-cols-3 gap-1.5">
            {[1, 2, 3].map((n) => (
              <button key={n} onClick={() => setSeasons(n)} disabled={n <= npc.seasons_left}
                className={`rounded-lg py-1.5 text-xs font-semibold disabled:opacity-30 ${seasons === n ? "bg-accent-cyan text-bg-base" : "bg-bg-raised text-ink-mist"}`}>
                {n} {seasonWord(n)}
              </button>
            ))}
          </div>
        </>
      )}
      <p className={`text-micro ${cost > club.free_budget ? "text-red-400" : "text-ink-mist"}`}>
        Из свободного бюджета {eur(cost)}, свободно {eur(club.free_budget)}.
      </p>
      <button disabled={send.isPending || cost > club.free_budget || (!loan && options.length === 0)} onClick={() => send.mutate()}
        className="rounded-xl bg-floodlight py-2.5 text-sm font-bold text-bg-base disabled:opacity-40">
        {loan ? `Продлить аренду · ${eur(loanFee)}` : "Продлить контракт"}
      </button>
    </div>
  );
}
