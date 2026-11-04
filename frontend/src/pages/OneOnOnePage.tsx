import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimOneOnOneReward, playOneOnOneAttack, startOneOnOne } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import AttackRun from "@/components/oneOnOne/AttackRun";
import { formatGameError } from "@/lib/errors";
import { hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { OneOnOneAttack, OneOnOneOutcome, OneOnOneResult, OneOnOneStartResult, UserCard } from "@/types";

const OUTCOME: Record<OneOnOneOutcome, { label: string; className: string }> = {
  goal: { label: "ГОЛ!", className: "text-accent-lime" },
  save: { label: "Сейв", className: "text-accent-cyan" },
  tackle: { label: "Вратарь забрал", className: "text-accent-cyan" },
  miss: { label: "Мимо", className: "text-ink-mist" },
  lost: { label: "Момент упущен", className: "text-ink-mist" },
  dispossessed: { label: "Отбор", className: "text-ink-mist" },
  intercepted: { label: "Перехват", className: "text-ink-mist" },
  offside: { label: "Офсайд", className: "text-ink-mist" },
  cleared: { label: "Вынесли", className: "text-ink-mist" },
  blocked: { label: "Блок", className: "text-accent-cyan" },
};

type Series = OneOnOneStartResult & { card: UserCard };

/** «Атака 1 на 1»: pick a card, then a series of breakaways at the keeper
 * from server-chosen spots. The episode runs here from the finger, frame
 * for frame what the server will replay from the input timeline it gets —
 * the server alone decides the outcome and the coins. */
export default function OneOnOnePage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [series, setSeries] = useState<Series | null>(null);
  const [attack, setAttack] = useState<OneOnOneAttack | null>(null);
  const [results, setResults] = useState<OneOnOneResult[]>([]);
  const [finished, setFinished] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");

  const { data: collection } = useQuery({
    queryKey: ["collection", "one-on-one", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: series === null,
  });

  const start = useMutation({
    mutationFn: (card: UserCard) => startOneOnOne(card.id).then((data) => ({ ...data, card })),
    onSuccess: (data) => {
      setSeries(data);
      setAttack(data.attack);
      setResults([]);
      setFinished(false);
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать серию")),
  });

  const claim = useMutation({
    mutationFn: () => claimOneOnOneReward(series!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
    },
  });

  if (!series || !attack) {
    return (
      <div className="flex flex-col gap-5">
        <GameHero game="one-on-one" title="Атака 1 на 1" />
        <p className="text-sm text-ink-mist">
          Выход один на один с вратарём, управление как в FIFA. Левый палец — джойстик: веди игрока с мячом, до края —
          спринт; куда он наклонён в момент удара — туда и летит мяч. «Удар»: держи и отпусти — удар подъёмом, чем
          дольше держишь, тем сильнее и выше (шкала покраснела — над перекладиной); свайп вверх с кнопки — удар на
          закрутку; тап — игрок всё выберет сам. Маленькая кнопка — парашют. Резкий рывок вбок с «Удара» — финт
          (поймаешь вратаря на нём — он провалится).
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open={!start.isPending}
          title="Кто выходит один на один?"
          cards={collection?.items ?? []}
          onSelect={(card) => start.mutate(card)}
          onClose={() => navigate("/play")}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      </div>
    );
  }

  const total = results.length ? results[results.length - 1].total_coins : 0;

  if (finished) {
    return (
      <div className="flex flex-col items-center gap-5 py-10 text-center">
        <p className="font-display text-2xl font-bold text-ink-chalk">Серия завершена</p>
        <div className="flex flex-wrap justify-center gap-2">
          {results.map((r, i) => (
            <span key={i} className={`rounded-lg bg-bg-surface px-2 py-1 text-xs font-semibold ${OUTCOME[r.outcome].className}`}>
              {OUTCOME[r.outcome].label}
            </span>
          ))}
        </div>
        <p className="text-sm text-ink-mist">
          Голов: {results.filter((r) => r.outcome === "goal").length} из {results.length} · Итог:{" "}
          <span className="inline-flex items-center gap-1 font-mono font-bold text-accent-lime">
            {total}
            <IconCoin size={14} />
          </span>
        </p>
        {claim.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claim.data ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claim.data.reward_coins}
              <IconCoin size={16} />
            </p>
            {claim.data.reward_coins === 0 && total > 0 && (
              <p className="mt-1 text-xs text-ink-mist">Лимит наградных серий на сегодня исчерпан</p>
            )}
          </div>
        ) : claim.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(claim.error, "Не удалось начислить награду")}
          </p>
        ) : null}
        <button
          onClick={() => start.mutate(series.card)}
          disabled={start.isPending}
          className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
        >
          {start.isPending ? "Начинаем…" : "Сыграть ещё серию"}
        </button>
        {start.isError && (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">
            {formatGameError(start.error, "Не удалось начать серию")}
          </p>
        )}
        <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Вернуться к играм
        </button>
      </div>
    );
  }

  return (
    <AttackRun
      seed={attack.seed}
      index={attack.attack_index}
      total={series.total_attacks}
      rating={series.rating}
      name={series.card.player.display_name}
      ball={series.ball}
      feint={series.feint}
      coins={total}
      results={results.map((r) => r.outcome)}
      nextLabel={attack.attack_index + 1 >= series.total_attacks ? "Итоги серии" : "Следующая атака"}
      submit={(timeline) => playOneOnOneAttack(series.session_id, timeline)}
      onBack={async () => {
        if (await showConfirm("Серия не закончена — оставшиеся атаки сгорят. Выйти?")) navigate("/play");
      }}
      onFeint={(feint) => setSeries((s) => (s ? { ...s, feint } : s))}
      onResult={(r) => setResults((prev) => [...prev, r])}
      onNext={(r) => {
        if (r.next_attack) setAttack(r.next_attack);
        else {
          setFinished(true);
          claim.mutate();
        }
      }}
    />
  );
}
