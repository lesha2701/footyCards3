import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";

import { changeCardSkill, fetchCardSkillState } from "@/api/cardSkills";
import { IconCoin, IconUpgrade, IconWarning } from "@/components/icons";
import { SkillIcon } from "@/components/icons/skills";
import { ApiRequestError } from "@/lib/api";
import { SKILL_LEVEL_LABELS, invalidateAfterSkillChange, skillByCode, useSkillCatalog } from "@/lib/cardSkills";
import { formatGameError } from "@/lib/errors";
import { haptic, hapticNotify } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { CardSkillState, SkillAction, SkillCatalogItem } from "@/types";

/** "Навык" block of the card detail modal. Works on ONE specific copy: when
 * the player owns several copies of this footballer, a copy switcher picks
 * which one (each copy has its own skill). Every number shown here (bonus,
 * costs, token counts) comes from the server; the confirmation sends the
 * exact state and price the player saw, so a stale screen can never be
 * charged a different amount. */
export default function CardSkillPanel({ cardId }: { cardId: number }) {
  const [selectedId, setSelectedId] = useState(cardId);
  const [picker, setPicker] = useState<"assign" | "replace" | null>(null);
  const [pending, setPending] = useState<{ action: SkillAction; key: string } | null>(null);
  const [error, setError] = useState<string | null>(null);
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: catalog } = useSkillCatalog();
  const { data: state, isLoading } = useQuery({
    queryKey: ["card-skills", "card", selectedId],
    queryFn: () => fetchCardSkillState(selectedId),
  });

  const mutation = useMutation({
    mutationFn: ({ action, key }: { action: SkillAction; key: string }) =>
      changeCardSkill(selectedId, {
        operation: action.operation,
        skill_code: action.operation === "upgrade" ? undefined : action.skill_code,
        expected_skill_code: state?.skill?.code ?? null,
        expected_level: state?.skill?.level ?? null,
        expected_token_cost: action.token_cost,
        expected_coin_cost: action.coin_cost,
        idempotency_key: key,
      }),
    onSuccess: (data) => {
      hapticNotify("success");
      updateBalance(data.new_balance);
      setPending(null);
      setPicker(null);
      setError(null);
      invalidateAfterSkillChange(queryClient);
    },
    onError: (err) => {
      hapticNotify("error");
      setPending(null);
      setError(formatGameError(err, "Не удалось изменить навык"));
      const reason = err instanceof ApiRequestError ? err.details?.reason : undefined;
      if (reason === "stale_state" || reason === "price_changed" || reason === "card_locked") {
        queryClient.invalidateQueries({ queryKey: ["card-skills"] });
      }
    },
  });

  if (isLoading || !state) {
    return <div className="mt-3 h-20 animate-pulse rounded-xl bg-black/20" />;
  }

  const skills = catalog?.skills ?? [];
  const current = skillByCode(skills, state.skill?.code);
  const upgrade = state.actions.find((a) => a.operation === "upgrade");
  const hasAssign = state.actions.some((a) => a.operation === "assign");
  const hasReplace = state.actions.some((a) => a.operation === "replace");

  const openConfirm = (action: SkillAction) => {
    if (!action.allowed || mutation.isPending) return;
    haptic("light");
    setError(null);
    // One key per confirmation: a double tap or a network retry of the same
    // confirmation replays on the server instead of charging twice.
    setPending({ action, key: crypto.randomUUID() });
  };

  return (
    <div className="mt-3 rounded-xl bg-black/20 p-3">
      <div className="flex items-center justify-between">
        <p className="text-xs font-semibold uppercase tracking-wide text-ink-mist">Навык</p>
        {state.copies.length > 1 && (
          <select
            value={selectedId}
            onChange={(e) => { setSelectedId(Number(e.target.value)); setPicker(null); setError(null); }}
            className="rounded-lg bg-bg-raised px-2 py-1 text-[11px] text-ink-chalk outline-none"
          >
            {state.copies.map((c) => {
              const s = skillByCode(skills, c.skill_code);
              return (
                <option key={c.id} value={c.id}>
                  № {c.serial_number}{s && c.skill_level ? ` · ${s.name} ${SKILL_LEVEL_LABELS[c.skill_level]}` : ""}
                </option>
              );
            })}
          </select>
        )}
      </div>

      {state.skill && current ? (
        <div className="mt-2">
          <p className="flex items-center gap-1.5 text-sm font-semibold text-ink-chalk">
            <SkillIcon code={current.code} size={16} className="text-accent-lime" aria-hidden />
            {current.name} {state.skill.level_label}
          </p>
          <p className="mt-1 text-xs text-ink-mist">
            {current.effect} — на <b className="text-accent-lime">{state.skill.bonus_pp} п.п.</b>
          </p>
          <SkillScope skill={current} />
          {state.next_level_bonus_pp !== null && (
            <p className="mt-1 text-[11px] text-ink-mist-dim">
              Уровень {SKILL_LEVEL_LABELS[state.skill.level + 1]}: {state.next_level_bonus_pp} п.п.
            </p>
          )}
          {state.skill.level >= 3 && <p className="mt-1 text-[11px] text-ink-mist-dim">Максимальный уровень.</p>}
          {!state.skill.is_effective && (
            <p className="mt-1.5 flex items-start gap-1 text-[11px] text-amber-300">
              <IconWarning size={12} className="mt-0.5 shrink-0" />
              Сейчас навык не действует в матчах (выключено администратором или не подходит позиции карточки).
            </p>
          )}
        </div>
      ) : (
        <p className="mt-2 text-xs text-ink-mist">
          У этого экземпляра нет навыка. Навык усиливает одно конкретное действие в матче и не меняет рейтинг карточки.
        </p>
      )}

      {state.blocked_reason && (
        <p className="mt-2 flex items-start gap-1 text-[11px] text-ink-mist">
          <IconWarning size={12} className="mt-0.5 shrink-0" />
          {state.blocked_reason}
        </p>
      )}

      <div className="mt-2 flex flex-wrap gap-2">
        {upgrade && (
          <button
            onClick={() => openConfirm(upgrade)}
            disabled={!upgrade.allowed || mutation.isPending}
            className="flex flex-1 items-center justify-center gap-1 rounded-xl bg-bg-raised px-3 py-2 text-xs font-semibold text-accent-lime disabled:opacity-40"
          >
            <IconUpgrade size={13} />
            Улучшить до {SKILL_LEVEL_LABELS[upgrade.target_level]}
          </button>
        )}
        {hasAssign && (
          <button
            onClick={() => setPicker(picker === "assign" ? null : "assign")}
            disabled={!!state.blocked_reason}
            className="flex-1 rounded-xl bg-bg-raised px-3 py-2 text-xs font-semibold text-accent-lime disabled:opacity-40"
          >
            Назначить навык
          </button>
        )}
        {hasReplace && (
          <button
            onClick={() => setPicker(picker === "replace" ? null : "replace")}
            disabled={!!state.blocked_reason}
            className="flex-1 rounded-xl bg-white/5 px-3 py-2 text-xs font-semibold text-ink-mist disabled:opacity-40"
          >
            Заменить
          </button>
        )}
      </div>
      {upgrade && !upgrade.allowed && upgrade.reason && !state.blocked_reason && (
        <p className="mt-1 text-[11px] text-ink-mist-dim">{upgrade.reason}</p>
      )}

      {picker && (
        <SkillPicker
          actions={state.actions.filter((a) => a.operation === picker)}
          skills={skills}
          onPick={openConfirm}
        />
      )}

      {error && <p className="mt-2 rounded-lg bg-red-500/10 px-2 py-1.5 text-[11px] text-red-400">{error}</p>}

      {pending && (
        <SkillConfirmSheet
          state={state}
          action={pending.action}
          skills={skills}
          busy={mutation.isPending}
          onCancel={() => !mutation.isPending && setPending(null)}
          onConfirm={() => !mutation.isPending && mutation.mutate(pending)}
        />
      )}
    </div>
  );
}

function SkillScope({ skill }: { skill: SkillCatalogItem }) {
  return (
    <details className="mt-1 text-[11px] text-ink-mist-dim">
      <summary className="cursor-pointer select-none">Где работает</summary>
      <ul className="mt-1 list-disc pl-4">
        {skill.applies_in.map((line) => <li key={line}>{line}</li>)}
      </ul>
      <p className="mt-1">{skill.not_affected}</p>
    </details>
  );
}

function SkillPicker({
  actions, skills, onPick,
}: { actions: SkillAction[]; skills: SkillCatalogItem[]; onPick: (a: SkillAction) => void }) {
  // Skills this card can actually take first, then the rest with their reasons.
  const ordered = [...actions].sort(
    (a, b) =>
      Number(b.allowed) - Number(a.allowed)
      || skills.findIndex((s) => s.code === a.skill_code) - skills.findIndex((s) => s.code === b.skill_code),
  );
  return (
    <div className="mt-2 flex flex-col gap-1.5">
      {ordered.map((action) => {
        const skill = skillByCode(skills, action.skill_code);
        return (
          <button
            key={action.skill_code}
            onClick={() => onPick(action)}
            disabled={!action.allowed}
            className="rounded-xl bg-bg-raised px-3 py-2 text-left disabled:opacity-50"
          >
            <div className="flex items-center justify-between gap-2">
              <span className="text-xs font-semibold text-ink-chalk">
                <SkillIcon code={action.skill_code} size={14} className="mr-1 inline-block align-[-2px] text-accent-lime" aria-hidden />
                {skill?.name ?? action.skill_code}
              </span>
              <span className="flex items-center gap-1 font-mono text-[10px] text-ink-mist">
                жетоны {action.tokens_owned}/{action.token_cost}
                {action.coin_cost > 0 && (<> · <IconCoin size={10} />{action.coin_cost}</>)}
              </span>
            </div>
            {skill && <p className="mt-0.5 text-[10px] text-ink-mist-dim">{skill.effect}</p>}
            {!action.allowed && action.reason && <p className="mt-0.5 text-[10px] text-amber-300">{action.reason}</p>}
          </button>
        );
      })}
    </div>
  );
}

function SkillConfirmSheet({
  state, action, skills, busy, onCancel, onConfirm,
}: {
  state: CardSkillState;
  action: SkillAction;
  skills: SkillCatalogItem[];
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  const target = skillByCode(skills, action.skill_code);
  const current = skillByCode(skills, state.skill?.code);
  const targetBonus = target?.levels.find((l) => l.level === action.target_level)?.bonus_pp;
  const title = { assign: "Назначить навык?", upgrade: "Улучшить навык?", replace: "Заменить навык?" }[action.operation];
  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/60 backdrop-blur-sm sm:items-center" onClick={onCancel}>
      <div
        className="safe-bottom w-full max-w-sm rounded-t-3xl border border-white/10 bg-bg-surface p-5 sm:rounded-3xl"
        onClick={(e) => e.stopPropagation()}
      >
        <p className="font-display text-lg text-ink-chalk">{title}</p>
        <p className="mt-1 text-xs text-ink-mist">
          {state.player_name} · экземпляр № {state.serial_number}
        </p>
        <div className="mt-3 grid grid-cols-2 gap-2 text-xs">
          <div className="rounded-xl bg-black/20 p-2">
            <p className="text-ink-mist-dim">Сейчас</p>
            <p className="mt-0.5 font-semibold text-ink-chalk">
              {state.skill && current ? (
                <span className="inline-flex items-center gap-1">
                  <SkillIcon code={current.code} size={13} aria-hidden />
                  {current.name} {state.skill.level_label}
                </span>
              ) : "Нет навыка"}
            </p>
          </div>
          <div className="rounded-xl bg-black/20 p-2">
            <p className="text-ink-mist-dim">Станет</p>
            <p className="mt-0.5 font-semibold text-accent-lime">
              {target ? (
                <span className="inline-flex items-center gap-1">
                  <SkillIcon code={target.code} size={13} aria-hidden />
                  {target.name} {SKILL_LEVEL_LABELS[action.target_level]}
                </span>
              ) : action.skill_code}
            </p>
            {targetBonus !== undefined && <p className="text-[10px] text-ink-mist">{targetBonus} п.п.</p>}
          </div>
        </div>
        <div className="mt-3 rounded-xl bg-black/20 p-2 text-xs text-ink-mist">
          Спишется: <b className="text-ink-chalk">{action.token_cost}</b> жетон(ов) «{target?.name ?? action.skill_code}»
          {action.coin_cost > 0 && (
            <> и <b className="inline-flex items-center gap-0.5 text-ink-chalk"><IconCoin size={11} />{action.coin_cost}</b> монет</>
          )}
          .
        </div>
        {action.operation === "replace" && state.skill && current && (
          <p className="mt-3 flex items-start gap-1.5 rounded-xl bg-red-500/10 p-2 text-xs text-red-300">
            <IconWarning size={14} className="mt-0.5 shrink-0" />
            Текущий навык «{current.name}» {state.skill.level_label} будет уничтожен. Потраченные на него жетоны не вернутся,
            новый навык начнётся с уровня I.
          </p>
        )}
        <div className="mt-5 flex gap-3">
          <button onClick={onCancel} disabled={busy} className="flex-1 rounded-2xl bg-white/5 py-3 text-sm font-semibold text-ink-mist active:scale-95">
            Отмена
          </button>
          <button
            onClick={onConfirm}
            disabled={busy}
            className={`flex-1 rounded-2xl py-3 text-sm font-semibold active:scale-95 disabled:opacity-50 ${
              action.operation === "replace" ? "bg-red-500 text-white" : "bg-floodlight text-bg-base"
            }`}
          >
            {busy ? "..." : "Подтвердить"}
          </button>
        </div>
      </div>
    </div>
  );
}
