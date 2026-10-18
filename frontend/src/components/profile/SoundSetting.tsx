import { useState } from "react";

import { playSound, setSoundEnabled, soundEnabled } from "@/lib/sound";

/** «Звуки»: short chimes on card reveals and rewards (per device). */
export default function SoundSetting() {
  const [on, setOn] = useState(soundEnabled);
  return (
    <label className="flex min-h-[52px] items-center justify-between gap-3 rounded-2xl bg-bg-surface px-4 py-3">
      <span>
        <span className="block font-display text-base font-bold text-ink-chalk">Звуки</span>
        <span className="block text-xs text-ink-mist">Открытие карт и награды</span>
      </span>
      <input
        type="checkbox"
        checked={on}
        onChange={(e) => {
          setSoundEnabled(e.target.checked);
          setOn(e.target.checked);
          if (e.target.checked) playSound("reward");
        }}
        className="h-5 w-5 accent-accent-lime"
        aria-label="Звуки"
      />
    </label>
  );
}
