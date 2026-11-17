import type { MagicRun } from "@/types";

/** Inside the run's playable map (a tall band of the grid on new maps). */
export function inMap(run: MagicRun, x: number, y: number): boolean {
  if (x < 0 || y < 0 || x >= run.map_w || y >= run.map_h) return false;
  const s = run.map_shape;
  return !s || (Math.abs(x - y) <= s[0] && x + y >= s[1] && x + y <= s[2]);
}

// Rows can be wider than 32 cells (hardcore), so no 32-bit `>>` here.
// Rows come as hex strings too (`seen_hex`): wider than 53 cells a JS number loses the low bits.
export const isSeen = (run: MagicRun, x: number, y: number) => {
  const hex = run.seen_hex?.[y];
  if (hex === undefined) return Math.floor((run.seen[y] ?? 0) / 2 ** x) % 2;
  const digit = hex.length - 1 - (x >> 2);
  return digit < 0 ? 0 : (parseInt(hex[digit], 16) >> (x & 3)) & 1;
};

/** Client copy of the engine's path (magic_engine.map_path): 4-way, terrain
 *  blocks, untaken objects (and markets / mines) and the rival stop the walk. */
export function mapPath(run: MagicRun, goal: [number, number]): [number, number][] | null {
  const blocked = new Set(run.blocks.map(([x, y]) => `${x},${y}`));
  const stoppers = new Set(
    run.objects.filter((o) => o.kind !== "castle" && (!o.taken_by || o.kind === "market" || o.kind === "mine")).map((o) => `${o.x},${o.y}`),
  );
  if (run.bot.visible && run.bot.x !== undefined && run.bot.y !== undefined) stoppers.add(`${run.bot.x},${run.bot.y}`);
  const start = `${run.hero.x},${run.hero.y}`;
  const goalKey = `${goal[0]},${goal[1]}`;
  const prev = new Map<string, string | null>([[start, null]]);
  const queue: [number, number][] = [[run.hero.x, run.hero.y]];
  while (queue.length) {
    const [x, y] = queue.shift()!;
    const key = `${x},${y}`;
    if (key === goalKey) break;
    if (key !== start && stoppers.has(key)) continue;
    for (const [dx, dy] of [[1, 0], [-1, 0], [0, 1], [0, -1]]) {
      const nx = x + dx;
      const ny = y + dy;
      const k = `${nx},${ny}`;
      if (!inMap(run, nx, ny) || prev.has(k) || blocked.has(k)) continue;
      prev.set(k, key);
      queue.push([nx, ny]);
    }
  }
  if (!prev.has(goalKey)) return null;
  const path: [number, number][] = [];
  let cur: string | null = goalKey;
  while (cur) {
    const [x, y] = cur.split(",").map(Number);
    path.unshift([x, y]);
    cur = prev.get(cur) ?? null;
  }
  return path;
}
