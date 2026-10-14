import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { buildCareerClubs, createCareerClub, fetchCareerClubs, updateCareerClub, type CareerClubAdmin } from "@/admin/api";
import { FORMATIONS } from "@/lib/clubTactics";

const PRESETS = [
  { value: "", label: "Случайная" },
  { value: "WING_PLAY", label: "Фланговая" }, { value: "CENTRAL_PLAY", label: "Через центр" },
  { value: "POSSESSION", label: "Контроль мяча" }, { value: "HIGH_PRESS", label: "Прессинг" },
  { value: "COUNTER_ATTACK", label: "Контратаки" },
];
const SOURCE: Record<string, string> = { real: "из карточек", generated: "сгенерирован", admin: "вручную" };

function ClubRow({ club, divisions, onSave }: { club: CareerClubAdmin; divisions: number; onSave: (c: CareerClubAdmin) => void }) {
  const [draft, setDraft] = useState(club);
  const dirty = JSON.stringify(draft) !== JSON.stringify(club);
  return (
    <tr className={`border-t border-white/5 ${draft.is_active ? "" : "opacity-50"}`}>
      <td className="py-1.5 pr-2">
        <input value={draft.name} onChange={(e) => setDraft({ ...draft, name: e.target.value })}
          className="w-36 rounded bg-bg-base px-2 py-1 text-xs" />
        <p className="mt-0.5 text-[10px] text-slate-500">
          {SOURCE[club.source ?? ""] ?? club.source}{club.pool_club ? ` · ${club.pool_club} (${club.pool_players})` : ""}
        </p>
      </td>
      <td className="pr-2">
        <select value={draft.division} onChange={(e) => setDraft({ ...draft, division: Number(e.target.value) })}
          className="rounded bg-bg-base px-1 py-1 text-xs">
          {Array.from({ length: divisions }, (_, i) => <option key={i + 1} value={i + 1}>{i + 1}</option>)}
        </select>
      </td>
      <td className="pr-2">
        <input type="number" value={draft.rating_offset} onChange={(e) => setDraft({ ...draft, rating_offset: Number(e.target.value) })}
          className="w-14 rounded bg-bg-base px-1 py-1 text-xs" />
      </td>
      <td className="pr-2">
        <select value={draft.formation ?? ""} onChange={(e) => setDraft({ ...draft, formation: e.target.value || null })}
          className="rounded bg-bg-base px-1 py-1 text-xs">
          <option value="">Случайная</option>
          {FORMATIONS.map((f) => <option key={f.value} value={f.value}>{f.label}</option>)}
        </select>
      </td>
      <td className="pr-2">
        <select value={draft.preset ?? ""} onChange={(e) => setDraft({ ...draft, preset: e.target.value || null })}
          className="rounded bg-bg-base px-1 py-1 text-xs">
          {PRESETS.map((p) => <option key={p.value} value={p.value}>{p.label}</option>)}
        </select>
      </td>
      <td className="pr-2 text-center">
        <input type="checkbox" checked={draft.is_active} onChange={(e) => setDraft({ ...draft, is_active: e.target.checked })} />
      </td>
      <td>
        <button disabled={!dirty} onClick={() => onSave(draft)} className="rounded bg-accent-lime/20 px-2 py-1 text-[11px] text-accent-lime disabled:opacity-30">
          Сохранить
        </button>
      </td>
    </tr>
  );
}

/** Career bot clubs per division: built from the real clubs of the card
 * pool (rosters from their players), gaps generated; editable. */
export default function AdminCareerClubs({ divisions }: { divisions: number }) {
  const queryClient = useQueryClient();
  const { data } = useQuery({ queryKey: ["admin-career-clubs"], queryFn: fetchCareerClubs });
  const [division, setDivision] = useState(1);
  const [newName, setNewName] = useState("");
  const set = (v: { clubs: CareerClubAdmin[] }) => queryClient.setQueryData(["admin-career-clubs"], v);
  const build = useMutation({ mutationFn: (replace: boolean) => buildCareerClubs(replace), onSuccess: set });
  const save = useMutation({ mutationFn: (c: CareerClubAdmin) => updateCareerClub(c), onSuccess: set });
  const create = useMutation({
    mutationFn: () => createCareerClub({ name: newName.trim(), division, rating_offset: 0, is_active: true }),
    onSuccess: (v) => { set(v); setNewName(""); },
  });
  const clubs = (data?.clubs ?? []).filter((c) => c.division === division);

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">Карьера: клубы дивизионов</p>
      <p className="mb-3 text-xs text-slate-400">
        Боты лиги берутся отсюда. «Из карточек» — реальные клубы, у которых в игре 8+ игроков: их составы собираются
        из этих игроков. Недостающие места заполняются сгенерированными клубами. Сила — сдвиг рейтинга относительно дивизиона.
      </p>
      <div className="mb-3 flex flex-wrap gap-2">
        <button onClick={() => build.mutate(false)} disabled={build.isPending} className="rounded-lg bg-accent-lime/20 px-3 py-1.5 text-xs text-accent-lime">
          Сформировать из карточек игры
        </button>
        <button onClick={() => { if (confirm("Пересобрать каталог? Клубы, добавленные вручную, останутся.")) build.mutate(true); }}
          disabled={build.isPending} className="rounded-lg bg-white/5 px-3 py-1.5 text-xs text-slate-300">
          Пересобрать заново
        </button>
      </div>
      <div className="mb-3 flex gap-1">
        {Array.from({ length: divisions }, (_, i) => i + 1).map((d) => (
          <button key={d} onClick={() => setDivision(d)}
            className={`rounded-lg px-3 py-1 text-xs ${d === division ? "bg-accent-lime text-bg-base" : "bg-white/5 text-slate-300"}`}>
            {d}-й · {(data?.clubs ?? []).filter((c) => c.division === d && c.is_active).length}
          </button>
        ))}
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr><th>Клуб</th><th>Див.</th><th>Сила</th><th>Схема</th><th>Тактика</th><th>Вкл.</th><th /></tr>
          </thead>
          <tbody>
            {clubs.map((c) => <ClubRow key={`${c.id}-${JSON.stringify(c)}`} club={c} divisions={divisions} onSave={(x) => save.mutate(x)} />)}
          </tbody>
        </table>
      </div>
      <div className="mt-3 flex gap-2">
        <input value={newName} onChange={(e) => setNewName(e.target.value)} placeholder="Новый клуб в этом дивизионе"
          className="flex-1 rounded-lg bg-bg-base px-3 py-1.5 text-xs" />
        <button disabled={newName.trim().length < 2 || create.isPending} onClick={() => create.mutate()}
          className="rounded-lg bg-accent-lime/20 px-3 py-1.5 text-xs text-accent-lime disabled:opacity-40">
          Добавить
        </button>
      </div>
    </section>
  );
}
