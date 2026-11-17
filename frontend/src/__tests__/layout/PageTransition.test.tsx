import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen, act } from "@testing-library/react";
import { MemoryRouter, Route, Routes, useNavigate } from "react-router-dom";

import { PageTransition } from "@/features/layout/PageTransition";

function GoToPatients(): JSX.Element {
  const navigate = useNavigate();
  return (
    <button type="button" onClick={() => void navigate("/patients")}>
      go to patients
    </button>
  );
}

function renderShell(): HTMLElement {
  const { container } = render(
    <MemoryRouter initialEntries={["/"]}>
      <Routes>
        <Route element={<PageTransition />}>
          <Route
            path="/"
            element={
              <div>
                <div>Home screen</div>
                <GoToPatients />
              </div>
            }
          />
          <Route path="/patients" element={<div>Patients screen</div>} />
        </Route>
      </Routes>
    </MemoryRouter>,
  );
  return container;
}

function layerStates(container: HTMLElement): Array<string | null> {
  return Array.from(container.querySelectorAll("[data-page-state]")).map(
    (node) => node.getAttribute("data-page-state"),
  );
}

describe("Page transition (Veyla)", () => {
  beforeEach(() => {
    vi.useFakeTimers();
    // jsdom has no layout engine; the scroll reset is a no-op there.
    vi.spyOn(window, "scrollTo").mockImplementation(() => undefined);
  });

  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  it("renders the current route without an animation on the first paint", () => {
    const { container } = render(
      <MemoryRouter initialEntries={["/"]}>
        <Routes>
          <Route element={<PageTransition />}>
            <Route path="/" element={<div>Home screen</div>} />
          </Route>
        </Routes>
      </MemoryRouter>,
    );

    expect(screen.getByText("Home screen")).toBeInTheDocument();
    expect(layerStates(container)).toEqual(["idle"]);
  });

  it("keeps the leaving page mounted while the arriving page enters", async () => {
    const container = renderShell();

    await act(async () => {
      screen.getByRole("button", { name: /go to patients/i }).click();
    });

    // Both pages are on screen mid-transition: the old one leaves, the new
    // one enters.
    expect(screen.getByText("Home screen")).toBeInTheDocument();
    expect(screen.getByText("Patients screen")).toBeInTheDocument();
    expect(layerStates(container)).toContain("exit");
    expect(layerStates(container)).toContain("enter");
  });

  it("removes the leaving page after the exit animation ends", async () => {
    const container = renderShell();

    await act(async () => {
      screen.getByRole("button", { name: /go to patients/i }).click();
    });
    await act(async () => {
      vi.advanceTimersByTime(200);
    });

    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
    expect(screen.getByText("Patients screen")).toBeInTheDocument();
    expect(layerStates(container)).not.toContain("exit");
  });

  it("swaps instantly when the user prefers reduced motion", async () => {
    vi.stubGlobal(
      "matchMedia",
      vi.fn().mockImplementation((query: string) => ({
        matches: query === "(prefers-reduced-motion: reduce)",
        media: query,
        onchange: null,
        addListener: vi.fn(),
        removeListener: vi.fn(),
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    );

    const container = renderShell();

    await act(async () => {
      screen.getByRole("button", { name: /go to patients/i }).click();
    });

    expect(screen.queryByText("Home screen")).not.toBeInTheDocument();
    expect(screen.getByText("Patients screen")).toBeInTheDocument();
    expect(layerStates(container)).toEqual(["idle"]);
  });
});
