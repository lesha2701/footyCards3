import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { useNavigate } from "react-router-dom";

import { fetchCollection } from "@/api/collection";
import { claimOtvetkaReward, playOtvetkaEpisode, startOtvetka } from "@/api/games";
import CardPickerModal from "@/components/cards/CardPickerModal";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import AttackRun from "@/components/oneOnOne/AttackRun";
import SetPieceRun from "@/components/oneOnOne/SetPieceRun";
import { formatGameError } from "@/lib/errors";
import { shirtPrint } from "@/lib/gameGear";
import type { QuantizedSwipe } from "@/lib/freeKick3d/trajectory";
import type { EpisodeTimeline } from "@/lib/oneOnOne/engine";
import { hapticNotify, showConfirm } from "@/lib/telegram";
import { useAuthStore } from "@/store/authStore";
import type { OneOnOneOutcome, OtvetkaEpisode, OtvetkaEpisodeKind, OtvetkaResult, OtvetkaStartResult, UserCard } from "@/types";

const TITLE: Record<OtvetkaEpisodeKind, string> = {
  penalty: "Пенальти",
  free_kick: "Штрафной",
  one_on_one: "Выход 1 на 1",
  two_v_one: "2 на 1",
  three_v_two: "3 на 2",
  through_ball: "Пас в разрез",
  cross: "Навес / прострел",
};

const HINT: Partial<Record<OtvetkaEpisodeKind, string>> = {
  one_on_one: "Обыграй вратаря и бей. Рывок вбок с «Удара» — финт.",
  two_v_one: "Отвлеки защитника и отдай пас, ответный идёт в свободную зону.",
  three_v_two: "Найди свободного: «Пас» — в ноги, «Разрез» — на ход.",
  through_ball: "Дождись рывка партнёра и отдай «Разрез», пока он в игре.",
  cross: "«Навес»: держи — сила и высота, тап — прострел. Потом сразу «Удар».",
};

const OUTCOME: Record<OneOnOneOutcome, string> = {
  goal: "Гол",
  save: "Сейв",
  tackle: "Вратарь забрал",
  miss: "Мимо",
  lost: "Момент упущен",
  dispossessed: "Отбор",
  intercepted: "Перехват",
  offside: "Офсайд",
  cleared: "Вынесли",
  blocked: "Блок",
  wall: "В стенку",
};

const signOf = (e: OtvetkaEpisode) => (e.minute === null ? "Серия пенальти" : `${e.minute}′ · ${TITLE[e.kind]}`);

type Match = OtvetkaStartResult & { card: UserCard };
type Played = { episode: OtvetkaEpisode; result: OtvetkaResult };

/** «Ответка»: pick a card, then a match of ten episodes at match minutes.
 * Each runs here from the finger, frame for frame what the server will
 * replay from the input it gets; the opponent's answer to an episode comes
 * back only with that episode's verdict. */
export default function OtvetkaPage() {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const [match, setMatch] = useState<Match | null>(null);
  const [episode, setEpisode] = useState<OtvetkaEpisode | null>(null);
  const [played, setPlayed] = useState<Played[]>([]);
  // The last episode the player has seen end: the score waits for the ball.
  const [seen, setSeen] = useState(-1);
  const [finished, setFinished] = useState(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [cardSearch, setCardSearch] = useState("");
  const answer = useRef<OtvetkaResult | null>(null);

  const { data: collection } = useQuery({
    queryKey: ["collection", "otvetka", cardSearch],
    queryFn: () => fetchCollection({ page_size: 100, sort_by: "rating", sort_dir: "desc", search: cardSearch || undefined }),
    enabled: match === null,
  });

  const start = useMutation({
    mutationFn: (card: UserCard) => startOtvetka(card.id).then((data) => ({ ...data, card })),
    onSuccess: (data) => {
      setMatch(data);
      setEpisode(data.episode);
      setPlayed([]);
      setSeen(-1);
      setFinished(false);
      setErrorMsg(null);
      void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
    },
    onError: (err) => setErrorMsg(formatGameError(err, "Не удалось начать матч")),
  });

  const claim = useMutation({
    mutationFn: () => claimOtvetkaReward(match!.session_id),
    onSuccess: (data) => {
      updateBalance(data.new_balance);
      hapticNotify("success");
    },
  });

  if (!match || !episode) {
    return (
      <div className="flex flex-col gap-5">
        <GameHero game="otvetka" title="Ответка" />
        <p className="text-sm text-ink-mist">
          Матч из 10 эпизодов: пенальти, штрафные, выходы 1 на 1, 2 на 1, 3 на 2, пасы в разрез и навесы. Ты играешь
          эпизод, соперник на него отвечает. Ничья — серия пенальти до первой ошибки. Пока соперник — бот.
        </p>
        {errorMsg && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{errorMsg}</p>}
        <CardPickerModal
          open={!start.isPending}
          title="Кто выходит на матч?"
          cards={collection?.items ?? []}
          onSelect={(card) => start.mutate(card)}
          onClose={() => navigate("/play")}
          searchValue={cardSearch}
          onSearchChange={setCardSearch}
        />
      </div>
    );
  }

  const settled = played.filter((p) => p.episode.episode_index <= seen);
  const lastPlayed = settled.length ? settled[settled.length - 1] : null;
  const last = lastPlayed?.result ?? null;
  const mine = last?.my_score ?? 0;
  const theirs = last?.opponent_score ?? 0;
  const coins = last?.total_coins ?? 0;
  const shootout = last && (last.shootout_my > 0 || last.shootout_opponent > 0 || episode.minute === null);

  if (finished && last) {
    const won = last.result === "win";
    return (
      <div className="flex flex-col items-center gap-4 py-8 text-center">
        <p className={`font-display text-2xl font-bold ${won ? "text-accent-lime" : "text-ink-chalk"}`}>{won ? "Победа!" : "Поражение"}</p>
        <p className="font-mono text-3xl font-bold text-ink-chalk">
          {mine} : {theirs}
          {shootout && (
            <span className="ml-2 text-lg text-ink-mist">
              (пен. {last.shootout_my} : {last.shootout_opponent})
            </span>
          )}
        </p>
        <div className="flex w-full max-w-sm flex-col gap-1 text-sm">
          {played.map(({ episode: e, result: r }) => (
            <div key={e.episode_index} className="flex items-center justify-between gap-2 rounded-lg bg-bg-surface px-3 py-1.5">
              <span className="w-10 shrink-0 text-left font-mono text-xs text-ink-mist">{e.minute === null ? "пен." : `${e.minute}′`}</span>
              <span className="flex-1 truncate text-left text-ink-chalk">{TITLE[e.kind]}</span>
              <span className={r.outcome === "goal" ? "font-semibold text-accent-lime" : "text-ink-mist"}>{OUTCOME[r.outcome]}</span>
              <span className={r.opponent_goal ? "w-14 text-right font-semibold text-red-300" : "w-14 text-right text-ink-mist"}>
                {r.opponent_goal ? "ответ" : "—"}
              </span>
            </div>
          ))}
        </div>
        {claim.isPending ? (
          <p className="text-sm text-ink-mist">Начисление награды...</p>
        ) : claim.data ? (
          <div className="rounded-2xl bg-accent-green/10 px-5 py-3">
            <p className="flex items-center justify-center gap-1.5 font-mono text-lg font-bold text-accent-green">
              Ты получил +{claim.data.reward_coins}
              <IconCoin size={16} />
            </p>
            {claim.data.reward_coins === 0 && (last.reward_coins ?? 0) > 0 && (
              <p className="mt-1 text-xs text-ink-mist">Лимит наградных матчей на сегодня исчерпан</p>
            )}
          </div>
        ) : claim.isError ? (
          <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{formatGameError(claim.error, "Не удалось начислить награду")}</p>
        ) : null}
        <button
          onClick={() => start.mutate(match.card)}
          disabled={start.isPending}
          className="rounded-2xl bg-accent px-6 py-3 font-semibold text-black disabled:opacity-50"
        >
          {start.isPending ? "Начинаем…" : "Сыграть ещё матч"}
        </button>
        {start.isError && <p className="rounded-xl bg-red-500/10 px-3 py-2 text-sm text-red-400">{formatGameError(start.error, "Не удалось начать матч")}</p>}
        <button onClick={() => navigate("/play")} className="rounded-2xl bg-white/5 px-5 py-2.5 text-sm font-semibold text-ink-mist">
          Вернуться к играм
        </button>
      </div>
    );
  }

  const label = signOf(episode);
  const bug = {
    index: episode.episode_index,
    total: match.total_episodes,
    results: settled.map((p) => p.result.outcome),
    coins,
    name: label,
    rating: match.rating,
    match: { mine, theirs, opponent: match.opponent, penalties: shootout && last ? ([last.shootout_my, last.shootout_opponent] as [number, number]) : undefined },
  };
  const send = async (body: { timeline: EpisodeTimeline } | { swipe: QuantizedSwipe }) => {
    const r = await playOtvetkaEpisode(match.session_id, body);
    answer.current = r;
    setPlayed((prev) => [...prev, { episode, result: r }]);
    return r;
  };
  const next = () => {
    const r = answer.current;
    if (r?.next_episode) setEpisode(r.next_episode);
    else {
      setFinished(true);
      claim.mutate();
    }
  };
  const verdict = last && lastPlayed?.episode === episode && (
    <div className="flex flex-col items-center gap-0.5">
      <div className={`font-display text-lg font-bold ${last.opponent_goal ? "text-red-300" : "text-ink-chalk"}`}>
        {last.opponent_goal ? `${match.opponent} ответил голом` : `${match.opponent} не ответил`}
      </div>
      <div className="font-mono text-sm text-ink-chalk/80">
        {shootout ? `пен. ${last.shootout_my} : ${last.shootout_opponent}` : `${last.my_score} : ${last.opponent_score}`}
        {last.coins_this_episode > 0 && ` · +${last.coins_this_episode}`}
      </div>
    </div>
  );
  const nextLabel = last?.is_finished ? "Итоги матча" : "Следующий эпизод";
  const onShown = () => setSeen(episode.episode_index);
  const onBack = async () => {
    if (await showConfirm("Матч не закончен — оставшиеся эпизоды сгорят. Выйти?")) navigate("/play");
  };

  if (episode.kind === "penalty" || episode.kind === "free_kick") {
    return (
      <SetPieceRun
        kind={episode.kind}
        seed={episode.seed}
        rating={match.rating}
        bug={bug}
        title={label}
        gear={{ ball: match.ball, kickerBoots: match.boots, kickerPrint: shirtPrint(match.card.player) }}
        celebration={match.celebration}
        nextLabel={nextLabel}
        note={verdict}
        submit={(swipe) => send({ swipe })}
        onShown={onShown}
        onBack={onBack}
        onNext={next}
      />
    );
  }

  return (
    <AttackRun
      seed={episode.seed}
      kind={episode.kind === "one_on_one" ? undefined : episode.kind}
      index={episode.episode_index}
      total={match.total_episodes}
      rating={match.rating}
      name={label}
      ball={match.ball}
      feint={match.feint}
      coins={coins}
      results={bug.results}
      match={bug.match}
      title={label}
      hint={HINT[episode.kind]}
      nextLabel={nextLabel}
      verdictNote={verdict}
      submit={async (timeline) => {
        const r = await send({ timeline });
        return {
          outcome: r.outcome, bonuses: [], feint: null, coins_this_attack: 0, total_coins: r.total_coins,
          is_finished: r.is_finished, next_attack: null,
        };
      }}
      onBack={onBack}
      onFeint={(feint) => setMatch((m) => (m ? { ...m, feint } : m))}
      onResult={() => undefined}
      onShown={onShown}
      onNext={next}
    />
  );
}
