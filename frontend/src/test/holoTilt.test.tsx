import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import HoloTilt, { HOLO_OPACITY } from "@/components/cards/HoloTilt";

describe("HoloTilt", () => {
  it("gives rarer cards a brighter foil, none to a common one", () => {
    expect(HOLO_OPACITY.common).toBe(0);
    expect(HOLO_OPACITY.rare).toBeLessThan(HOLO_OPACITY.epic);
    expect(HOLO_OPACITY.epic).toBeLessThan(HOLO_OPACITY.legendary);
    expect(HOLO_OPACITY.legendary).toBeLessThan(HOLO_OPACITY.diamond);
  });

  it("adds the foil to a rare card and only the tilt to a common one", () => {
    const { unmount } = render(<HoloTilt rarity="legendary"><p>card</p></HoloTilt>);
    expect(screen.getByTestId("holo-tilt")).toBeInTheDocument();
    expect(screen.getByTestId("holo-foil")).toBeInTheDocument();
    unmount();
    render(<HoloTilt rarity="common"><p>card</p></HoloTilt>);
    expect(screen.getByTestId("holo-tilt")).toBeInTheDocument();
    expect(screen.queryByTestId("holo-foil")).toBeNull();
  });

  it("keeps the card but adds nothing while off (before it turns over)", () => {
    render(<HoloTilt rarity="diamond" enabled={false}><p>card</p></HoloTilt>);
    expect(screen.getByText("card")).toBeInTheDocument();
    expect(screen.queryByTestId("holo-tilt")).toBeNull();
    expect(screen.queryByTestId("holo-foil")).toBeNull();
  });
});
