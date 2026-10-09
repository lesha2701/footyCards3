import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";

import {
  fetchAdminSkillCatalog,
  fetchAdminUserSkillTokens,
  fetchGameConfig,
  fetchSkillLedger,
  grantSkillTokens,
  updateAdminSkill,
  updateGameConfig,
} from "@/admin/api";
import type { GameConfig } from "@/admin/types";
import { SkillIcon, SkillTokenIcon } from "@/components/icons/skills";
import { ApiRequestError } from "@/lib/api";
import type { SkillCatalogItem } from "@/types";

type SkillConfigKey = Extract<keyof GameConfig, `card_skill_${string}`>;

const ECONOMY_FIELDS: [SkillConfigKey, string][] = [
  ["card_skill_level_1_bonus_pp", "Бонус уровня I, п.п."],
  ["card_skill_level_2_bonus_pp", "Бонус уровня II, п.п."],
  ["card_skill_level_3_bonus_pp", "Бонус уровня III, п.п."],
  ["card_skill_event_bonus_cap_pp", "Предел суммарного бонуса к одному событию, п.п."],
  ["card_skill_probability_floor_pct", "Нижняя граница итоговой вероятности, %"],
  ["card_skill_probability_ceiling_pct", "Верхняя граница итоговой вероятности, %"],
  ["card_skill_assign_token_cost", "Назначение: жетоны"],
  ["card_skill_assign_coin_cost", "Назначение: монеты"],
  ["card_skill_upgrade_2_token_cost", "Улучшение I→II: жетоны"],
  ["card_skill_upgrade_2_coin_cost", "Улучшение I→II: монеты"],
  ["card_skill_upgrade_3_token_cost", "Улучшение II→III: жетоны"],
  ["card_skill_upgrade_3_coin_cost", "Улучшение II→III: монеты"],
  ["card_skill_replace_token_cost", "Замена: жетоны нового навыка"],
  ["card_skill_replace_coin_cost", "Замена: монеты"],
];

const PLACES = 16;

function errorText(err: unknown) {
  return err instanceof ApiRequestError ? err.message : "Ошибка";
}

export default function AdminCardSkillsPage() {
  const queryClient = useQueryClient();
  const { data: catalog } = useQuery({ queryKey: ["admin-card-skills"], queryFn: fetchAdminSkillCatalog });
  const { data: config } = useQuery({ queryKey: ["admin-game-config"], queryFn: fetchGameConfig });

  const [form, setForm] = useState<Partial<GameConfig> | null>(null);
  useEffect(() => {
    if (!config) return;
    const picked: Partial<GameConfig> = { card_skills_enabled: config.card_skills_enabled };
    for (const [key] of ECONOMY_FIELDS) (picked as Record<string, number>)[key] = config[key] as number;
    const places = [...(config.ptour_place_skill_tokens ?? [])];
    while (places.length < PLACES) places.push(null);
    picked.ptour_place_skill_tokens = places.slice(0, PLACES);
    setForm(picked);
  }, [config]);

  const [configMessage, setConfigMessage] = useState<string | null>(null);
  const saveConfig = useMutation({
    mutationFn: () => {
      // Trailing empty places are trimmed so "no token rewards" stays [].
      const places = [...(form!.ptour_place_skill_tokens ?? [])];
      while (places.length && !places[places.length - 1]) places.pop();
      return updateGameConfig({ ...form!, ptour_place_skill_tokens: places });
    },
    onSuccess: () => {
      setConfigMessage("Сохранено");
      queryClient.invalidateQueries({ queryKey: ["admin-game-config"] });
      queryClient.invalidateQueries({ queryKey: ["admin-card-skills"] });
    },
    onError: (err) => setConfigMessage(errorText(err)),
  });

  const [skillError, setSkillError] = useState<string | null>(null);
  const skillMutation = useMutation({
    mutationFn: ({ code, payload }: { code: string; payload: Parameters<typeof updateAdminSkill>[1] }) =>
      updateAdminSkill(code, payload),
    onSuccess: (data) => {
      setSkillError(null);
      queryClient.setQueryData(["admin-card-skills"], data);
    },
    onError: (err) => setSkillError(errorText(err)),
  });

  if (!form || !catalog) return <p className="text-sm text-slate-400">Загрузка...</p>;
  const grantable = catalog.skills.filter((s) => s.engine_supported);

  return (
    <div className="flex flex-col gap-6">
      <h1 className="font-display text-2xl font-bold">Навыки карточек</h1>

      <section className="rounded-2xl border border-amber-500/20 bg-amber-500/5 p-4">
        <label className="flex items-center gap-2 text-sm font-semibold">
          <input
            type="checkbox"
            checked={!!form.card_skills_enabled}
            onChange={(e) => setForm({ ...form, card_skills_enabled: e.target.checked })}
          />
          Механика навыков включена
        </label>
        <p className="mt-2 text-xs text-slate-400">
          Выключение: назначение/улучшение/замена недоступны, новые матчи стартуют без эффектов навыков. Навыки на
          карточках и жетоны у игроков сохраняются; уже начатые матчи доигрываются по правилам, зафиксированным на старте.
        </p>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Сила и стоимость</p>
        <p className="mb-3 text-xs text-slate-400">
          Бонус добавляется в процентных пунктах к одному конкретному броску (например, 40% + 4 п.п. = 44%) после
          рейтинга, тренера и стадиона. Границы применяются только к вероятностям, которые изменил навык, и не
          обрезают значения, уже лежащие за ними по базовым формулам.
        </p>
        <div className="grid grid-cols-2 gap-3">
          {ECONOMY_FIELDS.map(([key, label]) => (
            <label key={key} className="flex flex-col gap-1">
              <span className="text-xs text-slate-400">{label}</span>
              <input
                type="number"
                min={0}
                value={(form[key] as number | undefined) ?? 0}
                onChange={(e) => setForm({ ...form, [key]: Number(e.target.value) })}
                className="rounded-lg bg-bg-base px-3 py-2 outline-none"
              />
            </label>
          ))}
        </div>

        <p className="mb-2 mt-5 font-display text-sm font-bold">Жетоны за места в турнире игроков</p>
        <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
          {(form.ptour_place_skill_tokens ?? []).map((entry, index) => (
            <div key={index} className="flex items-center gap-2 text-xs">
              <span className="w-10 text-slate-400">{index + 1}-е</span>
              <select
                value={entry?.skill_code ?? ""}
                onChange={(e) => {
                  const places = [...(form.ptour_place_skill_tokens ?? [])];
                  places[index] = e.target.value ? { skill_code: e.target.value, quantity: entry?.quantity || 1 } : null;
                  setForm({ ...form, ptour_place_skill_tokens: places });
                }}
                className="flex-1 rounded-lg bg-bg-base px-2 py-1.5 outline-none"
              >
                <option value="">Нет</option>
                {grantable.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
              </select>
              <input
                type="number"
                min={1}
                disabled={!entry}
                value={entry?.quantity ?? 0}
                onChange={(e) => {
                  const places = [...(form.ptour_place_skill_tokens ?? [])];
                  if (entry) places[index] = { ...entry, quantity: Math.max(1, Number(e.target.value)) };
                  setForm({ ...form, ptour_place_skill_tokens: places });
                }}
                className="w-16 rounded-lg bg-bg-base px-2 py-1.5 outline-none disabled:opacity-40"
              />
            </div>
          ))}
        </div>

        <div className="mt-4 flex items-center gap-3">
          <button
            onClick={() => { setConfigMessage(null); saveConfig.mutate(); }}
            disabled={saveConfig.isPending}
            className="rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40"
          >
            Сохранить
          </button>
          {configMessage && <span className="text-xs text-slate-400">{configMessage}</span>}
        </div>
      </section>

      <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
        <p className="mb-1 font-display text-base font-bold">Каталог</p>
        <p className="mb-3 text-xs text-slate-400">
          Отключённый навык нельзя назначить, улучшить или выбрать при замене; у карточек, где он уже есть, он остаётся
          и продолжает действовать в матчах, а замена его на другой навык доступна. Позиции можно только сузить в
          пределах серверной таблицы совместимости.
        </p>
        {skillError && <p className="mb-2 rounded-lg bg-red-500/10 px-3 py-2 text-xs text-red-400">{skillError}</p>}
        <div className="flex flex-col gap-3">
          {catalog.skills.map((skill) => (
            <SkillRow
              key={skill.code}
              skill={skill}
              busy={skillMutation.isPending}
              onUpdate={(payload) => skillMutation.mutate({ code: skill.code, payload })}
            />
          ))}
        </div>
      </section>

      <PackDropSection skills={catalog.skills} busy={skillMutation.isPending} onUpdate={(code, payload) => skillMutation.mutate({ code, payload })} />

      <GrantTokensSection skills={grantable} />
      <LedgerSection />
    </div>
  );
}

function SkillRow({
  skill, busy, onUpdate,
}: { skill: SkillCatalogItem; busy: boolean; onUpdate: (payload: Parameters<typeof updateAdminSkill>[1]) => void }) {
  return (
    <div className="rounded-xl bg-bg-base p-3">
      <div className="flex flex-wrap items-center justify-between gap-2">
        <p className="flex items-center gap-1.5 font-semibold"><SkillIcon code={skill.code} size={16} /> {skill.name} <span className="font-mono text-xs text-slate-500">{skill.code}</span></p>
        <label className="flex items-center gap-2 text-xs">
          <input
            type="checkbox"
            checked={skill.is_enabled}
            disabled={busy || !skill.engine_supported}
            onChange={(e) => onUpdate({ is_enabled: e.target.checked })}
          />
          Доступен для получения
        </label>
      </div>
      <p className="mt-1 text-xs text-slate-400">{skill.effect}</p>
      <p className="mt-1 text-xs text-slate-500">
        Уровни: {skill.levels.map((l) => `${l.level_label} — ${l.bonus_pp} п.п.`).join(", ")}
      </p>
      {!skill.engine_supported && (
        <div className="mt-2 rounded-lg bg-amber-500/10 p-2 text-xs text-amber-300">
          {skill.unavailable_reason}
          {skill.remaining_work.length > 0 && (
            <ul className="mt-1 list-disc pl-4 text-amber-200/80">
              {skill.remaining_work.map((w) => <li key={w}>{w}</li>)}
            </ul>
          )}
        </div>
      )}
      <div className="mt-2 flex flex-wrap items-center gap-2 text-xs">
        <span className="text-slate-400">Позиции:</span>
        {skill.max_positions.map((pos) => {
          const checked = skill.positions.includes(pos);
          return (
            <label key={pos} className="flex items-center gap-1">
              <input
                type="checkbox"
                checked={checked}
                disabled={busy || (checked && skill.positions.length === 1)}
                onChange={(e) => {
                  const next = e.target.checked
                    ? [...skill.positions, pos]
                    : skill.positions.filter((p) => p !== pos);
                  onUpdate(next.length === skill.max_positions.length ? { reset_positions: true } : { allowed_positions: next });
                }}
              />
              {pos}
            </label>
          );
        })}
      </div>
    </div>
  );
}

function GrantTokensSection({ skills }: { skills: SkillCatalogItem[] }) {
  const [userId, setUserId] = useState("");
  const [skillCode, setSkillCode] = useState(skills[0]?.code ?? "");
  const [quantity, setQuantity] = useState(1);
  const [reason, setReason] = useState("");
  // A fresh key per grant form submission: a double click replays instead of
  // granting twice.
  const [key, setKey] = useState(() => crypto.randomUUID());
  const [message, setMessage] = useState<string | null>(null);
  const queryClient = useQueryClient();

  const numericUserId = Number(userId);
  const { data: balances } = useQuery({
    queryKey: ["admin-skill-tokens", numericUserId],
    queryFn: () => fetchAdminUserSkillTokens(numericUserId),
    enabled: numericUserId > 0,
    retry: false,
  });

  const grant = useMutation({
    mutationFn: () => grantSkillTokens({ user_id: numericUserId, skill_code: skillCode, quantity, reason, idempotency_key: key }),
    onSuccess: (tokens) => {
      setMessage("Готово");
      setKey(crypto.randomUUID());
      queryClient.setQueryData(["admin-skill-tokens", numericUserId], tokens);
      queryClient.invalidateQueries({ queryKey: ["admin-skill-ledger"] });
    },
    onError: (err) => setMessage(errorText(err)),
  });

  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">Выдать жетоны</p>
      <p className="mb-3 text-xs text-slate-400">
        Каждая выдача пишется в журнал навыков и журнал администратора. Отрицательное количество — корректировка (баланс
        не уходит ниже нуля).
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <input value={userId} onChange={(e) => setUserId(e.target.value)} placeholder="ID пользователя" className="rounded-lg bg-bg-base px-3 py-2 outline-none" />
        <select value={skillCode} onChange={(e) => setSkillCode(e.target.value)} className="rounded-lg bg-bg-base px-3 py-2 outline-none">
          {skills.map((s) => <option key={s.code} value={s.code}>{s.name}</option>)}
        </select>
        <input type="number" value={quantity} onChange={(e) => setQuantity(Number(e.target.value))} className="rounded-lg bg-bg-base px-3 py-2 outline-none" />
        <input value={reason} onChange={(e) => setReason(e.target.value)} placeholder="Причина" className="rounded-lg bg-bg-base px-3 py-2 outline-none" />
      </div>
      <div className="mt-3 flex items-center gap-3">
        <button
          onClick={() => { setMessage(null); grant.mutate(); }}
          disabled={grant.isPending || !(numericUserId > 0) || !reason.trim() || quantity === 0}
          className="rounded-xl bg-floodlight px-4 py-2 text-sm font-bold text-bg-base disabled:opacity-40"
        >
          Выдать
        </button>
        {message && <span className="text-xs text-slate-400">{message}</span>}
      </div>
      {balances && (
        <p className="mt-3 text-xs text-slate-400">
          Баланс жетонов: {balances.map((b) => `${b.skill_code}: ${b.quantity}`).join(" · ")}
        </p>
      )}
    </section>
  );
}

const KIND_LABELS: Record<string, string> = {
  grant_task: "Задание",
  grant_tournament: "Турнир",
  grant_admin: "Выдача админом",
  revoke_admin: "Списание админом",
  assign: "Назначение",
  upgrade: "Улучшение",
  replace: "Замена",
};

function LedgerSection() {
  const [userFilter, setUserFilter] = useState("");
  const userId = Number(userFilter) > 0 ? Number(userFilter) : undefined;
  const { data: entries } = useQuery({
    queryKey: ["admin-skill-ledger", userId],
    queryFn: () => fetchSkillLedger({ user_id: userId, limit: 200 }),
  });
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <div className="mb-3 flex items-center justify-between gap-3">
        <p className="font-display text-base font-bold">История операций</p>
        <input value={userFilter} onChange={(e) => setUserFilter(e.target.value)} placeholder="ID пользователя" className="w-40 rounded-lg bg-bg-base px-3 py-1.5 text-sm outline-none" />
      </div>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3">Дата</th>
              <th className="py-1 pr-3">Игрок</th>
              <th className="py-1 pr-3">Операция</th>
              <th className="py-1 pr-3">Навык</th>
              <th className="py-1 pr-3">Жетоны</th>
              <th className="py-1 pr-3">Монеты</th>
              <th className="py-1 pr-3">Карточка</th>
              <th className="py-1 pr-3">Комментарий</th>
            </tr>
          </thead>
          <tbody>
            {entries?.map((e) => (
              <tr key={e.id} className="border-t border-white/5">
                <td className="py-1 pr-3 text-slate-400">{new Date(e.created_at).toLocaleString("ru-RU")}</td>
                <td className="py-1 pr-3">{e.user_id}</td>
                <td className="py-1 pr-3">{KIND_LABELS[e.kind] ?? e.kind}</td>
                <td className="py-1 pr-3">
                  {e.from_skill_code ? `${e.from_skill_code} ${e.from_level} → ` : ""}{e.to_skill_code ? `${e.to_skill_code} ${e.to_level}` : e.skill_code}
                </td>
                <td className="py-1 pr-3 font-mono">{e.token_delta > 0 ? `+${e.token_delta}` : e.token_delta} ({e.token_balance_after})</td>
                <td className="py-1 pr-3 font-mono">{e.coins_spent || ""}</td>
                <td className="py-1 pr-3">{e.user_card_id ?? ""}</td>
                <td className="py-1 pr-3 text-slate-400">{e.reason ?? ""}{e.admin_id ? ` (админ ${e.admin_id})` : ""}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PackDropSection({
  skills, busy, onUpdate,
}: {
  skills: SkillCatalogItem[];
  busy: boolean;
  onUpdate: (code: string, payload: Parameters<typeof updateAdminSkill>[1]) => void;
}) {
  const totalWeight = skills.filter((s) => s.is_available).reduce((sum, s) => sum + s.pack_drop_weight, 0);
  return (
    <section className="rounded-2xl border border-white/5 bg-bg-surface p-4">
      <p className="mb-1 font-display text-base font-bold">Жетоны в паках</p>
      <p className="mb-3 text-xs text-slate-400">
        Как у стадионов: в «Паки» у каждого пака задаётся «Шанс жетона навыка» на слот (100% — пак навыков).
        Если слот выпал жетоном, навык выбирается по весам ниже, количество — из колонки «Жетонов за слот».
        Вес 0 — навык не выпадает. Закрытые для получения навыки не выпадают.
      </p>
      <div className="overflow-x-auto">
        <table className="w-full text-left text-xs">
          <thead className="text-slate-500">
            <tr>
              <th className="py-1 pr-3">Навык</th>
              <th className="py-1 pr-3">Вес</th>
              <th className="py-1 pr-3">Доля</th>
              <th className="py-1 pr-3">Жетонов за слот</th>
            </tr>
          </thead>
          <tbody>
            {skills.map((skill) => (
              <PackDropRow key={skill.code} skill={skill} totalWeight={totalWeight} busy={busy} onUpdate={onUpdate} />
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function PackDropRow({
  skill, totalWeight, busy, onUpdate,
}: {
  skill: SkillCatalogItem;
  totalWeight: number;
  busy: boolean;
  onUpdate: (code: string, payload: Parameters<typeof updateAdminSkill>[1]) => void;
}) {
  const [weight, setWeight] = useState(skill.pack_drop_weight);
  const [quantity, setQuantity] = useState(skill.pack_drop_quantity);
  useEffect(() => { setWeight(skill.pack_drop_weight); setQuantity(skill.pack_drop_quantity); }, [skill.pack_drop_weight, skill.pack_drop_quantity]);
  const dirty = weight !== skill.pack_drop_weight || quantity !== skill.pack_drop_quantity;
  const share = skill.is_available && totalWeight > 0 ? Math.round((skill.pack_drop_weight / totalWeight) * 100) : 0;
  return (
    <tr className="border-t border-white/5">
      <td className="py-1.5 pr-3"><SkillTokenIcon code={skill.code} size={14} className="mr-1 inline-block align-[-2px]" />{skill.name}{!skill.is_available && <span className="text-slate-500"> (закрыт)</span>}</td>
      <td className="py-1.5 pr-3">
        <input
          type="number" min={0} value={weight} disabled={!skill.engine_supported}
          onChange={(e) => setWeight(Math.max(0, Number(e.target.value)))}
          className="w-20 rounded-lg bg-bg-base px-2 py-1 outline-none disabled:opacity-40"
        />
      </td>
      <td className="py-1.5 pr-3 font-mono text-slate-400">{share}%</td>
      <td className="py-1.5 pr-3">
        <div className="flex items-center gap-2">
          <input
            type="number" min={1} value={quantity} disabled={!skill.engine_supported}
            onChange={(e) => setQuantity(Math.max(1, Number(e.target.value)))}
            className="w-20 rounded-lg bg-bg-base px-2 py-1 outline-none disabled:opacity-40"
          />
          {dirty && (
            <button
              onClick={() => onUpdate(skill.code, { pack_drop_weight: weight, pack_drop_quantity: quantity })}
              disabled={busy}
              className="rounded-lg bg-floodlight px-2 py-1 font-bold text-bg-base disabled:opacity-40"
            >
              Сохранить
            </button>
          )}
        </div>
      </td>
    </tr>
  );
}
