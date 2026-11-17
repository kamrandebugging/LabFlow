import { useEffect, useRef } from "react";
import type { RefObject } from "react";

const FOCUSABLE_SELECTOR = [
  "a[href]",
  "button:not([disabled])",
  "input:not([disabled])",
  "select:not([disabled])",
  "textarea:not([disabled])",
  '[tabindex]:not([tabindex="-1"])',
].join(",");

function focusable(panel: HTMLElement | null): HTMLElement[] {
  if (!panel) return [];
  return Array.from(
    panel.querySelectorAll<HTMLElement>(FOCUSABLE_SELECTOR),
  ).filter((element) => !element.hasAttribute("disabled"));
}

/**
 * WCAG 2.2 focus management for a modal dialog: the panel takes focus when it
 * opens, Tab / Shift+Tab cycle inside it, Escape closes it, and focus returns
 * to whatever triggered it. The caller owns the open state and renders the
 * `role="dialog"` panel with the returned ref.
 */
export function useDialogFocus<T extends HTMLElement = HTMLDivElement>(
  open: boolean,
  onClose: () => void,
  returnFocusRef?: RefObject<HTMLElement>,
) {
  const panelRef = useRef<T>(null);
  const triggerRef = useRef<HTMLElement | null>(null);
  // Kept in a ref so an inline arrow handler does not re-run the effect (which
  // would steal focus back to the panel on every parent render).
  const onCloseRef = useRef(onClose);
  onCloseRef.current = onClose;

  useEffect(() => {
    if (!open) return;

    const active = document.activeElement;
    triggerRef.current = returnFocusRef?.current
      ? returnFocusRef.current
      : active instanceof HTMLElement && active !== document.body
        ? active
        : null;

    const panel = panelRef.current;
    const first = focusable(panel)[0];
    (first ?? panel)?.focus();

    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        event.stopPropagation();
        onCloseRef.current();
        return;
      }
      if (event.key !== "Tab") return;

      const items = focusable(panelRef.current);
      if (items.length === 0) return;
      const firstItem = items[0] as HTMLElement;
      const lastItem = items[items.length - 1] as HTMLElement;
      const current = document.activeElement;

      if (event.shiftKey && (current === firstItem || current === panel)) {
        event.preventDefault();
        lastItem.focus();
      } else if (!event.shiftKey && current === lastItem) {
        event.preventDefault();
        firstItem.focus();
      }
    };

    document.addEventListener("keydown", onKeyDown, true);
    return () => {
      document.removeEventListener("keydown", onKeyDown, true);
      triggerRef.current?.focus();
      triggerRef.current = null;
    };
  }, [open, returnFocusRef]);

  return panelRef;
}
