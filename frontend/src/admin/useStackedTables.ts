import { useEffect, type RefObject } from "react";

/** Every admin table with a header turns into cards on a phone (see
 * `.admin-stack` in index.css): each cell is labelled with its column's
 * header text, so CSS can show «Колонка: значение» rows instead of a table
 * wider than the screen. Runs on any table that appears later too (pages,
 * tabs, refetches). A table can opt out with `data-keep-table`. */
export function useStackedTables(root: RefObject<HTMLElement>): void {
  useEffect(() => {
    const el = root.current;
    if (!el) return;
    let frame = 0;
    const label = () => {
      frame = 0;
      for (const table of el.querySelectorAll("table")) {
        if (table.hasAttribute("data-keep-table")) continue;
        const headRow = table.tHead?.rows[0];
        if (!headRow) continue;
        const names: string[] = [];
        for (const th of headRow.cells) {
          for (let i = 0; i < th.colSpan; i++) names.push((th.textContent || "").trim());
        }
        table.classList.add("admin-stack");
        for (const body of table.tBodies) {
          for (const row of body.rows) {
            let col = 0;
            for (const cell of row.cells) {
              const name = cell.colSpan > 1 ? "" : names[col] ?? "";
              if (cell.getAttribute("data-label") !== name) cell.setAttribute("data-label", name);
              col += cell.colSpan;
            }
          }
        }
      }
    };
    const schedule = () => {
      if (!frame) frame = requestAnimationFrame(label);
    };
    label();
    const observer = new MutationObserver(schedule);
    observer.observe(el, { childList: true, subtree: true });
    return () => {
      observer.disconnect();
      if (frame) cancelAnimationFrame(frame);
    };
  }, [root]);
}
