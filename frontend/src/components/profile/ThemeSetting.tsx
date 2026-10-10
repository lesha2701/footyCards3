import { useUiStore, type ThemePreference } from "@/store/uiStore";

const OPTIONS: { value: ThemePreference; label: string }[] = [
  { value: "auto", label: "Как в Telegram" },
  { value: "dark", label: "Тёмная" },
  { value: "light", label: "Светлая" },
];

export default function ThemeSetting() {
  const preference = useUiStore((s) => s.preference);
  const setPreference = useUiStore((s) => s.setPreference);
  return (
    <section className="rounded-2xl bg-bg-surface p-4">
      <p className="font-display text-base font-bold text-ink-chalk">Тема</p>
      <div className="mt-3 grid grid-cols-3 gap-1 rounded-xl bg-bg-raised p-1" role="radiogroup" aria-label="Тема оформления">
        {OPTIONS.map((o) => (
          <button
            key={o.value}
            role="radio"
            aria-checked={preference === o.value}
            onClick={() => setPreference(o.value)}
            className={`rounded-lg py-2 text-xs font-semibold transition ${
              preference === o.value ? "bg-floodlight text-bg-base" : "text-ink-mist"
            }`}
          >
            {o.label}
          </button>
        ))}
      </div>
    </section>
  );
}
