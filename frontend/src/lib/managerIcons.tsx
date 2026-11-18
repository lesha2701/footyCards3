// Icons of the «Менеджер» tabs and sub-tabs by code: assets/manager/icons/<code>.webp.
// A code without a file falls back to its emoji, so pictures can land one by one.
const files = import.meta.glob("../assets/manager/icons/*.webp", { eager: true, import: "default" }) as Record<string, string>;

const BY_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(files).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1, -".webp".length), url]),
);

export function managerIcon(code: string): string | undefined {
  return BY_CODE[code];
}

export function MIcon({ code, emoji, className = "h-6 w-6", emojiClass = "" }: {
  code: string; emoji: string; className?: string; emojiClass?: string;
}) {
  const src = BY_CODE[code];
  return src
    ? <img src={src} alt="" aria-hidden className={`${className} shrink-0 object-contain drop-shadow`} />
    : <span aria-hidden className={`leading-none ${emojiClass}`}>{emoji}</span>;
}
