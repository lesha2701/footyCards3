/** «Как бить» / «Как отбивать» for the 3D shootout: a card over the scene
 * with a looping swipe drawing per tip. Shown the first time the player
 * shoots and the first time they keep goal; the «?» button brings it back. */

export type HowToRole = "shoot" | "keep";

/** A swipe drawn on a goal: the finger's path (viewBox 0 0 120 80). */
type Demo = { path: string; label: string; hint: string };

const GOAL = "M14 66 V18 H106 V66";

const DEMOS: Record<HowToRole, { title: string; demos: Demo[]; footer: string }> = {
  shoot: {
    title: "Как бить",
    demos: [
      { path: "M60 76 L28 34", label: "В угол", hint: "Свайп от мяча к воротам — куда ведёшь, туда и летит." },
      { path: "M60 76 L84 22", label: "Выше", hint: "Длиннее свайп — выше мяч. Слишком длинный — над перекладиной." },
      { path: "M60 76 Q96 56 80 30", label: "Закрутка", hint: "Изогни свайп дугой — мяч обойдёт вратаря по дуге." },
      { path: "M60 76 L60 52", label: "Парашют", hint: "Медленный свайп — мягкий удар навесом по центру." },
    ],
    footer: "Быстрый свайп — сильный удар. Вратарь бота иногда прыгает заранее: бей в другой угол.",
  },
  keep: {
    title: "Как отбивать",
    demos: [
      { path: "M60 52 L24 52", label: "В угол", hint: "Свайп влево или вправо — прыжок в этот угол." },
      { path: "M60 52 L88 24", label: "Верхний угол", hint: "Свайп по диагонали вверх — прыжок под перекладину." },
      { path: "M60 52 L60 22", label: "По центру верхом", hint: "Свайп прямо вверх — выпрыгивает в центре." },
      { path: "M60 52 L60 52", label: "Стоять", hint: "Ничего не делаешь — стоит в центре и сам берёт удар в себя." },
    ],
    footer: "Свайпай в момент удара — когда бьющий касается мяча. Прыгнешь раньше — он увидит и пробьёт в другую сторону.",
  },
};

function SwipeDemo({ path, delay }: { path: string; delay: number }) {
  const still = /^M(\S+) (\S+) L\1 \2$/.test(path);
  return (
    <svg viewBox="0 0 120 80" className="h-16 w-24 shrink-0" aria-hidden>
      <path d={GOAL} fill="none" stroke="currentColor" strokeOpacity={0.5} strokeWidth={3} className="text-ink-chalk" />
      {!still && (
        <path
          d={path}
          fill="none"
          stroke="rgb(198,230,58)"
          strokeWidth={5}
          strokeLinecap="round"
          pathLength={1}
          strokeDasharray="1 1"
          style={{ animation: `howto-draw 1.6s ${delay}s ease-in-out infinite` }}
        />
      )}
      {still ? (
        <circle cx={60} cy={52} r={6} fill="rgb(198,230,58)" style={{ animation: "howto-pulse 1.6s ease-in-out infinite" }} />
      ) : (
        <circle r={6} fill="rgb(198,230,58)">
          <animateMotion dur="1.6s" begin={`${delay}s`} repeatCount="indefinite" path={path} keyPoints="0;1;1" keyTimes="0;0.6;1" calcMode="linear" />
        </circle>
      )}
    </svg>
  );
}

export default function PenaltyHowTo({ role, onClose }: { role: HowToRole; onClose: () => void }) {
  const { title, demos, footer } = DEMOS[role];
  return (
    <div className="absolute inset-0 z-20 flex items-center justify-center bg-black/60 p-4" onPointerDown={(e) => e.stopPropagation()}>
      <style>{`
        @keyframes howto-draw { 0% { stroke-dashoffset: 1 } 60%, 100% { stroke-dashoffset: 0 } }
        @keyframes howto-pulse { 0%, 100% { opacity: 1 } 50% { opacity: 0.35 } }
      `}</style>
      <div className="flex w-full max-w-sm flex-col gap-3 rounded-2xl bg-bg-surface p-4 text-ink-chalk shadow-xl">
        <h2 className="font-display text-xl">{title}</h2>
        {demos.map((d, i) => (
          <div key={d.label} className="flex items-center gap-3">
            <SwipeDemo path={d.path} delay={i * 0.2} />
            <div className="flex flex-col">
              <span className="text-sm font-semibold">{d.label}</span>
              <span className="text-caption text-ink-mist">{d.hint}</span>
            </div>
          </div>
        ))}
        <p className="text-caption text-ink-mist">{footer}</p>
        <button type="button" onClick={onClose} className="rounded-xl bg-accent px-6 py-3 font-semibold text-black">
          Понятно
        </button>
      </div>
    </div>
  );
}
