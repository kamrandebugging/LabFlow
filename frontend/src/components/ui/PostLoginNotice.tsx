import type { ReactElement, ReactNode } from "react";

import styles from "./PostLoginNotice.module.css";

export interface PostLoginNoticeProps {
  title: string;
  body?: ReactNode;
  /** Flat primary action ("Change Now" / "Enable Now"). */
  primaryLabel: string;
  onPrimary: () => void;
  /** Ghost dismiss ("Remind me later"). */
  onDismiss: () => void;
}

/**
 * The one post-login warning dialog. Both notices (temporary password, 2FA)
 * share this neumorphism modal: raised card, flat primary, ghost dismiss.
 */
export function PostLoginNotice({
  title,
  body,
  primaryLabel,
  onPrimary,
  onDismiss,
}: PostLoginNoticeProps): ReactElement {
  return (
    <div className={styles.overlay} role="presentation">
      <div
        role="alertdialog"
        aria-modal="true"
        aria-labelledby="post-login-notice-title"
        className={styles.card}
      >
        <h2 id="post-login-notice-title" className={styles.title}>
          {title}
        </h2>
        {body ? <div className={styles.body}>{body}</div> : null}
        <div className={styles.actions}>
          <button type="button" className={styles.ghost} onClick={onDismiss}>
            Remind me later
          </button>
          <button type="button" className={styles.primary} onClick={onPrimary}>
            {primaryLabel}
          </button>
        </div>
      </div>
    </div>
  );
}
