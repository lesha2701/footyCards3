// Art of «Штаб» items (skins, cars, rooms) by item code: assets/manager/staff/<code>.webp.
// An item without a file is drawn from its `art` palette (StaffPortrait / OfficeScene).
const files = import.meta.glob("../assets/manager/staff/*.webp", { eager: true, import: "default" }) as Record<string, string>;

const BY_CODE: Record<string, string> = Object.fromEntries(
  Object.entries(files).map(([path, url]) => [path.slice(path.lastIndexOf("/") + 1, -".webp".length), url]),
);

export function staffArt(code: string | null | undefined): string | undefined {
  return code ? BY_CODE[code] : undefined;
}
