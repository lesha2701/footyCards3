import { IconCoin } from "@/components/icons";

/** «Докупить 132 ◎ · от 25 ⭐» — opens the coin top-up right where the
 * player is short. */
export default function TopUpButton({
  need, stars, onClick, className = "rounded-full py-1.5 text-xs",
}: {
  need: number;
  stars: number | null;
  onClick: () => void;
  className?: string;
}) {
  return (
    <button
      onClick={onClick}
      className={`flex w-full items-center justify-center gap-1 bg-amber-400 font-bold text-bg-base active:scale-95 ${className}`}
    >
      Докупить {need.toLocaleString("ru-RU")} <IconCoin size={12} />
      {stars != null && <span className="font-semibold opacity-80">· от {stars} ⭐</span>}
    </button>
  );
}
