import { useState } from "react";

import { musicEnabled, musicVolume, setMusicEnabled, setMusicVolume } from "@/lib/music";

/** «Музыка»: the menu theme on / off and its volume (per device). */
export default function MusicSetting() {
  const [on, setOn] = useState(musicEnabled);
  const [volume, setVolume] = useState(() => Math.round(musicVolume() * 100));
  return (
    <div className="rounded-2xl bg-bg-surface px-4 py-3" data-testid="music-setting">
      <label className="flex min-h-[28px] items-center justify-between gap-3">
        <span>
          <span className="block font-display text-base font-bold text-ink-chalk">Музыка</span>
          <span className="block text-xs text-ink-mist">Тема «Campeones» в меню и коллекции</span>
        </span>
        <input
          type="checkbox"
          checked={on}
          onChange={(e) => {
            setMusicEnabled(e.target.checked);
            setOn(e.target.checked);
          }}
          className="h-5 w-5 accent-accent-lime"
          aria-label="Музыка"
        />
      </label>
      {on && (
        <label className="mt-3 flex items-center gap-3 text-xs text-ink-mist">
          Громкость
          <input
            type="range"
            min={5}
            max={100}
            step={5}
            value={volume}
            onChange={(e) => {
              const v = Number(e.target.value);
              setVolume(v);
              setMusicVolume(v / 100);
            }}
            className="flex-1 accent-accent-lime"
            aria-label="Громкость музыки"
          />
          <span className="w-8 text-right font-mono">{volume}%</span>
        </label>
      )}
    </div>
  );
}
