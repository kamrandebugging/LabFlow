import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { afterEach, describe, expect, it, vi } from "vitest";

import {
  REDUCED_MOTION_QUERY,
  motionDurationMs,
  prefersReducedMotion,
  revealThemeChange,
} from "../../lib/motion";

const read = (relative: string): string =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

type ViewTransitionCapable = {
  startViewTransition?: (callback: () => void) => { ready: Promise<void> };
};

const originalMatchMedia = window.matchMedia;
const originalStartViewTransition = (
  document as unknown as ViewTransitionCapable
).startViewTransition;
const originalAnimate = document.documentElement.animate;

function mockMatchMedia(matches: boolean): void {
  window.matchMedia = vi.fn().mockImplementation((query: string) => ({
    matches: query === REDUCED_MOTION_QUERY ? matches : false,
    media: query,
    onchange: null,
    addListener: vi.fn(),
    removeListener: vi.fn(),
    addEventListener: vi.fn(),
    removeEventListener: vi.fn(),
    dispatchEvent: vi.fn(),
  })) as unknown as typeof window.matchMedia;
}

afterEach(() => {
  window.matchMedia = originalMatchMedia;
  (document as unknown as ViewTransitionCapable).startViewTransition =
    originalStartViewTransition;
  Object.defineProperty(document.documentElement, "animate", {
    configurable: true,
    value: originalAnimate,
  });
  vi.restoreAllMocks();
});

describe("Veyla motion system", () => {
  it("uses the approved duration and easing tokens", () => {
    const tokens = read("../../theme/tokens.css");
    expect(tokens).toContain("--motion-fast: 150ms;");
    expect(tokens).toContain("--motion-base: 200ms;");
    expect(tokens).toContain("--motion-drawer: 280ms;");
    expect(tokens).toContain("--motion-theme: 500ms;");
    expect(tokens).toContain("--ease-out: cubic-bezier(0.22, 1, 0.36, 1);");
    expect(tokens).toContain("--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);");
  });

  it("keeps drawer and modal keyframes in one global place", () => {
    const indexCss = read("../../index.css");
    const patientFormCss = read(
      "../../features/patients/PatientForm.module.css",
    );

    expect(indexCss).toContain(".veyla-drawer-panel");
    expect(indexCss).toContain(".veyla-modal");
    expect(indexCss).toContain("@media (prefers-reduced-motion: reduce)");
    expect(indexCss).toContain("animation: none !important;");
    expect(indexCss).toContain("transition: none !important;");

    expect(patientFormCss).not.toContain("@keyframes drawerSlide");
    expect(patientFormCss).not.toContain("@keyframes drawerFade");
  });

  it("reads a duration token and falls back safely", () => {
    expect(motionDurationMs("--motion-fast", 150)).toBe(150);
    expect(motionDurationMs("--not-a-token", 200)).toBe(200);
  });

  it("applies the theme instantly when View Transitions are unavailable", () => {
    mockMatchMedia(false);
    (document as unknown as ViewTransitionCapable).startViewTransition =
      undefined;
    const apply = vi.fn();

    revealThemeChange({ clientX: 10, clientY: 20 }, apply);

    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("applies the theme instantly under prefers-reduced-motion", () => {
    const start = vi.fn(() => ({ ready: Promise.resolve() }));
    (document as unknown as ViewTransitionCapable).startViewTransition = start;
    mockMatchMedia(true);
    const apply = vi.fn();

    revealThemeChange({ clientX: 10, clientY: 20 }, apply);

    expect(prefersReducedMotion()).toBe(true);
    expect(start).not.toHaveBeenCalled();
    expect(apply).toHaveBeenCalledTimes(1);
  });

  it("reveals from the click point with the 500ms ease-in-out token", async () => {
    let resolveReady: () => void = () => undefined;
    const ready = new Promise<void>((resolve) => {
      resolveReady = resolve;
    });
    const start = vi.fn((callback: () => void) => {
      callback();
      return { ready };
    });
    (document as unknown as ViewTransitionCapable).startViewTransition = start;

    const animate = vi.fn();
    Object.defineProperty(document.documentElement, "animate", {
      configurable: true,
      value: animate,
    });
    mockMatchMedia(false);
    const apply = vi.fn();

    revealThemeChange({ clientX: 12, clientY: 34 }, apply);

    expect(start).toHaveBeenCalledTimes(1);
    expect(apply).toHaveBeenCalledTimes(1);

    resolveReady();
    await Promise.resolve();
    await Promise.resolve();

    expect(animate).toHaveBeenCalledTimes(1);
    const [keyframes, options] = animate.mock.calls[0] as [
      { clipPath: string[] },
      {
        duration: number;
        easing: string;
        pseudoElement: string;
      },
    ];
    expect(keyframes.clipPath[0]).toBe("circle(0px at 12px 34px)");
    expect(keyframes.clipPath[1]).toMatch(/^circle\([\d.]+px at 12px 34px\)$/);
    expect(options.duration).toBe(500);
    expect(options.easing).toBe("cubic-bezier(0.65, 0, 0.35, 1)");
    expect(options.pseudoElement).toBe("::view-transition-new(root)");
  });
});
