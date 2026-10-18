import { useIsNew } from "@/lib/seenSections";

/** Small «NEW» pill shown until the player opens the section once. */
export default function NewBadge({ section, className = "" }: { section: string; className?: string }) {
  const fresh = useIsNew(section);
  if (!fresh) return null;
  return (
    <span className={`inline-block rounded-full bg-accent-lime px-1.5 py-0.5 align-middle text-micro font-bold uppercase leading-none text-bg-base ${className}`}>
      Новое
    </span>
  );
}
