import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import {
  canAccessPath,
  isRoleEnabled,
  navForRole,
  roleHome,
} from "../auth/access";
import {
  dismissNotice,
  isNoticeDismissed,
  type PostLoginNoticeKind,
} from "../auth/postLoginNotice";
import { fetchTenantContext, getSubdomainTenant } from "../auth/tenantContext";
import { PostLoginNotice } from "../../components/ui/PostLoginNotice";
import { ThemeToggle } from "../../components/ui/ThemeToggle";
import styles from "./TenantLayout.module.css";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { useTranslation } from "react-i18next";

export function TenantLayout(): ReactElement {
  const { t } = useTranslation(["common", "auth"]);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);

  // Start blank: the slug-derived name ("Apexlab") is a guess, not the lab's
  // real brand. Render the resolved tenant name only.
  const [tenantName, setTenantName] = useState<string | null>(null);
  const [tenantCity, setTenantCity] = useState<string>("");
  const [noticeDismissedLocally, setNoticeDismissedLocally] = useState(false);
  const [badges, setBadges] = useState({
    pendingApprovals: 0,
    draftSettlements: 0,
    exceptions: 0,
  });

  const displayName = useMemo(() => {
    return user?.display_name || user?.name || user?.email || t("role.staff");
  }, [user, t]);

  const userInitials = useMemo(() => {
    const source = displayName.trim();
    const parts = source.split(/\s+/);
    if (parts.length >= 2 && parts[0] && parts[1]) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return source.slice(0, 2).toUpperCase();
  }, [displayName]);

  const userRole = useMemo(() => {
    if (!user?.role) return t("role.staff");
    return t(`role.${user.role}`);
  }, [user?.role, t]);

  const navigation = useMemo(
    () => navForRole(user?.role, user?.enabled_roles),
    [user?.role, user?.enabled_roles],
  );

  useEffect(() => {
    let active = true;
    const controller = new AbortController();

    void fetchTenantContext().then((info) => {
      if (!active) return;
      setTenantName(info?.name || getSubdomainTenant()?.name || "LabFlow");
      setTenantCity(info?.city || "");
    });

    const loadBadges = async () => {
      if (!accessToken) return;

      // Do not probe routes the role policy denies; a hidden badge must not
      // generate a stream of 403s in the background.
      const roleEnabled = isRoleEnabled(user?.role, user?.enabled_roles);
      const canReadApprovals =
        roleEnabled && (user?.role === "owner" || user?.role === "pathologist");
      const canReadSettlements =
        roleEnabled && (user?.role === "owner" || user?.role === "manager");
      const canReadExceptions = roleEnabled;

      try {
        const [approvalsRes, stRes, exRes] = await Promise.allSettled([
          canReadApprovals
            ? resultsService.getApprovalsQueue(controller.signal)
            : Promise.resolve(null),
          canReadSettlements
            ? partnersService.getSettlements({
                status: "draft",
                signal: controller.signal,
              })
            : Promise.resolve(null),
          canReadExceptions
            ? reportsService.getExceptions(controller.signal)
            : Promise.resolve(null),
        ]);

        // The badge is the approvals queue itself — counting "ready" samples
        // left a stale number after every result had been approved.
        let pendingApprovals = 0;
        if (approvalsRes.status === "fulfilled" && approvalsRes.value) {
          pendingApprovals = approvalsRes.value.length;
        }

        let draftSettlements = 0;
        if (stRes.status === "fulfilled" && stRes.value?.results) {
          draftSettlements = stRes.value.results.length;
        }

        let exceptions = 0;
        if (exRes.status === "fulfilled" && exRes.value?.counts) {
          exceptions = exRes.value.counts.total || 0;
        }

        if (active) {
          setBadges({ pendingApprovals, draftSettlements, exceptions });
        }
      } catch {
        // Silent catch for resilience
      }
    };

    void loadBadges();

    return () => {
      active = false;
      controller.abort();
    };
  }, [location.pathname, accessToken, user?.role, user?.enabled_roles]);

  if (!accessToken || !user) {
    return <Navigate to="/login" replace />;
  }

  // A role the Platform has disabled for this lab is a dead end: the API
  // refuses it, so never render a dashboard or sidebar for it.
  if (!isRoleEnabled(user.role, user.enabled_roles)) {
    return <Navigate to="/login" replace />;
  }

  // D1/D2: a temporary password and a missing TOTP enrolment are dismissible
  // post-login notices, never gates. The dashboard always loads.

  // S3/S15: owner-only screens never render for staff. The API refuses them
  // independently; this only prevents a dead-end screen.
  if (user && !canAccessPath(user.role, location.pathname)) {
    return <Navigate to={roleHome(user.role)} replace />;
  }

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  // D1/D2: one dismissible notice per login. If both apply, the password
  // notice shows first; the 2FA notice waits for the next login.
  const noticeKind: PostLoginNoticeKind | null = user.must_change_password
    ? "password"
    : !user.totp_enabled
      ? "totp"
      : null;
  const showNotice =
    noticeKind !== null &&
    !noticeDismissedLocally &&
    !isNoticeDismissed(noticeKind, user.id);

  const isLinkActive = (to: string) => {
    if (to === "/") {
      return location.pathname === "/";
    }
    // Tenant settings lives at /settings/tenant; keep its two sibling routes
    // (branches, account) from lighting it up as well.
    if (to === "/settings") {
      return (
        location.pathname === "/settings" ||
        location.pathname === "/settings/tenant"
      );
    }
    return location.pathname === to || location.pathname.startsWith(`${to}/`);
  };

  const linkClass = (to: string) =>
    `${styles.navLink} ${isLinkActive(to) ? styles.navLinkActive : ""}`;

  return (
    <div className={styles.shell}>
      {/* Top Header */}
      <header className={styles.topbar}>
        <div className={styles.brandBlock}>
          <Link
            to="/"
            className={styles.brandLink}
            title={t("topbar.dashboard_title")}
          >
            <svg
              aria-hidden="true"
              className={styles.icon}
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
            >
              <path d="M9 3h6" />
              <path d="M10 3v6l-4.5 9.5A1.8 1.8 0 0 0 7.1 21h9.8a1.8 1.8 0 0 0 1.6-2.5L14 9V3" />
            </svg>
          </Link>
          <div className={styles.brandText}>
            <div className={styles.brandRow}>
              <span className={styles.brandName}>{tenantName ?? "\u00a0"}</span>
              <span className={styles.brandTag}>LabFlow</span>
            </div>
            <p className={styles.brandMeta}>
              {user?.role === "owner" || user?.role === "pathologist"
                ? t("topbar.all_branches")
                : t("topbar.branch_workspace")}
              {tenantCity ? ` • ${tenantCity}` : ""}
            </p>
          </div>
        </div>

        <div className={styles.topActions}>
          <div className={styles.langWrap}>
            <LanguageSwitcher compact />
          </div>
          <ThemeToggle />
          <div className={styles.divider} />
          <div className={styles.userChip}>
            <div className={styles.avatar}>{userInitials}</div>
            <div className={styles.userText}>
              <span className={styles.userName}>{displayName}</span>
              <span className={styles.userRole}>{userRole}</span>
            </div>
            <button
              onClick={handleLogout}
              className={styles.logout}
              title={t("topbar.logout")}
              type="button"
            >
              <svg
                aria-hidden="true"
                className={styles.icon}
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
                <path d="M16 17l5-5-5-5" />
                <path d="M21 12H9" />
              </svg>
            </button>
          </div>
        </div>
      </header>

      {/* Left Sidebar */}
      <aside className={styles.sidebar}>
        {navigation.operations.length > 0 && (
          <div className={styles.navSection}>
            <p className={styles.navLabel}>{t("nav.operations")}</p>
            <nav className={styles.nav}>
              {navigation.operations.map((item) => (
                <Link key={item.to} to={item.to} className={linkClass(item.to)}>
                  <span className={styles.navInner}>
                    <span
                      aria-hidden="true"
                      className={`material-symbols-outlined ${styles.navIcon}`}
                    >
                      {item.icon}
                    </span>
                    <span className={styles.navText}>
                      {t(`nav.${item.labelKey}`)}
                    </span>
                  </span>
                  {item.to === "/results/approvals" &&
                    badges.pendingApprovals > 0 && (
                      <span className={styles.navBadge}>
                        {badges.pendingApprovals}
                      </span>
                    )}
                  {item.to === "/exceptions" && badges.exceptions > 0 && (
                    <span
                      className={`${styles.navBadge} ${styles.navBadgeDanger}`}
                    >
                      {badges.exceptions}
                    </span>
                  )}
                </Link>
              ))}
            </nav>
          </div>
        )}

        {navigation.management.length > 0 && (
          <div className={styles.navSection}>
            <p className={styles.navLabel}>{t("nav.management")}</p>
            <nav className={styles.nav}>
              {navigation.management.map((item) => (
                <Link key={item.to} to={item.to} className={linkClass(item.to)}>
                  <span className={styles.navInner}>
                    <span
                      aria-hidden="true"
                      className={`material-symbols-outlined ${styles.navIcon}`}
                    >
                      {item.icon}
                    </span>
                    <span className={styles.navText}>
                      {t(`nav.${item.labelKey}`)}
                    </span>
                  </span>
                  {item.to === "/settlements" &&
                    badges.draftSettlements > 0 && (
                      <span className={styles.navBadge}>
                        {badges.draftSettlements}
                      </span>
                    )}
                </Link>
              ))}
            </nav>
          </div>
        )}
      </aside>

      {/* Main Content Area */}
      <div className={styles.main}>
        <main className={styles.content}>
          <Outlet />
        </main>
      </div>

      {showNotice && noticeKind === "password" && (
        <PostLoginNotice
          title="Change Your Password"
          body={t("auth:modal.body")}
          primaryLabel="Change Now"
          onPrimary={() => {
            // Taking the action closes the notice for the rest of this login;
            // the next login re-arms it if the password is still temporary.
            dismissNotice("password", user.id);
            setNoticeDismissedLocally(true);
            navigate("/settings/account");
          }}
          onDismiss={() => {
            dismissNotice("password", user.id);
            setNoticeDismissedLocally(true);
          }}
        />
      )}

      {showNotice && noticeKind === "totp" && (
        <PostLoginNotice
          title="Enable 2FA on Your Account"
          primaryLabel="Enable Now"
          onPrimary={() => {
            dismissNotice("totp", user.id);
            setNoticeDismissedLocally(true);
            navigate("/settings/account");
          }}
          onDismiss={() => {
            dismissNotice("totp", user.id);
            setNoticeDismissedLocally(true);
          }}
        />
      )}
    </div>
  );
}
