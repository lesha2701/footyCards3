import { useState } from "react";

/** Art for «Агентская лицензия»: drop the file at frontend/public/market/agent-badge.webp
 * (square, transparent). Until it exists the emoji stands in. */
export const AGENT_BADGE_SRC = "/market/agent-badge.webp";

export function AgentIcon({ size = 16, className = "" }: { size?: number; className?: string }) {
  const [broken, setBroken] = useState(false);
  if (broken) {
    return (
      <span aria-hidden className={className} style={{ fontSize: size * 0.9, lineHeight: 1 }}>
        🕴️
      </span>
    );
  }
  return (
    <img
      src={AGENT_BADGE_SRC}
      alt=""
      aria-hidden
      width={size}
      height={size}
      className={`inline-block object-contain ${className}`}
      onError={() => setBroken(true)}
    />
  );
}

/** «Агент» chip next to a seller's name: they hold an active license. */
export default function AgentBadge() {
  return (
    <span
      className="inline-flex items-center gap-1 rounded-full bg-amber-400/15 px-1.5 py-0.5 text-micro font-bold text-amber-300"
      title="Агентская лицензия"
    >
      <AgentIcon size={12} />
      Агент
    </span>
  );
}
