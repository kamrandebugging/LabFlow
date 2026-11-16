import React from "react";
import type { ReactNode, RefObject } from "react";
import { useTranslation } from "react-i18next";
import { X } from "lucide-react";
import { useDialogFocus } from "../../lib/dialogFocus";
import styles from "./PatientForm.module.css";

interface PatientRegisterDrawerProps {
  /** The drawer is mounted only while open; this drives the focus trap. */
  open: boolean;
  /** Called on Escape, the close button, or a backdrop click. */
  onClose: () => void;
  /** Heading of the drawer panel. */
  title: string;
  /** Optional supporting line under the heading. */
  subtitle?: string;
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
  /** Form body. */
  children: ReactNode;
  /** Sticky footer actions. */
  footer?: ReactNode;
}

/**
 * Veyla side-panel drawer: a right-hand panel over the patient list.
 *
 * The list underneath keeps its scroll position, search query and filters
 * while a patient is being registered, which is what the reception desk
 * needs when registering a queue of patients.
 *
 * Focus management is delegated to the shared `useDialogFocus` hook, which
 * traps Tab inside the panel, closes on Escape and restores focus to the
 * trigger on close.
 */
export const PatientRegisterDrawer: React.FC<PatientRegisterDrawerProps> = ({
  open,
  onClose,
  title,
  subtitle,
  triggerRef,
  suspendFocusTrap = false,
  children,
  footer,
}) => {
  const { t } = useTranslation(["common", "patients"]);
  const panelRef = useDialogFocus<HTMLDivElement>(
    open && !suspendFocusTrap,
    onClose,
    triggerRef,
  );
  const headingId = "patient-register-drawer-title";

  if (!open) return null;

  return (
    <div
      className={styles.drawerScrim}
      onMouseDown={(event) => {
        // Only a click that starts on the backdrop itself closes the drawer;
        // a drag that ends outside the panel must not dismiss it.
        if (event.target === event.currentTarget) onClose();
      }}
    >
      <div
        ref={panelRef}
        tabIndex={-1}
        role="dialog"
        aria-modal="true"
        aria-labelledby={headingId}
        className={styles.drawerPanel}
      >
        <header className={styles.drawerHeader}>
          <div className={styles.drawerHeading}>
            <h2 id={headingId} className={styles.drawerTitle}>
              {title}
            </h2>
            {subtitle ? (
              <span className={styles.drawerSubtitle}>{subtitle}</span>
            ) : null}
          </div>
          <button
            type="button"
            onClick={onClose}
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

export default PatientRegisterDrawer;
