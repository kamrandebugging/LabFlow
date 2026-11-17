/**
 * Shared motion helpers.
 *
 * One implementation is used by every Veyla theme trigger. The top-bar
 * button is the current Veyla caller; any account-menu or Settings →
 * Appearance control added later must call `revealThemeChange` too.
 * Component CSS never hard-codes a duration or curve; the JS side reads the
 * same tokens from tokens.css.
 */
import { flushSync } from "react-dom";

export const REDUCED_MOTION_QUERY = "(prefers-reduced-motion: reduce)";

type ViewTransitionLike = { ready: Promise<void> };

type ViewTransitionCapableDocument = {
  startViewTransition?: (callback: () => void) => ViewTransitionLike;
};

/** True when the user asked the OS to remove non-essential motion. */
export function prefersReducedMotion(): boolean {
  if (typeof window === "undefined" || typeof window.matchMedia !== "function")
    return false;
  return window.matchMedia(REDUCED_MOTION_QUERY).matches;
}

/** Reads a duration token (ms or s) from :root, with a safe fallback. */
export function motionDurationMs(token: string, fallback: number): number {
  if (typeof window === "undefined") return fallback;
  const raw = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue(token)
    .trim();
  const match = /^([\d.]+)(ms|s)$/.exec(raw);
  if (!match) return fallback;
  const value = Number.parseFloat(match[1] ?? "");
  if (!Number.isFinite(value)) return fallback;
  return match[2] === "s" ? value * 1000 : value;
}

/** Reads an easing token from :root, with a safe fallback. */
export function motionEasing(token: string, fallback: string): string {
  if (typeof window === "undefined") return fallback;
  const raw = window
    .getComputedStyle(document.documentElement)
    .getPropertyValue(token)
    .trim();
  return raw || fallback;
}

export interface RevealOrigin {
  clientX: number;
  clientY: number;
}

/**
 * Applies a theme change through a circular-reveal View Transition that
 * expands from the exact click coordinates to the farthest viewport corner.
 *
 * Falls back to an instant swap when the View Transitions API is missing or
 * the user prefers reduced motion. The page never ends up half-themed.
 */
export function revealThemeChange(
  origin: RevealOrigin,
  applyChange: () => void,
): void {
  if (typeof document === "undefined") {
    applyChange();
    return;
  }

  const doc = document as unknown as ViewTransitionCapableDocument;
  const root = document.documentElement;

  if (prefersReducedMotion() || typeof doc.startViewTransition !== "function") {
    applyChange();
    return;
  }

  const x = origin.clientX;
  const y = origin.clientY;
  const endRadius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y),
  );

  // flushSync makes the new theme part of the same snapshot the transition
  // captures; without it React would commit after the capture.
  const transition = doc.startViewTransition(() => {
    flushSync(applyChange);
  });

  void transition.ready
    .then(() => {
      if (typeof root.animate !== "function") return;
      root.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${endRadius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: motionDurationMs("--motion-theme", 500),
          easing: motionEasing(
            "--ease-in-out",
            "cubic-bezier(0.65, 0, 0.35, 1)",
          ),
          pseudoElement: "::view-transition-new(root)",
        },
      );
    })
    .catch(() => {
      // A cancelled transition already leaves the DOM on the new theme.
    });
}
