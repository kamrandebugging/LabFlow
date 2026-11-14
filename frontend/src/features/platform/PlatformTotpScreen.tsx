import type { ReactElement } from "react";
import { useState, type FormEvent } from "react";
import { ArrowLeft } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { usePlatformAuthStore } from "./platformAuthStore";
import { ThemeToggle } from "../../components/ui/ThemeToggle";
import { VerifyCodeCard } from "../../components/ui/VerifyCodeCard";
import styles from "./PlatformTotpScreen.module.css";

export function PlatformTotpScreen(): ReactElement {
  const navigate = useNavigate();
  const verifyTotp = usePlatformAuthStore((state) => state.verifyTotp);
  const isLoading = usePlatformAuthStore((state) => state.isLoading);
  const [error, setError] = useState<string | null>(null);
  const [backupMode, setBackupMode] = useState(false);
  const [backupCode, setBackupCode] = useState("");

  const finish = (): void => {
    const enrolled = usePlatformAuthStore.getState().platformUser?.totp_enabled;
    navigate(enrolled ? "/platform/overview" : "/platform/enroll", {
      replace: true,
    });
  };

  // The card owns the success animation; it calls onSuccess when it is done.
  const handleSubmit = async (code: string): Promise<void> => {
    setError(null);
    const ok = await verifyTotp(code.trim());
    if (!ok) {
      setError(
        usePlatformAuthStore.getState().error ??
          "Sign-in failed. Check your email, password and authenticator code.",
      );
      throw new Error("invalid_code");
    }
  };

  const handleBackupSubmit = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    const code = backupCode.trim();
    if (!code) return;
    try {
      await handleSubmit(code);
      finish();
    } catch {
      setBackupCode("");
    }
  };

  return (
    <div className={styles.page}>
      <aside className={styles.topControls}>
        {backupMode ? <ThemeToggle /> : null}
      </aside>

      {backupMode ? (
        <main className={styles.backupCard}>
          <h1 className={styles.backupTitle}>Backup code</h1>
          <p className={styles.backupSubline}>
            A single-use backup code also works here.
          </p>
          <form
            onSubmit={(event) => void handleBackupSubmit(event)}
            className={styles.backupForm}
          >
            <label
              htmlFor="platform-backup-code"
              className={styles.backupLabel}
            >
              Backup code
            </label>
            <input
              id="platform-backup-code"
              type="text"
              value={backupCode}
              onChange={(event) => setBackupCode(event.target.value)}
              className={styles.backupInput}
              dir="ltr"
              autoComplete="one-time-code"
            />
            {error && (
              <p role="alert" className={styles.error}>
                {error}
              </p>
            )}
            <button
              type="submit"
              disabled={isLoading}
              className={styles.primary}
            >
              {isLoading ? "Verifying…" : "Verify"}
            </button>
          </form>
          <button
            type="button"
            className={styles.backLink}
            onClick={() => {
              setBackupMode(false);
              setError(null);
            }}
          >
            Use authenticator app
          </button>
        </main>
      ) : (
        <VerifyCodeCard
          mode="totp"
          error={error}
          verifying={isLoading}
          onSubmit={handleSubmit}
          onSuccess={finish}
          onSecondary={() => {
            setBackupMode(true);
            setError(null);
          }}
          secondaryLabel="Use backup code"
        />
      )}

      {!backupMode && (
        <Link to="/platform/login" className={styles.pageBack}>
          <ArrowLeft size={14} aria-hidden="true" />
          <span>Back to sign in</span>
        </Link>
      )}
    </div>
  );
}
