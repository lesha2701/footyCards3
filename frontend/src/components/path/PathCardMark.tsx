import { isLegendStage, stageIcon, talentByCode, talentLevelAt, usePathCatalog } from "@/lib/pathCards";

/** «Росток» chip for a «Академия» card: stage mark + talent emoji and its
 * level (I/II, dimmed while the talent is not unlocked yet). Sits in the
 * bottom-RIGHT corner of the image, opposite the skill badge, so it never
 * covers the face, rating, position or name. */
export default function PathCardMark({
  talentCode,
  stage,
  size = "md",
}: {
  talentCode: string;
  /** Stage of this copy; undefined = a design (album / pack) — no stage. */
  stage?: number;
  size?: "sm" | "md" | "lg";
}) {
  const { data: catalog } = usePathCatalog();
  const talent = talentByCode(catalog, talentCode);
  const level = stage != null ? talentLevelAt(catalog, stage) : 0;
  const legend = isLegendStage(catalog, stage);
  const stageName = stage != null ? catalog?.stages.find((s) => s.index === stage)?.name : undefined;
  const text = size === "sm" ? "text-[9px]" : "text-[10px]";
  return (
    <span
      title={[
        catalog?.title ?? "Академия",
        stageName,
        talent ? `${talent.name}${level ? ` ${level === 2 ? "II" : "I"}` : " — откроется на этапе «Основной»"}` : undefined,
      ].filter(Boolean).join(" · ")}
      className={`inline-flex items-center gap-0.5 rounded-full px-1.5 py-0.5 font-mono font-bold leading-none shadow ${text} ${
        legend ? "bg-amber-300/90 text-black" : "bg-emerald-950/80 text-emerald-200"
      }`}
    >
      <span aria-hidden>{stage != null ? stageIcon(stage) : "🌱"}</span>
      {talent && (
        <span className={level ? "" : "opacity-50 grayscale"} aria-label={talent.name}>
          {talent.emoji}
        </span>
      )}
      {level > 0 && <span>{level === 2 ? "II" : "I"}</span>}
    </span>
  );
}
