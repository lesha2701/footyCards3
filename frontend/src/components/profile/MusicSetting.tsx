import { useState } from "react";

import { musicEnabled, musicVolume, nextMusicTrack, setMusicEnabled, setMusicVolume, toggleMusicPause, TRACKS } from "@/lib/music";
import { useMusic } from "@/lib/useMusic";

/** «Музыка»: the soundtrack on / off, the player (⏯ ⏭) and the volume (per device). */
export default function MusicSetting() {
  const [on, setOn] = useState(musicEnabled);
  const [volume, setVolume] = useState(() => Math.round(musicVolume() * 100));
  const { track, playing } = useMusic();
  return (
    <div className="rounded-2xl bg-bg-surface px-4 py-3" data-testid="music-setting">
      <label className="flex min-h-[28px] items-center justify-between gap-3">
        <span>
          <span className="block font-display text-base font-bold text-ink-chalk">Музыка</span>
          <span className="block text-xs text-ink-mist">Саундтрек VICTOR FC · {TRACKS.length} треков</span>
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
        <>
          <div className="mt-3 flex items-center gap-2 rounded-xl bg-black/20 p-2">
            <span className="flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-accent-lime/15 text-lg">🎵</span>
            <span className="min-w-0 flex-1">
              <span className="block truncate text-sm font-bold text-ink-chalk">{track?.title ?? "Campeones"}</span>
              <span className="block text-[11px] text-ink-mist">{playing ? "Играет" : "На паузе"}</span>
            </span>
            <button
              onClick={toggleMusicPause}
              className="h-9 w-9 rounded-full bg-white/10 text-base active:scale-95"
              aria-label={playing ? "Пауза" : "Играть"}
              data-testid="music-toggle"
            >
              {playing ? "⏸" : "▶️"}
            </button>
            <button
              onClick={nextMusicTrack}
              className="h-9 w-9 rounded-full bg-white/10 text-base active:scale-95"
              aria-label="Следующий трек"
              data-testid="music-next"
            >
              ⏭
            </button>
          </div>
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
        </>
      )}
    </div>
  );
}
