import { useQuery } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { fetchArtifacts } from "@/api/monetization";
import ArtifactTile from "@/components/artifacts/ArtifactTile";
import { IconChevronRight } from "@/components/icons";

/** «Мой игрок» → Имущество: the active artifacts meant for him and what
 * they give, with a way to the shelf/shop. Hidden while artifacts are off. */
export default function MyPlayerArtifacts() {
  const navigate = useNavigate();
  const { data: catalog } = useQuery({ queryKey: ["artifacts"], queryFn: fetchArtifacts });
  if (!catalog?.enabled) return null;
  const mine = catalog.shelf.filter((c) => c.equipped && c.artifact.target === "my_player");
  return (
    <button onClick={() => navigate("/artifacts")} className="flex items-center gap-3 rounded-2xl bg-bg-surface p-4 text-left active:scale-[0.99]">
      <span className="flex -space-x-3">
        {mine.slice(0, 3).map((c) => <ArtifactTile key={c.copy_id} artifact={c.artifact} size="sm" />)}
        {!mine.length && <span className="flex h-14 w-14 items-center justify-center rounded-2xl border border-dashed border-white/15 text-2xl">🏺</span>}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-display text-sm font-bold text-ink-chalk">Артефакты</span>
        <span className="block text-xs text-accent-lime">
          {catalog.effects.my_player.map((e) => e.label).join(" · ") || "Дай своему игроку артефакт — например, футболку легенды"}
        </span>
      </span>
      <IconChevronRight size={16} className="shrink-0 text-ink-mist-dim" />
    </button>
  );
}
