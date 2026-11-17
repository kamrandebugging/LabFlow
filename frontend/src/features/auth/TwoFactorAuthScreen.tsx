import { useRef, useState, type FormEvent } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft } from "lucide-react";
import type {
  AuthService,
  LoginSuccessSession,
  TotpVerifyPayload,
} from "./types";
import { defaultAuthService } from "./authService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { ThemeToggle } from "../../components/ui/ThemeToggle";
import { VerifyCodeCard } from "../../components/ui/VerifyCodeCard";
import styles from "./TwoFactorAuthScreen.module.css";

export interface TwoFactorAuthScreenProps {
  email?: string;
  challengeToken?: string;
  tenantName?: string;
  terminalId?: string;
  authService?: AuthService;
  onSuccess?: (session: LoginSuccessSession) => void;
  onBack?: () => void;
}

export function TwoFactorAuthScreen({
  email,
  challengeToken,
  authService = defaultAuthService,
  onSuccess,
  onBack,
}: TwoFactorAuthScreenProps): JSX.Element {
  const { t } = useTranslation(["auth", "common"]);
  const [verifying, setVerifying] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [backupMode, setBackupMode] = useState(false);
  const [backupCode, setBackupCode] = useState("");
  const sessionRef = useRef<LoginSuccessSession | null>(null);

  const verify = async (
    code: string,
    isBackupCode: boolean,
  ): Promise<LoginSuccessSession> => {
    const payload: TotpVerifyPayload = { code, isBackupCode };
    if (challengeToken) {
      payload.challengeToken = challengeToken;
    }
    return authService.verifyTotp(payload);
  };

  // The card owns the success animation; it calls onSuccess once it is done.
  const handleCardSubmit = async (code: string): Promise<void> => {
    setVerifying(true);
    setError(null);
    try {
      sessionRef.current = await verify(code, false);
    } catch {
      setError(t("auth:errors.generic"));
      throw new Error("401 invalid_code");
    } finally {
      setVerifying(false);
    }
  };

  const handleCardSuccess = (): void => {
    const session = sessionRef.current;
    if (session) onSuccess?.(session);
  };

  const handleBackupSubmit = async (
    event: FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    event.preventDefault();
    const code = backupCode.trim();
    if (!code) return;
    setVerifying(true);
    setError(null);
    try {
      const session = await verify(code, true);
      onSuccess?.(session);
    } catch {
      setError(t("auth:errors.generic"));
      setBackupCode("");
    } finally {
      setVerifying(false);
    }
  };

  return (
    <div className={styles.page}>
      <aside className={styles.topControls}>
        <div className={styles.langWrap}>
          <LanguageSwitcher compact />
        </div>
        {backupMode ? <ThemeToggle /> : null}
      </aside>

      {backupMode ? (
        <main className={styles.backupCard}>
          <h1 className={styles.backupTitle}>{t("auth:totp.backup_code")}</h1>
          <p className={styles.backupSubline}>
            {t("auth:totp.backup_placeholder")}
          </p>
          <form
            onSubmit={(event) => void handleBackupSubmit(event)}
            className={styles.backupForm}
          >
            <label htmlFor="backup-code" className={styles.backupLabel}>
              {t("auth:totp.backup_code")}
            </label>
            <input
              id="backup-code"
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
              disabled={verifying}
              className={styles.primary}
            >
              {t("auth:totp.verify")}
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
            {t("auth:totp.use_authenticator")}
          </button>
        </main>
      ) : (
        <VerifyCodeCard
          mode="totp"
          maskedContact={email}
          error={error}
          verifying={verifying}
          onSubmit={handleCardSubmit}
          onSuccess={handleCardSuccess}
          onSecondary={() => {
            setBackupMode(true);
            setError(null);
          }}
          secondaryLabel={t("auth:totp.use_backup")}
        />
      )}

      {!backupMode && (
        <button type="button" className={styles.pageBack} onClick={onBack}>
          <ArrowLeft size={14} aria-hidden="true" />
          <span>{t("auth:totp.back_to_sign_in")}</span>
        </button>
      )}
    </div>
  );
}
