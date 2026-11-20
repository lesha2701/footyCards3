import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";

import { fetchZamesInfo, finishZames, startZames, type ZamesFinish } from "@/api/games";
import bossUrl from "@/assets/zames/boss-chief.webp";
import coverUrl from "@/assets/zames/cover.webp";
import GameHero from "@/components/common/GameHero";
import { IconCoin } from "@/components/icons";
import ZamesArena, { type ZamesResult } from "@/components/zames/ZamesArena";
import ZamesSkins from "@/components/zames/ZamesSkins";
import { setHeroSkin } from "@/components/zames/sprites";
import { formatGameError } from "@/lib/errors";
import { DERBY_WAVES, type Mode } from "@/lib/zames/engine";
import { useAuthStore } from "@/store/authStore";

const GESTURES: { icon: string; title: string; hint: string }[] = [
  { icon: "👆", title: "Тап", hint: "по сопернику — подбежать и бить; тапай быстро — серия до апперкота" },
  { icon: "👉", title: "Свайп ← →", hint: "удар ногой с разбега, отбрасывает далеко" },
  { icon: "🌀", title: "Свайп ↑ или круг", hint: "вертуха — раскидывает всех вокруг" },
  { icon: "👇", title: "Свайп ↓", hint: "подсечка — сбивает с ног" },
  { icon: "✋", title: "Удержание", hint: "блок: держи, когда над соперником «❗»" },
  { icon: "🔥", title: "Разнос", hint: "ярость набралась — жми кнопку и сноси всех" },
];

const RIVALS: { icon: string; name: string; hint: string }[] = [
  { icon: "🏃", name: "Шустрик", hint: "быстрый, слабый, лезет толпой" },
  { icon: "🦍", name: "Шкаф", hint: "лёгкие удары не чувствует — бей ногой или вертухой" },
  { icon: "🥁", name: "Барабанщик", hint: "держится сзади и заводит своих — догони его" },
  { icon: "📢", name: "Мегафон", hint: "орёт волной вдоль линии — уйди с неё или закройся" },
  { icon: "🧥", name: "Кузьмич", hint: "плюётся издалека — отойди или отбей плевок ударом" },
  { icon: "💺", name: "Креслолом", hint: "выламывает кресла и швыряет — отбей вертухой обратно" },
  { icon: "🍾", name: "Синяк (босс)", hint: "кидает бутылки веером и зовёт своих — бей по отбитым" },
];

type Phase = { k: "lobby" } | { k: "fight"; mode: Mode; seed: number; runId: number } | { k: "result"; mode: Mode; result: ZamesResult };

export default function ZamesPage() {
  const queryClient = useQueryClient();
  const updateBalance = useAuthStore((s) => s.updateBalance);
  const { data: info } = useQuery({ queryKey: ["zames-info"], queryFn: fetchZamesInfo });
  const [phase, setPhase] = useState<Phase>({ k: "lobby" });
  const [error, setError] = useState<string | null>(null);
  const [starting, setStarting] = useState(false);
  const [reward, setReward] = useState<ZamesFinish | null>(null);
  const [rewardError, setRewardError] = useState<string | null>(null);
  const session = useRef<number | null>(null);
  const runs = useRef(0);

  const start = async (mode: Mode) => {
    setError(null);
    setStarting(true);
    setReward(null);
    setRewardError(null);
    session.current = null;
    let seed: number;
    try {
      const out = await startZames(mode);
      session.current = out.session_id;
      seed = out.seed;
    } catch (err) {
      setError(formatGameError(err, "Не удалось начать замес"));
      setStarting(false);
      return;
    }
    setStarting(false);
    setHeroSkin(info?.skin);
    runs.current += 1;
    setPhase({ k: "fight", mode, seed, runId: runs.current });
  };

  const finish = (mode: Mode, result: ZamesResult) => {
    setPhase({ k: "result", mode, result });
    const id = session.current;
    session.current = null;
    if (id === null) {
      setRewardError("Этот замес без награды");
      return;
    }
    void finishZames(id, { waves: result.waves, knockouts: result.knockouts, best_combo: result.bestCombo, won: result.won })
      .then((done) => {
        setReward(done);
        updateBalance(done.new_balance);
        void queryClient.invalidateQueries({ queryKey: ["zames-info"] });
        void queryClient.invalidateQueries({ queryKey: ["game-limits"] });
        void queryClient.invalidateQueries({ queryKey: ["tasks"] });
      })
      .catch((err) => setRewardError(formatGameError(err, "Награду получить не удалось")));
  };

  if (phase.k === "fight") {
    return (
      <ZamesArena
        key={phase.runId}
        mode={phase.mode}
        seed={phase.seed}
        onFinish={(r) => finish(phase.mode, r)}
        onExit={() => {
          session.current = null;
          setPhase({ k: "lobby" });
        }}
      />
    );
  }

  if (phase.k === "result") {
    const r = phase.result;
    const title = phase.mode === "derby" ? (r.won ? "Сектор твой!" : "Тебя вынесли") : "Пар выпущен";
    return (
      <div className="flex min-h-full flex-col gap-4 px-4 pb-8 pt-4">
        <div className="relative overflow-hidden rounded-3xl bg-bg-surface p-5 text-center ring-1 ring-white/10">
          <img src={coverUrl} alt="" aria-hidden className="absolute inset-0 h-full w-full object-cover opacity-25 blur-sm" />
          <div className="relative">
            <p className="text-5xl">{r.won ? "🏆" : phase.mode === "endless" ? "💨" : "🤕"}</p>
            <h1 className="mt-2 font-display text-3xl font-black text-ink-chalk">{title}</h1>
            <div className="mt-4 grid grid-cols-3 gap-2">
              <Stat label="Отметелил" value={r.knockouts} />
              <Stat label="Волн" value={phase.mode === "derby" ? `${r.waves}/${DERBY_WAVES}` : r.waves} />
              <Stat label="Комбо" value={`×${r.bestCombo}`} />
            </div>
            <div className="mt-4 min-h-[2.5rem] text-body font-bold">
              {reward ? (
                reward.reward_coins > 0 ? (
                  <span className="inline-flex items-center gap-1.5 text-lime-300">
                    +{reward.reward_coins} <IconCoin className="h-5 w-5" />
                  </span>
                ) : (
                  <span className="text-ink-mist">{reward.daily_cap_reached ? "Награды за замесы на сегодня закончились" : "Без награды"}</span>
                )
              ) : rewardError ? (
                <span className="text-ink-mist">{rewardError}</span>
              ) : (
                <span className="text-ink-mist">Считаем…</span>
              )}
              {reward?.new_record ? <p className="mt-1 text-caption text-yellow-300">Новый рекорд: {reward.best_knockouts} 🥊</p> : null}
            </div>
          </div>
        </div>
        <button type="button" onClick={() => void start(phase.mode)} disabled={starting} className="rounded-2xl bg-lime-400 py-3.5 font-display text-lg font-black text-black disabled:opacity-60">
          Ещё замес
        </button>
        <button type="button" onClick={() => setPhase({ k: "lobby" })} className="rounded-2xl bg-white/10 py-3 font-bold text-ink-chalk ring-1 ring-white/15">
          В меню
        </button>
        {error ? <p className="text-center text-caption text-red-300">{error}</p> : null}
      </div>
    );
  }

  return (
    <div className="flex flex-col gap-4 px-4 pb-8 pt-3">
      <GameHero game="zames" title="Замес">
        {info ? (
          <span className="rounded-full bg-white/5 px-2.5 py-1 text-caption text-ink-mist ring-1 ring-white/10">
            Рекорд: <b className="text-yellow-300">{info.best_knockouts}</b> 🥊
          </span>
        ) : null}
      </GameHero>

      <div className="relative overflow-hidden rounded-3xl ring-1 ring-white/10">
        <img src={coverUrl} alt="" className="aspect-[4/3] w-full object-cover object-center" />
        <div className="absolute inset-x-0 bottom-0 bg-gradient-to-t from-black/90 via-black/60 to-transparent p-4 pt-12">
          <p className="font-display text-2xl font-black leading-tight text-white">Толпа на одного.<br />Выпусти пар!</p>
          <p className="mt-1 text-caption text-white/75">Махай кулаками, бей с вертухи и раскидывай фанатов соперника</p>
        </div>
      </div>

      <div className="grid gap-3">
        <button
          type="button"
          disabled={starting}
          onClick={() => void start("derby")}
          className="relative overflow-hidden rounded-3xl bg-gradient-to-br from-red-600 to-orange-500 p-4 text-left shadow-[0_12px_30px_-12px_rgba(255,90,40,0.8)] disabled:opacity-60"
        >
          <img src={bossUrl} alt="" aria-hidden className="absolute -right-4 -top-2 h-32 w-32 object-contain drop-shadow-[0_6px_10px_rgba(0,0,0,0.5)]" />
          <p className="font-display text-xl font-black text-white">⚔️ Дерби</p>
          <p className="mt-0.5 max-w-[65%] text-caption text-white/85">{DERBY_WAVES - 1} волн и босс: «Главный по сектору» или Синяк</p>
          {info ? (
            <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-black/30 px-2.5 py-1 text-caption font-bold text-white">
              до {info.base_coins + info.wave_coins * Math.min(DERBY_WAVES, info.max_waves)} <IconCoin className="h-4 w-4" />
            </p>
          ) : null}
        </button>
        <button
          type="button"
          disabled={starting}
          onClick={() => void start("endless")}
          className="rounded-3xl bg-gradient-to-br from-teal-500 to-lime-500 p-4 text-left shadow-[0_12px_30px_-12px_rgba(120,220,80,0.7)] disabled:opacity-60"
        >
          <p className="font-display text-xl font-black text-black">💨 Выпусти пар</p>
          <p className="mt-0.5 text-caption text-black/75">Волны без конца — бей, пока стоишь на ногах</p>
          {info ? (
            <p className="mt-2 inline-flex items-center gap-1 rounded-full bg-black/15 px-2.5 py-1 text-caption font-bold text-black">
              {info.base_coins} + {info.wave_coins} за волну <IconCoin className="h-4 w-4" />
            </p>
          ) : null}
        </button>
        {info ? (
          <p className="text-center text-caption text-ink-mist">
            Наградных замесов сегодня: <b className="text-ink-chalk">{info.rewarded_left}</b> из {info.daily_limit}
          </p>
        ) : null}
        {error ? <p className="text-center text-caption text-red-300">{error}</p> : null}
      </div>

      <ZamesSkins />

      <section className="rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
        <h2 className="font-display text-base font-bold text-ink-chalk">Как драться</h2>
        <div className="mt-3 grid grid-cols-2 gap-2">
          {GESTURES.map((g) => (
            <div key={g.title} className="rounded-2xl bg-white/5 p-2.5">
              <p className="text-body font-bold text-ink-chalk">
                <span className="mr-1">{g.icon}</span>
                {g.title}
              </p>
              <p className="mt-0.5 text-micro leading-snug text-ink-mist">{g.hint}</p>
            </div>
          ))}
        </div>
      </section>

      <section className="rounded-3xl bg-bg-surface p-4 ring-1 ring-white/10">
        <h2 className="font-display text-base font-bold text-ink-chalk">Кто полезет</h2>
        <div className="mt-3 grid gap-2">
          {RIVALS.map((r) => (
            <div key={r.name} className="flex items-center gap-3 rounded-2xl bg-white/5 p-2.5">
              <span className="text-2xl">{r.icon}</span>
              <div>
                <p className="text-body font-bold text-ink-chalk">{r.name}</p>
                <p className="text-micro text-ink-mist">{r.hint}</p>
              </div>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="rounded-2xl bg-black/30 p-2.5 ring-1 ring-white/10">
      <p className="font-display text-2xl font-black text-ink-chalk">{value}</p>
      <p className="text-micro text-ink-mist">{label}</p>
    </div>
  );
}
