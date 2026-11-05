/** «⏳ Лимитка · до 20.11» on a shop tile: a seasonal event's item, on sale until `until`. */
export default function LimitedBadge({ until, className = "" }: { until: string | null | undefined; className?: string }) {
  if (!until) return null;
  const date = new Date(until).toLocaleDateString("ru-RU", { day: "2-digit", month: "2-digit" });
  return (
    <span className={`inline-block whitespace-nowrap rounded-full bg-gradient-to-r from-fuchsia-500 to-orange-400 px-1.5 py-0.5 text-micro font-bold leading-none text-white ${className}`}>
      ⏳ Лимитка · до {date}
    </span>
  );
}
