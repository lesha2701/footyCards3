import { useTelegramMainButton } from "@/lib/useTelegramMainButton";

/** A screen's single primary action (e.g. «Начать игру»). Inside Telegram it
 * becomes the native bottom MainButton — shown while this component is
 * mounted, hidden again when it unmounts (the hook's cleanup), so rendering
 * it only on the start screen is all a page has to do. Outside Telegram it
 * renders the regular in-page button. */
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
  const native = useTelegramMainButton({ text, onClick, enabled: !disabled, loading });
  if (native) return null;
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
