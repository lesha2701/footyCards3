import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { EnergyBar, EnergyBattery } from "@/components/career/EnergyBar";
import { FormTriangle } from "@/components/career/PlayerTile";
import { ChemistryFlask } from "@/components/squad/Chemistry";
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

describe("pitch card numbers", () => {
  it("shows the energy percentage inside the battery", () => {
    render(<EnergyBattery fatigue={35} />);
    expect(screen.getByRole("img", { name: /Энергия 65%/ })).toHaveTextContent("65%");
  });

  it("shows form as a triangle with its number, nothing at zero", () => {
    const { container, rerender } = render(<FormTriangle form={2} />);
    expect(screen.getByRole("img", { name: "Форма +2" })).toHaveTextContent("2");
    rerender(<FormTriangle form={-1} />);
    expect(screen.getByRole("img", { name: "Форма -1" })).toHaveTextContent("1");
    rerender(<FormTriangle form={0} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("shows chemistry inside the flask, without a plus at zero", () => {
    const { rerender } = render(<ChemistryFlask points={3} max={3} onPosition />);
    expect(screen.getByRole("img", { name: "Химия 3 из 3" })).toHaveTextContent("+3");
    rerender(<ChemistryFlask points={0} max={3} onPosition={false} />);
    expect(screen.getByRole("img", { name: "Химия 0 из 3" })).not.toHaveTextContent("+");
  });
});
