import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnergyBar } from "@/components/career/EnergyBar";
import { energyLevel, energyOf } from "@/lib/careerEnergy";

describe("player energy", () => {
  it("is 100 − fatigue, clamped", () => {
    expect([energyOf(0), energyOf(28), energyOf(100), energyOf(130), energyOf(-5)]).toEqual([100, 72, 0, 0, 100]);
  });

  it("fresh, a bit tired, spent", () => {
    expect([energyLevel(100), energyLevel(60), energyLevel(59), energyLevel(30), energyLevel(29)])
      .toEqual(["fresh", "fresh", "tired", "tired", "spent"]);
  });

  it("the bar's length and colour say the same: full green when fresh, short red when spent", () => {
    const { container, rerender } = render(<EnergyBar fatigue={10} />);
    expect(screen.getByLabelText("Энергия 90% — свежий")).toHaveTextContent("90%");
    expect(container.querySelector(".bg-accent-lime")).toHaveStyle({ width: "90%" });
    rerender(<EnergyBar fatigue={80} />);
    expect(screen.getByLabelText("Энергия 20% — сильно устал")).toBeInTheDocument();
    expect(container.querySelector(".bg-red-400")).toHaveStyle({ width: "20%" });
    rerender(<EnergyBar fatigue={50} thin />);
    expect(screen.getByLabelText("Энергия 50% — немного устал")).toBeInTheDocument();
  });
});
