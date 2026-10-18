import type { ClubSponsorTier } from "@/types";

const STYLES: Record<ClubSponsorTier, { label: string; className: string }> = {
  bronze: { label: "Меценат", className: "bg-gradient-to-br from-[#F6C99A] to-[#8C5A2B] text-[#2A1606]" },
  silver: { label: "Меценат", className: "bg-gradient-to-br from-white to-[#8A929C] text-[#1C2026]" },
  gold: { label: "Меценат", className: "bg-gradient-to-br from-[#FFF3B0] to-[#C8961B] text-[#2B1E00]" },
};

const TITLES: Record<ClubSponsorTier, string> = {
  bronze: "Бронзовый меценат клуба",
  silver: "Серебряный меценат клуба",
  gold: "Золотой меценат клуба",
};

/** «Казна за Stars» sponsor badge next to a member's name. */
export function SponsorBadge({ tier }: { tier: ClubSponsorTier }) {
  const style = STYLES[tier];
  return (
    <span title={TITLES[tier]} className={`inline-flex shrink-0 items-center gap-0.5 rounded-full px-1.5 py-0.5 text-micro font-bold ${style.className}`}>
      ★ {style.label}
    </span>
  );
}
