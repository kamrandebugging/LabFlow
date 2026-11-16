/**
 * Veyla page transition for the tenant shell.
 *
 * Every route change inside the tenant app plays the same motion: the page
 * that is leaving fades out and lifts 4px (150ms), the page that is arriving
 * fades in and settles from 8px (280ms). Both are briefly on screen, which is
 * what the Veyla reference does. The sidebar and the top bar live outside
 * this component, so they never animate and never re-mount.
 *
 * Implementation notes:
 * - The router location keys the transition: every pathname change replays
 *   it, a re-click on the same path does nothing.
 * - The leaving page stays mounted until its exit animation ends. React keeps
 *   that instance alive because the layer keeps its key, so no screen is ever
 *   mounted twice and no request is ever sent twice.
 * - Redirect routes (<Navigate />) resolve themselves, so the current page
 *   stays on screen until the real destination arrives.
 */
import { useEffect, useLayoutEffect, useRef, useState } from "react";
import type { ReactNode } from "react";
import { isValidElement } from "react";
import { Navigate, useLocation, useOutlet } from "react-router-dom";

import { motionDurationMs, prefersReducedMotion } from "../../lib/motion";

type LayerState = "enter" | "idle" | "exit";

interface PageLayer {
  id: number;
  pathname: string;
  element: ReactNode;
  state: LayerState;
}

function isRedirectRoute(element: ReactNode): boolean {
  return isValidElement(element) && element.type === Navigate;
}

export function PageTransition(): JSX.Element {
  const location = useLocation();
  const outlet = useOutlet();
  const nextId = useRef(1);
  const livePath = useRef(location.pathname);
  const timers = useRef<number[]>([]);

  const [layers, setLayers] = useState<PageLayer[]>(() => [
    { id: 0, pathname: location.pathname, element: outlet, state: "idle" },
  ]);

  useLayoutEffect(() => {
    if (livePath.current === location.pathname) return;
    livePath.current = location.pathname;

    const incoming: PageLayer = {
      id: nextId.current++,
      pathname: location.pathname,
      element: outlet,
      state: "enter",
    };

    // A redirect route resolves itself; the current page stays on screen
    // until the destination route is known.
    if (isRedirectRoute(outlet)) {
      setLayers((prev): PageLayer[] => [
        { ...incoming, state: "idle" },
        ...prev.map((layer): PageLayer =>
          layer.state === "exit" ? layer : { ...layer, state: "idle" },
        ),
      ]);
      return;
    }

    // Reduced motion: the switch is instant. No fade, no slide.
    if (prefersReducedMotion()) {
      setLayers([{ ...incoming, state: "idle" }]);
      window.scrollTo(0, 0);
      return;
    }

    setLayers((prev): PageLayer[] => [
      incoming,
      ...prev.map((layer): PageLayer =>
        layer.state === "exit" ? layer : { ...layer, state: "exit" },
      ),
    ]);

    // The arriving page starts at the top of the content area.
    window.scrollTo(0, 0);

    const exitTimer = window.setTimeout(
      () => {
        setLayers((prev): PageLayer[] =>
          prev.filter((layer) => layer.state !== "exit"),
        );
      },
      motionDurationMs("--motion-fast", 150),
    );

    const enterTimer = window.setTimeout(
      () => {
        setLayers((prev): PageLayer[] =>
          prev.map((layer): PageLayer =>
            layer.state === "enter" ? { ...layer, state: "idle" } : layer,
          ),
        );
      },
      motionDurationMs("--motion-drawer", 280),
    );

    timers.current.push(exitTimer, enterTimer);
  }, [location.pathname, outlet]);

  useEffect(
    () => () => {
      timers.current.forEach((timer) => window.clearTimeout(timer));
    },
    [],
  );

  return (
    <div className="lf-page-stack">
      {layers.map((layer) => (
        <div
          key={layer.id}
          data-page-state={layer.state}
          className={`lf-page-layer lf-page-layer--${layer.state}`}
        >
          {layer.element}
        </div>
      ))}
    </div>
  );
}

export default PageTransition;
