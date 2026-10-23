import type { EquipmentItem } from "@/api/equipment";
import { staticUrl } from "@/lib/api";
import { RARITY_GRADIENTS } from "@/lib/rarity";

/** A thing's photo (or its icon) in a rarity frame. */
export default function EquipmentTile({
  item, size = "md", dimmed = false,
}: {
  item: Pick<EquipmentItem, "name" | "image_path" | "icon" | "rarity">;
  size?: "sm" | "md";
  dimmed?: boolean;
}) {
  const box = size === "sm" ? "h-12 w-12" : "h-16 w-16";
  return (
    <span className={`block shrink-0 rounded-2xl bg-gradient-to-b p-[2px] ${RARITY_GRADIENTS[item.rarity]} ${dimmed ? "opacity-50 grayscale" : ""}`}>
      <span className={`flex ${box} items-center justify-center overflow-hidden rounded-[14px] bg-bg-raised`}>
        {item.image_path ? (
          <img src={staticUrl(item.image_path)} alt={item.name} loading="lazy" decoding="async" className="h-full w-full object-cover" />
        ) : (
          <span className={size === "sm" ? "text-xl" : "text-3xl"} aria-hidden>{item.icon}</span>
        )}
      </span>
    </span>
  );
}
