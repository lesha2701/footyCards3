import type { StrategoPiece, StrategoRole } from "@/types";

export const ROLE_META: Record<StrategoRole, { label: string; glyph: string; hint: string }> = {
  cup: { label: "Кубок", glyph: "🏆", hint: "Не ходит. Захватят — матч проигран" },
  wall: { label: "Стенка", glyph: "🧱", hint: "Не ходит. Сносит любого атакующего, кроме Подкатчика" },
  star: { label: "Звезда", glyph: "⭐", hint: "Самая сильная карта. Уязвима только для атаки Провокатора" },
  tackler: { label: "Подкатчик", glyph: "🦵", hint: "Единственный, кто разбивает Стенку" },
  provocateur: { label: "Провокатор", glyph: "🎭", hint: "Атакуя, выбивает Звезду" },
  speedster: { label: "Скорость", glyph: "⚡", hint: "Бежит на любое расстояние по прямой" },
  regular: { label: "Игрок", glyph: "👟", hint: "Бьётся рейтингом" },
};

export function roleOfSlot(slot: string): StrategoRole {
  return slot.split("_")[0] as StrategoRole;
}

export const WIN_REASON_LABELS: Record<string, string> = {
  cup_captured: "Кубок захвачен",
  no_moves: "Не осталось ходов",
  move_limit: "Лимит ходов — по силе оставшихся фишек",
  forfeit: "Сдача",
  timeout: "Время на ход вышло",
};

/** UX-only mirror of stratego_engine.legal_moves for highlighting; the
 *  server re-validates every move. */
export function legalTargets(pieces: StrategoPiece[], piece: StrategoPiece, size: number): [number, number][] {
  if (!piece.mine || piece.role === "cup" || piece.role === "wall") return [];
  const occ = new Map(pieces.map((p) => [`${p.row}:${p.col}`, p]));
  const maxSteps = piece.role === "speedster" ? size : 1;
  const out: [number, number][] = [];
  for (const [dr, dc] of [[-1, 0], [1, 0], [0, -1], [0, 1]]) {
    let r = piece.row;
    let c = piece.col;
    for (let i = 0; i < maxSteps; i++) {
      r += dr;
      c += dc;
      if (r < 0 || c < 0 || r >= size || c >= size) break;
      const occupant = occ.get(`${r}:${c}`);
      if (occupant) {
        if (!occupant.mine) out.push([r, c]);
        break;
      }
      out.push([r, c]);
    }
  }
  return out;
}

/** Client twin of stratego_engine.auto_layout for the «Авто» button: cup on
 *  the back row (usually a corner), walls hugging it, the rest shuffled. */
export function autoLayout(slots: string[], size: number): Record<string, [number, number]> {
  const free: [number, number][] = [];
  for (const r of [0, 1]) for (let c = 0; c < size; c++) free.push([r, c]);
  const layout: Record<string, [number, number]> = {};
  const pick = (pool: [number, number][]) => pool[Math.floor(Math.random() * pool.length)];
  const take = (slot: string, cell: [number, number]) => {
    free.splice(free.findIndex(([r, c]) => r === cell[0] && c === cell[1]), 1);
    layout[slot] = cell;
  };
  const back = free.filter(([r]) => r === 1);
  const corners = back.filter(([, c]) => c === 0 || c === size - 1);
  take("cup", pick(Math.random() < 0.7 ? corners : back));
  const [cr, cc] = layout.cup;
  for (const slot of slots.filter((s) => roleOfSlot(s) === "wall")) {
    const near = free.filter(([r, c]) => Math.abs(r - cr) + Math.abs(c - cc) === 1);
    take(slot, pick(near.length ? near : free));
  }
  for (const slot of slots.filter((s) => !(s in layout)).sort(() => Math.random() - 0.5)) {
    take(slot, pick(free));
  }
  return layout;
}
