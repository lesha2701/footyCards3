/** A screen's single primary action (e.g. «Начать игру»). Always an
 * in-page button: Telegram's native MainButton (lib/useTelegramMainButton)
 * did not show up for some players, leaving mini-game start screens with no
 * way to start — a start button must never depend on it. */
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
    <button
      onClick={onClick}
      disabled={disabled || loading}
      className="rounded-2xl bg-floodlight py-3.5 font-display text-base font-bold text-bg-base active:scale-95 disabled:opacity-50"
    >
      {loading ? loadingText : text}
    </button>
  );
}
