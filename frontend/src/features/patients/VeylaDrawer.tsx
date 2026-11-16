import React, { useCallback, useEffect, useRef, useState } from "react";
import type { ReactNode, RefObject } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useDialogFocus } from "../../lib/dialogFocus";
import { motionDurationMs, prefersReducedMotion } from "../../lib/motion";
import styles from "./PatientForm.module.css";

export interface VeylaDrawerProps {
  /** The drawer is mounted only while open; this drives the focus trap. */
  open: boolean;
  /** Called on Escape, the close button, or a backdrop click. */
  onClose: () => void;
  /** Heading of the drawer panel. */
  title: string;
  /** Optional supporting line under the heading. */
  subtitle?: string;
  /**
   * Replaces the default heading block. Use it when the header carries more
   * than a title (identity card, status chips, metadata).
   */
  header?: ReactNode;
  /**
   * The element that opened the drawer. Focus returns to it when the drawer
   * closes (WCAG 2.2 focus management).
   */
  triggerRef?: RefObject<HTMLElement>;
  /**
   * Suspends the focus trap while a nested modal (the duplicate-patient
   * dialog) owns the keyboard. Without this the drawer would trap Tab
   * before the nested dialog could.
   */
  suspendFocusTrap?: boolean;
  /** Panel width. The register form needs room; the record drawer is narrow. */
  width?: "wide" | "narrow";
  /** Form body. */
  children: ReactNode;
  /** Sticky footer actions. */
  footer?: ReactNode;
}

/**
 * Veyla side-panel drawer: a right-hand panel over the page behind it.
 *
 * This is the single drawer primitive in the tenant app. The register form
 * and the patient record drawer both use it, so there is exactly one panel,
 * one backdrop and one focus trap in the DOM at any time.
 *
 * The drawer must be mounted OUTSIDE any element that is transformed during
 * the page transition. A transformed ancestor turns `position: fixed`
 * descendants into viewport-relative boxes, which is what used to push the
 * panel off-screen and clip its backdrop while the page was cross-fading.
 *
 * Focus management is delegated to the shared `useDialogFocus` hook, which
 * traps Tab inside the panel, closes on Escape and restores focus to the
 * trigger on close.
 */
export const VeylaDrawer: React.FC<VeylaDrawerProps> = ({
  open,
  onClose,
  title,
  subtitle,
  header,
  triggerRef,
  suspendFocusTrap = false,
  width = "wide",
  children,
  footer,
}) => {
  const { t } = useTranslation(["common", "patients"]);
  const [isClosing, setIsClosing] = useState(false);
  const closingRef = useRef(false);
  const closeTimerRef = useRef<number | null>(null);

  // Closing plays the 200ms slide-out first; the parent unmounts the drawer
  // only after the animation finishes. Escape, the close button and the
  // backdrop all go through this one handler, so focus behaviour is unchanged.
  const requestClose = useCallback(() => {
    if (closingRef.current) return;

    if (prefersReducedMotion()) {
      onClose();
      return;
    }

    closingRef.current = true;
    setIsClosing(true);
    closeTimerRef.current = window.setTimeout(
      () => {
        closeTimerRef.current = null;
        onClose();
      },
      motionDurationMs("--motion-base", 200),
    );
  }, [onClose]);

  useEffect(
    () => () => {
      if (closeTimerRef.current !== null) {
        window.clearTimeout(closeTimerRef.current);
      }
    },
    [],
  );

  const panelRef = useDialogFocus<HTMLDivElement>(
    open && !suspendFocusTrap,
    requestClose,
    triggerRef,
  );
  const headingId = "veyla-drawer-title";

  if (!open) return null;

  return (
    <div
      className={`${styles.drawerScrim} veyla-drawer-scrim`}
      data-state={isClosing ? "closing" : "open"}
      onMouseDown={(event) => {
        // Only a click that starts on the backdrop itself closes the drawer;
        // a drag that ends outside the panel must not dismiss it.
        if (event.target === event.currentTarget) requestClose();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={header ? undefined : headingId}
        aria-label={header ? title : undefined}
        data-state={isClosing ? "closing" : "open"}
        data-width={width}
        className={`${styles.drawerPanel} veyla-drawer-panel`}
      >
        <header className={styles.drawerHeader}>
          {header ? (
            header
          ) : (
            <div className={styles.drawerHeading}>
              <h2 id={headingId} className={styles.drawerTitle}>
                {title}
              </h2>
              {subtitle ? (
                <span className={styles.drawerSubtitle}>{subtitle}</span>
              ) : null}
            </div>
          )}
          <button
            type="button"
            onClick={requestClose}
            className={styles.drawerClose}
            aria-label={t("common:actions.close")}
            title={t("common:actions.close")}
          >
            <X className={styles.drawerIcon} aria-hidden="true" />
          </button>
        </header>

        <div className={styles.drawerBody}>{children}</div>

        {footer ? (
          <footer className={styles.drawerFooter}>{footer}</footer>
        ) : null}
      </div>
    </div>
  );
};

export default VeylaDrawer;
