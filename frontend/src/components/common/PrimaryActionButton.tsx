import StickyActionBar from "@/components/common/StickyActionBar";

/** A screen's single primary action (e.g. «Начать игру»): our own button,
 * pinned above the bottom navigation (StickyActionBar) so it is always in
 * reach. Not Telegram's native MainButton (lib/useTelegramMainButton) — it
 * did not show up for some players, leaving start screens with no way to
 * start. */
export default function PrimaryActionButton({
  text,
  loadingText = "Загрузка...",
  onClick,
  disabled = false,
  loading = false,
}: {
  text: string;
  loadingText?: string;
  onClick: () => void;
  disabled?: boolean;
  loading?: boolean;
}) {
  return (
    <StickyActionBar>
      <button
        onClick={onClick}
        disabled={disabled || loading}
        className="w-full rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base shadow-lg shadow-black/40 active:scale-95 disabled:opacity-50"
      >
        {loading ? loadingText : text}
      </button>
    </StickyActionBar>
  );
}
