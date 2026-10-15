import type { Match } from "@/types";

const STATUS_TEXT: Record<string, string> = {
  no_attempts: "попытки на сегодня закончились — купи ещё в «Пути» карточки",
  limit: "дневной лимит этого режима исчерпан",
  duplicate: "уже засчитано",
};

/** After the whistle: the «Академия» talents that applied from kickoff and
 * the experience each path card earned (or why it did not). Renders nothing
 * for a match without path cards. */
export default function MatchPathSummary({ match }: { match: Pick<Match, "talent_notes" | "path_progress" | "reward_coins"> }) {
  const talents = (match.talent_notes ?? []).filter((t) => t.bonus > 0 || t.aura);
  const progress = (match.path_progress ?? []).filter((p) => p.status !== "not_path");
  if (!talents.length && !progress.length) return null;
  return (
    <div className="rounded-xl border border-emerald-400/25 bg-emerald-400/5 px-3 py-2 text-[11px]">
      <p className="font-semibold text-path">🌱 Академия</p>
      {talents.map((t, i) => (
        <p key={`t${i}`} className="text-ink-mist">
          {t.emoji} {t.name} {t.level_label}
          {t.player ? ` (${t.player})` : ""}: {t.aura ? `+${t.bonus} соседям` : `+${t.bonus}`} с начала матча
        </p>
      ))}
      {progress.map((p) => (
        <p key={p.user_card_id} className="text-ink-chalk">
          {p.status === "awarded" ? (
            <>
              +{p.xp} опыта
              {p.levels.length > 0 && <span className="text-path"> · рейтинг {p.levels[p.levels.length - 1]}</span>}
              {p.stages.length > 0 && <span className="font-semibold text-legend"> · новый этап!</span>}
            </>
          ) : (
            <span className="text-ink-mist">Опыт не начислен: {STATUS_TEXT[p.status] ?? p.status}</span>
          )}
        </p>
      ))}
      {match.reward_coins === 0 && progress.length === 0 && (
        <p className="text-ink-mist">Опыт начисляется только за наградные матчи</p>
      )}
    </div>
  );
}
