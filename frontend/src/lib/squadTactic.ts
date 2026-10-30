/** Where the tactic under the «Состав» cards is drawn (pure). */

/** A row of cards on the «Состав» pitch, in px from its top. */
export interface Band { top: number; bottom: number; mid: number }

/** Where the defensive line is drawn for a block: pushed up towards the
 * midfield, between the lines, or dropped towards the keeper. */
export function lineY(block: string | undefined, mid: Band, def: Band, gk: Band | undefined): number {
  if (block === "high") return mid.bottom + (def.top - mid.bottom) * 0.25;
  if (block === "low") return def.bottom + ((gk?.top ?? def.bottom + 24) - def.bottom) * 0.55;
  return (mid.bottom + def.top) / 2;
}
