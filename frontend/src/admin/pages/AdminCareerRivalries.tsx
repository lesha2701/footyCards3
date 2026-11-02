import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import {
  bulkAdminRivalries, createAdminRivalry, deleteAdminRivalry, fetchAdminDuelStats, fetchAdminPlayers, fetchAdminRivalries,
  updateAdminRivalry, type AdminRivalriesOverview, type AdminRivalryBulkResult,
} from "@/admin/api";
import { useAdminToastStore } from "@/admin/adminToastStore";
import { ApiRequestError } from "@/lib/api";
import type { Player } from "@/types";

const input = "w-full rounded-lg bg-bg-base px-2 py-1.5 text-sm outline-none";
const LEVELS: { value: number; label: string }[] = [
  { value: -3, label: "−3 защитник гасит нападающего" },
  { value: -2, label: "−2 защитнику заметно легче" },
  { value: -1, label: "−1 защитнику чуть легче" },
  { value: 1, label: "+1 нападающему чуть легче" },
  { value: 2, label: "+2 нападающему заметно легче" },
  { value: 3, label: "+3 нападающий «возит» защитника" },
];
const errText = (err: unknown) => (err instanceof ApiRequestError ? err.message : "Не удалось сохранить");

function PlayerPicker({ label, value, onPick }: { label: string; value: Player | null; onPick: (p: Player | null) => void }) {
  const [search, setSearch] = useState("");
  const { data } = useQuery({
    queryKey: ["admin-players", "rivalry-pick", search],
    queryFn: () => fetchAdminPlayers(search, 1),
    enabled: search.trim().length >= 2,
  });
  return (
    <label className="flex flex-col gap-1">
      <span className="text-micro text-slate-500">{label}</span>
      {value ? (
        <button type="button" onClick={() => onPick(null)}
          className="rounded-lg bg-accent-lime/10 px-2 py-1.5 text-left text-sm text-accent-lime">
          {value.display_name} · {value.position} ✕
        </button>
      ) : (
        <>
          <input value={search} onChange={(e) => setSearch(e.target.value)} placeholder="Имя футболиста" className={input} />
          {(data?.items ?? []).slice(0, 6).map((p) => (
            <button key={p.id} type="button" onClick={() => { onPick(p); setSearch(""); }}
              className="rounded-lg bg-white/5 px-2 py-1 text-left text-xs">
              {p.display_name} · {p.position} · {p.club} · {p.rating}
            </button>
          ))}
        </>
      )}
    </label>
  );
}

/** Many pairs at once: one per line «атакующий; защитник; уровень; заметка». */
function BulkRivalries({ onSaved }: { onSaved: (v: AdminRivalriesOverview) => void }) {
  const toast = useAdminToastStore((s) => s.push);
  const [text, setText] = useState("");
  const [result, setResult] = useState<AdminRivalryBulkResult["bulk"] | null>(null);
  const save = useMutation({
    mutationFn: () => bulkAdminRivalries(text),
    onSuccess: (v) => {
      onSaved(v);
      setResult(v.bulk);
      if (!v.bulk.errors.length) setText("");
      toast(`Сохранено противостояний: ${v.bulk.saved}`, v.bulk.errors.length ? "error" : "success");
    },
    onError: (err) => toast(errText(err), "error"),
  });
  return (
    <details className="mt-3 rounded-xl bg-bg-base/40 p-3">
      <summary className="cursor-pointer text-xs font-semibold text-slate-300">Добавить списком</summary>
      <p className="mt-2 text-micro text-slate-500">
        По одному в строке: «Нападающий; Защитник; уровень −3..3; подпись». Имена — как в «Футболисты» (любая версия
        карты). Строки с # пропускаются.
      </p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={5}
        placeholder={"Ламин Ямаль; Нуну Мендеш; -3; Мендеш гасит Ямаля\nВинисиус; Карвахаль; -1"}
        className={`${input} mt-2 font-mono text-xs`} />
      <button onClick={() => save.mutate()} disabled={!text.trim() || save.isPending}
        className="mt-2 rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-40">
        Сохранить список
      </button>
      {result && result.errors.length > 0 && (
        <ul className="mt-2 flex flex-col gap-0.5">
          {result.errors.map((e) => (
            <li key={e.line} className="text-xs text-red-400">Строка {e.line}: {e.error} — «{e.text}»</li>
          ))}
        </ul>
      )}
    </details>
  );
}

/** How the duels actually play out per style matchup: the attacker's win
 * share should be higher where he has the edge — the numbers to tune by. */
function DuelStats() {
  const { data } = useQuery({ queryKey: ["admin-career-duel-stats"], queryFn: fetchAdminDuelStats });
  if (!data) return null;
  const tone = (expected: number) => (expected > 0 ? "text-accent-lime" : expected < 0 ? "text-red-400" : "text-slate-300");
  return (
    <details className="mt-4 rounded-xl bg-bg-base/40 p-3">
      <summary className="cursor-pointer text-xs font-semibold text-slate-300">
        Статистика дуэлей · пар {data.pairs} · дуэлей {data.duels}
      </summary>
      <p className="mt-2 text-micro text-slate-500">
        Доля выигранных стыков нападающего по сочетанию стилей (вся история карьеры). Зелёным — где по таблице легче
        нападающему, красным — защитнику. Стиль задан вручную у {data.players_explicit_style} карт; известных
        противостояний {data.rivalries}. Страх: {(data.levels["-1"] ?? 0) + (data.levels["-2"] ?? 0)} пар, любимый
        соперник: {(data.levels["1"] ?? 0) + (data.levels["2"] ?? 0)}.
      </p>
      <table className="mt-2 w-full text-xs">
        <thead>
          <tr className="text-slate-500">
            <th className="pb-1 text-left font-normal">Нападающий</th>
            <th className="pb-1 text-left font-normal">Защитник</th>
            <th className="pb-1 text-right font-normal">Дуэлей</th>
            <th className="pb-1 text-right font-normal">Нападающий выиграл</th>
          </tr>
        </thead>
        <tbody>
          {data.matrix.map((c) => (
            <tr key={`${c.attacker_type}-${c.defender_type}`} className={tone(c.expected)}>
              <td className="py-0.5">{c.attacker_label}</td>
              <td className="py-0.5">{c.defender_label}</td>
              <td className="py-0.5 text-right font-mono">{c.duels}</td>
              <td className="py-0.5 text-right font-mono">{c.attacker_win_pct == null ? "—" : `${c.attacker_win_pct}%`}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </details>
  );
}

/** «Противостояния» of the career flank duels: known pairs set by hand
 * («Мендеш гасит Ямаля») and the pairs the global duel history has made
 * one-sided by itself. */
export default function AdminCareerRivalries() {
  const queryClient = useQueryClient();
  const toast = useAdminToastStore((s) => s.push);
  const { data } = useQuery({ queryKey: ["admin-career-rivalries"], queryFn: fetchAdminRivalries });
  const [attacker, setAttacker] = useState<Player | null>(null);
  const [defender, setDefender] = useState<Player | null>(null);
  const [level, setLevel] = useState(-2);
  const [note, setNote] = useState("");
  const set = (v: AdminRivalriesOverview) => {
    queryClient.setQueryData(["admin-career-rivalries"], v);
    void queryClient.invalidateQueries({ queryKey: ["admin-career-duel-stats"] });
  };
  const onError = (err: unknown) => toast(errText(err), "error");

  const create = useMutation({
    mutationFn: () => createAdminRivalry({ attacker_id: attacker!.id, defender_id: defender!.id, level, note: note || null }),
    onSuccess: (v) => { set(v); setAttacker(null); setDefender(null); setNote(""); toast("Противостояние сохранено", "success"); },
    onError,
  });
  const update = useMutation({
    mutationFn: ({ id, lvl, n }: { id: number; lvl: number; n: string | null }) => updateAdminRivalry(id, lvl, n),
    onSuccess: set,
    onError,
  });
  const remove = useMutation({ mutationFn: deleteAdminRivalry, onSuccess: set, onError });

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">Противостояния (дуэли на флангах)</p>
      <p className="mb-3 text-xs text-slate-400">
        Кто кому неудобен в дуэли на фланге: нападающий (вингер) против защитника. Плюс к стилю игроков и истории их
        дуэлей; −3 — защитник «гасит» нападающего. Стиль игрока задаётся в «Футболисты».
      </p>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <PlayerPicker label="Нападающий (атакует по флангу)" value={attacker} onPick={setAttacker} />
        <PlayerPicker label="Защитник" value={defender} onPick={setDefender} />
        <label className="flex flex-col gap-1">
          <span className="text-micro text-slate-500">Сила</span>
          <select value={level} onChange={(e) => setLevel(Number(e.target.value))} className={input}>
            {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
          </select>
        </label>
        <label className="flex flex-col gap-1">
          <span className="text-micro text-slate-500">Подпись (необязательно)</span>
          <input value={note} onChange={(e) => setNote(e.target.value)} maxLength={255} className={input} />
        </label>
      </div>
      <button
        onClick={() => create.mutate()}
        disabled={!attacker || !defender || create.isPending}
        className="mt-2 rounded-lg bg-accent-lime px-4 py-1.5 text-sm font-semibold text-bg-base disabled:opacity-40"
      >
        Добавить противостояние
      </button>
      <BulkRivalries onSaved={set} />

      <div className="mt-4 flex flex-col">
        {(data?.rivalries ?? []).map((r) => (
          <div key={r.id} className="flex flex-wrap items-center gap-2 border-t border-white/5 py-2 text-sm">
            <span className="min-w-0 flex-1">
              <span className="block truncate">{r.attacker} <span className="text-slate-500">⟷</span> {r.defender}</span>
              {r.note && <span className="block truncate text-xs text-slate-400">{r.note}</span>}
            </span>
            <select
              aria-label={`Сила: ${r.attacker} — ${r.defender}`}
              value={r.level}
              onChange={(e) => update.mutate({ id: r.id, lvl: Number(e.target.value), n: r.note })}
              className="rounded-lg bg-bg-base px-2 py-1 text-xs"
            >
              {LEVELS.map((l) => <option key={l.value} value={l.value}>{l.label}</option>)}
            </select>
            <button onClick={() => remove.mutate(r.id)} className="rounded-lg bg-red-500/10 px-2 py-1 text-xs text-red-400">
              Удалить
            </button>
          </div>
        ))}
        {data && !data.rivalries.length && <p className="text-xs text-slate-500">Пока нет ни одного противостояния.</p>}
      </div>

      {(data?.history ?? []).length > 0 && (
        <div className="mt-4">
          <p className="mb-1 text-xs font-semibold text-slate-300">Сложились сами (по истории дуэлей в карьере)</p>
          {(data?.history ?? []).map((h) => (
            <p key={`${h.attacker_key}-${h.defender_key}`} className="border-t border-white/5 py-1 text-xs text-slate-400">
              {h.attacker_key} ⟷ {h.defender_key} · {h.record[0]}:{h.record[1]} ·{" "}
              {h.level < 0 ? `страх (${h.level})` : `любимый соперник (+${h.level})`}
            </p>
          ))}
        </div>
      )}
      <DuelStats />
    </section>
  );
}
