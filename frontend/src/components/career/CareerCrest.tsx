import Emblem from "@/components/manager/Emblem";
import { careerCrest } from "@/lib/careerCrest";

/** The club's crest in «Карьера тренера», drawn from its name (lib/careerCrest). */
export function CareerCrest({ name, size = 20, className = "" }: { name: string | null | undefined; size?: number; className?: string }) {
  if (!name) return null;
  return <Emblem look={careerCrest(name)} size={size} className={className} />;
}
