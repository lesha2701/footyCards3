import { render } from "@testing-library/react";
import { useRef } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import type { Tactic } from "@/api/career";
import { SquadTacticLayer } from "@/components/career/SquadTacticLayer";

// jsdom lays nothing out: the pitch is 300×600, rows by their data-row.
const ROWS: Record<string, [number, number]> = { FWD: [30, 100], MID: [130, 200], DEF: [230, 300], GK: [330, 400] };
afterEach(() => vi.restoreAllMocks());

function Pitch({ tactic }: { tactic?: Tactic }) {
  const ref = useRef<HTMLDivElement>(null);
  return (
    <div ref={ref} data-testid="pitch">
      <SquadTacticLayer containerRef={ref} tactic={tactic} lineLabel="высокий прессинг" />
      {Object.keys(ROWS).map((k) => <div key={k} data-row={k} />)}
    </div>
  );
}

function layout() {
  vi.spyOn(HTMLElement.prototype, "getBoundingClientRect").mockImplementation(function (this: HTMLElement) {
    const [top, bottom] = ROWS[this.dataset.row ?? ""] ?? [0, 600];
    return { top, bottom, left: 0, right: 300, width: 300, height: bottom - top, x: 0, y: top, toJSON: () => ({}) } as DOMRect;
  });
}

describe("the «Состав» pitch", () => {
  it("the grass and the markings even without a tactic", () => {
    layout();
    const { container } = render(<Pitch />);
    expect(container.querySelector("[data-pitch]")).not.toBeNull();
    expect(container.querySelector("[data-direction]")).toBeNull();
  });

  it("draws the tactic: lanes, the line with its label, pressing chevrons", () => {
    layout();
    const { container } = render(<Pitch tactic={{ direction: "wings", block: "high", buildup: "direct", on_loss: "counterpress" }} />);
    expect(container.querySelectorAll("[data-direction=wings] path")).toHaveLength(2);
    expect(container.querySelector("[data-line=high]")).not.toBeNull();
    expect(container.querySelector("[data-line-label]")).toHaveTextContent("высокий прессинг");
    expect(container.querySelector("[data-buildup=direct] circle")).not.toBeNull();
    expect(container.querySelector("[data-on-loss=counterpress]")).not.toBeNull();
  });
});
