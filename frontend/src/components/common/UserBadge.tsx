import { staticUrl } from "@/lib/api";
import type { Badge } from "@/types";

export function UserBadge({ badge, className = "" }: { badge: Badge | null | undefined; className?: string }) {
  if (!badge) return null;
  if (badge.image_path) {
    return (
      <img
        src={staticUrl(badge.image_path) ?? undefined}
        alt={badge.name}
        title={badge.name}
        className={`inline-block h-4 w-4 shrink-0 rounded-full object-cover ${className}`}
      />
    );
  }
  return (
    <span
      title={badge.name}
      className={`inline-flex shrink-0 items-center justify-center text-sm leading-none ${className}`}
    >
      {badge.icon}
    </span>
  );
}
