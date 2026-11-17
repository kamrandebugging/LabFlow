import { useEffect, useMemo, useState } from "react";
import type { ReactElement } from "react";

import styles from "./ForgotPasswordModal.module.css";

export interface ForgotPasswordModalProps {
  tenantName?: string;
  slug: string;
  /** Email typed on the login form (never hardcoded). */
  email: string;
  onClose: () => void;
}

const SUPPORT_NAME = "Muhammad Kamran — Platform Owner";
const SUPPORT_EMAIL = "kamrandebugging@gmail.com";
const SUPPORT_WHATSAPP_DISPLAY = "+92 320 6744652";
const SUPPORT_WHATSAPP_NUMBER = "923206744652";

/**
 * Forgot-password chooser. Display-only: no lookup endpoint, no email is sent,
 * and the card never reveals whether an account exists.
 */
export function ForgotPasswordModal({
  tenantName,
  slug,
  email,
  onClose,
}: ForgotPasswordModalProps): ReactElement {
  const [view, setView] = useState<"chooser" | "owner" | "staff">("chooser");
  const [copied, setCopied] = useState(false);
  const [requestEmail, setRequestEmail] = useState(email);
  const [requestName, setRequestName] = useState("");
  const [requestSent, setRequestSent] = useState(false);

  const sendRequest = async (): Promise<void> => {
    try {
      await fetch("/api/v1/auth/password-reset/staff-request", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          email: requestEmail.trim(),
          display_name: requestName.trim(),
        }),
      });
    } catch {
      // Non-enumerating by design: the confirmation is identical either way.
    }
    setRequestSent(true);
  };

  useEffect(() => {
    const onKey = (event: KeyboardEvent): void => {
      if (event.key === "Escape") onClose();
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [onClose]);

  const labName = tenantName?.trim() || "—";
  const loginEmail = email.trim() || "—";

  const whatsappHref = useMemo(() => {
    const message = [
      "LabFlow owner password reset request",
      `Lab name: ${labName}`,
      `Lab code (subdomain): ${slug}`,
      `Owner login email: ${loginEmail}`,
    ].join("\n");
    return `https://wa.me/${SUPPORT_WHATSAPP_NUMBER}?text=${encodeURIComponent(message)}`;
  }, [labName, loginEmail, slug]);

  const copyEmail = async (): Promise<void> => {
    try {
      await navigator.clipboard.writeText(SUPPORT_EMAIL);
      setCopied(true);
      window.setTimeout(() => setCopied(false), 1600);
    } catch {
      setCopied(false);
    }
  };

  return (
    <div className={styles.overlay} role="presentation">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="forgot-password-title"
        className={styles.card}
      >
        <header className={styles.header}>
          <h2 id="forgot-password-title" className={styles.title}>
            Forgot password?
          </h2>
          <button
            type="button"
            className={styles.close}
            onClick={onClose}
            aria-label="Close"
          >
            ✕
          </button>
        </header>

        {view === "chooser" && (
          <>
            <p className={styles.body}>Who is resetting their password?</p>
            <div className={styles.choices}>
              <button
                type="button"
                className={styles.primary}
                onClick={() => setView("owner")}
              >
                I&#39;m the Lab Owner
              </button>
              <button
                type="button"
                className={styles.ghost}
                onClick={() => setView("staff")}
              >
                I&#39;m Staff
              </button>
            </div>
          </>
        )}

        {view === "owner" && (
          <>
            <h3 className={styles.subtitle}>Contact LabFlow Support</h3>
            <p className={styles.supportName}>{SUPPORT_NAME}</p>

            <div className={styles.contactRow}>
              <div>
                <p className={styles.label}>Email</p>
                <p className={styles.value}>{SUPPORT_EMAIL}</p>
              </div>
              <button
                type="button"
                className={styles.ghostSmall}
                onClick={() => void copyEmail()}
              >
                {copied ? "Copied" : "Copy"}
              </button>
            </div>

            <div className={styles.contactRow}>
              <div>
                <p className={styles.label}>WhatsApp</p>
                <p className={styles.value}>{SUPPORT_WHATSAPP_DISPLAY}</p>
              </div>
              <a
                className={styles.primarySmall}
                href={whatsappHref}
                target="_blank"
                rel="noreferrer noopener"
              >
                Chat
              </a>
            </div>

            <p className={styles.hint}>
              Please send: lab name, lab code, owner email.
            </p>
            <p className={styles.dynamic}>
              Lab: {labName} · Code: {slug} · Email: {loginEmail}
            </p>
            <button
              type="button"
              className={styles.back}
              onClick={() => setView("chooser")}
            >
              Back
            </button>
          </>
        )}

        {view === "staff" && (
          <>
            {requestSent ? (
              <p className={styles.success} role="status">
                Request sent to your Lab Owner. They will issue a temporary
                password from their dashboard.
              </p>
            ) : (
              <form
                className={styles.requestForm}
                onSubmit={(event) => {
                  event.preventDefault();
                  void sendRequest();
                }}
              >
                <p className={styles.body}>
                  Send a reset request to your Lab Owner / Lab Admin. Tell them
                  your name and login email — only they can reset your password.
                </p>
                <label className={styles.label} htmlFor="forgot-email">
                  Login email
                </label>
                <input
                  id="forgot-email"
                  type="email"
                  required
                  value={requestEmail}
                  onChange={(event) => setRequestEmail(event.target.value)}
                  className={styles.input}
                  dir="ltr"
                />
                <label className={styles.label} htmlFor="forgot-name">
                  Your name (optional)
                </label>
                <input
                  id="forgot-name"
                  type="text"
                  value={requestName}
                  onChange={(event) => setRequestName(event.target.value)}
                  className={styles.input}
                />
                <button type="submit" className={styles.primary}>
                  Send request to Lab Owner
                </button>
              </form>
            )}
            <button
              type="button"
              className={styles.back}
              onClick={() => setView("chooser")}
            >
              Back
            </button>
          </>
        )}
      </div>
    </div>
  );
}
