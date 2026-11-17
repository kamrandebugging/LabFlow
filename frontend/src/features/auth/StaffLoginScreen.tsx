import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Loader2,
  ArrowRight,
  Eye,
  EyeOff,
  ShieldCheck,
  AlertCircle,
} from "lucide-react";
import type { AuthService, AuthUser, LoginSuccessSession } from "./types";
import { defaultAuthService } from "./authService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { ThemeToggle } from "../../components/ui/ThemeToggle";
import { ForgotPasswordModal } from "./ForgotPasswordModal";
import styles from "./StaffLoginScreen.module.css";

export interface StaffLoginScreenProps {
  tenantName?: string;
  nodeId?: string;
  authService?: AuthService;
  onSuccess?: (session: LoginSuccessSession) => void;
  onTotpRequired?: (email: string, challengeToken?: string) => void;
  /** An already-restored session must be surfaced, never silently resumed. */
  currentUser?: AuthUser | null;
  onContinue?: () => void;
  onLogInAsSomeoneElse?: () => void | Promise<void>;
}

export function StaffLoginScreen({
  tenantName,
  nodeId,
  authService = defaultAuthService,
  onSuccess,
  onTotpRequired,
  currentUser,
  onContinue,
  onLogInAsSomeoneElse,
}: StaffLoginScreenProps): JSX.Element {
  const { t } = useTranslation(["auth", "common"]);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showResetNotice, setShowResetNotice] = useState(false);
  const [forgotOpen, setForgotOpen] = useState(false);
  const [sessionExpiredNotice, setSessionExpiredNotice] = useState<boolean>(
    () => {
      if (typeof window === "undefined") return false;
      const params = new URLSearchParams(window.location.search);
      return params.get("reason") === "session_expired";
    },
  );

  const activeName =
    currentUser?.name ||
    currentUser?.display_name ||
    currentUser?.email ||
    currentUser?.id;

  useEffect(() => {
    if (sessionExpiredNotice && typeof window !== "undefined") {
      const url = new URL(window.location.href);
      url.searchParams.delete("reason");
      window.history.replaceState(
        {},
        document.title,
        url.pathname + (url.search ? url.search : ""),
      );
    }
  }, [sessionExpiredNotice]);

  const handleSubmit = async (
    e: React.FormEvent<HTMLFormElement>,
  ): Promise<void> => {
    e.preventDefault();
    if (!email || !password) {
      return;
    }

    setIsLoading(true);
    setError(null);

    try {
      const result = await authService.login({ email, password });
      if (result.totpRequired) {
        if (result.challengeToken) {
          onTotpRequired?.(email, result.challengeToken);
        } else {
          onTotpRequired?.(email);
        }
        return;
      }

      if (result.session) {
        // D2: TOTP is optional. A missing enrolment never blocks login.
        onSuccess?.(result.session);
        return;
      }
    } catch {
      setError(t("auth:errors.generic"));
    } finally {
      setIsLoading(false);
    }
  };

  return (
    <div className={styles.page}>
      <aside className={styles.topControls}>
        <div className={styles.langWrap}>
          <LanguageSwitcher />
        </div>
        <ThemeToggle />
      </aside>

      <main className={styles.card}>
        {/* Brand Header */}
        <header className={styles.brandHeader}>
          <div className={styles.brand}>
            <img src="/logo.svg" alt="LabFlow" className={styles.logo} />
            <div className={styles.brandText}>
              <span className={styles.brandName}>LabFlow</span>
              <span className={styles.version}>LIS v4.2</span>
            </div>
          </div>
          <span className={styles.portalBadge}>{t("auth:login.portal")}</span>
        </header>

        {/* Tenant Banner (only rendered when tenant is resolved) */}
        {tenantName && (
          <section
            aria-label={t("auth:login.lab_node_details")}
            className={styles.tenant}
          >
            <div className={styles.tenantRow}>
              <div>
                <h1 className={styles.tenantName}>{tenantName}</h1>
                <p className={styles.tenantSub}>
                  {t("auth:login.staff_sign_in")}
                </p>
              </div>
              {nodeId && (
                <span className={styles.nodeBadge}>
                  <span className={styles.nodeDot} aria-hidden="true" />
                  {nodeId}
                </span>
              )}
            </div>
          </section>
        )}

        {/* Session Expired Notice */}
        {sessionExpiredNotice && (
          <div role="status" className={styles.expiredBanner}>
            <div className={styles.expiredText}>
              <AlertCircle
                className={styles.expiredIcon}
                aria-hidden="true"
                size={16}
              />
              <span>{t("auth:login.session_expired")}</span>
            </div>
            <button
              type="button"
              onClick={() => setSessionExpiredNotice(false)}
              className={styles.dismiss}
              aria-label={t("auth:login.dismiss_session_expired")}
            >
              ✕
            </button>
          </div>
        )}

        {currentUser ? (
          <section
            role="status"
            aria-label={t("auth:login.session_active_aria")}
            className={styles.sessionActive}
          >
            <div>
              <h2 className={styles.sessionTitle}>
                {t("auth:login.session_active_title")}
              </h2>
              <p className={styles.sessionMessage}>
                {t("auth:login.session_active_message", {
                  name: activeName,
                  role: t(`common:role.${currentUser.role}`),
                })}
              </p>
              <p className={styles.sessionHint}>
                {t("auth:login.session_active_hint")}
              </p>
            </div>
            <div className={styles.sessionActions}>
              <button
                type="button"
                onClick={onContinue}
                className={styles.primary}
              >
                <span>{t("auth:login.continue_session")}</span>
                <ArrowRight className={styles.rtlIcon} size={16} />
              </button>
              <button
                type="button"
                onClick={() => void onLogInAsSomeoneElse?.()}
                className={styles.ghost}
              >
                {t("auth:login.log_in_as_someone_else")}
              </button>
            </div>
          </section>
        ) : (
          <form
            onSubmit={(e) => void handleSubmit(e)}
            className={styles.form}
            noValidate={false}
          >
            {/* Email field */}
            <div className={styles.field}>
              <div className={styles.labelRow}>
                <label htmlFor="email" className={styles.label}>
                  {t("auth:login.email")}
                </label>
                <span className={styles.hint}>
                  {t("auth:login.email_hint")}
                </span>
              </div>
              <input
                id="email"
                type="email"
                autoComplete="email"
                required
                placeholder={t("auth:login.email_placeholder")}
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                className={styles.input}
              />
            </div>

            {/* Password field */}
            <div className={styles.field}>
              <div className={styles.labelRow}>
                <label htmlFor="password" className={styles.label}>
                  {t("auth:login.password")}
                </label>
                <button
                  type="button"
                  onClick={() => setShowResetNotice(true)}
                  className={styles.textButton}
                >
                  {t("auth:login.reset_via_admin")}
                </button>
              </div>
              <div className={styles.passwordWrap}>
                <input
                  id="password"
                  type={showPassword ? "text" : "password"}
                  autoComplete="current-password"
                  required
                  placeholder={t("auth:login.password_placeholder")}
                  value={password}
                  onChange={(e) => setPassword(e.target.value)}
                  className={`${styles.input} ${styles.passwordInput}`}
                />
                <button
                  type="button"
                  aria-label={t("auth:login.toggle_password")}
                  onClick={() => setShowPassword(!showPassword)}
                  className={styles.eyeButton}
                >
                  {showPassword ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
            </div>

            {/* Reset Notice */}
            {showResetNotice && (
              <div className={styles.resetNotice}>
                <p>{t("auth:login.reset_help")}</p>
                <button
                  type="button"
                  onClick={() => setShowResetNotice(false)}
                  className={styles.resetDismiss}
                >
                  {t("common:actions.dismiss")}
                </button>
              </div>
            )}

            {/* Submit Button */}
            <div className={styles.submitRow}>
              <button
                type="submit"
                disabled={isLoading}
                className={styles.primary}
              >
                {isLoading ? (
                  <>
                    <Loader2 className={styles.spin} size={16} />
                    <span>{t("auth:login.authenticating")}</span>
                  </>
                ) : (
                  <>
                    <span>{t("auth:login.sign_in")}</span>
                    <ArrowRight className={styles.rtlIcon} size={16} />
                  </>
                )}
              </button>
              <button
                type="button"
                className={styles.forgotLink}
                onClick={() => setForgotOpen(true)}
              >
                Forgot password?
              </button>
            </div>

            {/* Generic Error Notice */}
            {error && (
              <div role="alert" className={styles.error}>
                <AlertCircle
                  className={styles.errorIcon}
                  aria-hidden="true"
                  size={16}
                />
                <span>{error}</span>
              </div>
            )}
          </form>
        )}

        {/* Compliance Footer */}
        <footer className={styles.footer}>
          <div className={styles.footerBadge}>
            <ShieldCheck size={14} aria-hidden="true" />
            <span>{t("auth:login.secured_node")}</span>
          </div>
          <p className={styles.footerText}>{t("auth:login.compliance")}</p>
        </footer>
      </main>

      {forgotOpen && (
        <ForgotPasswordModal
          tenantName={tenantName}
          slug={window.location.hostname.split(".")[0] ?? ""}
          email={email}
          onClose={() => setForgotOpen(false)}
        />
      )}
    </div>
  );
}
