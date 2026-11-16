import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Link,
  Navigate,
  Outlet,
  useLocation,
  useNavigate,
} from "react-router-dom";
import { useTranslation } from "react-i18next";

import { useAuthStore } from "../auth/authStore";
import {
  canAccessPath,
  isRoleEnabled,
  navForRole,
  roleHome,
  type NavItem,
} from "../auth/access";
import {
  dismissNotice,
  isNoticeDismissed,
  type PostLoginNoticeKind,
} from "../auth/postLoginNotice";
import { fetchTenantContext, getSubdomainTenant } from "../auth/tenantContext";
import { PostLoginNotice } from "../../components/ui/PostLoginNotice";
import { useTheme } from "../../theme/themeContext";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import { LanguageSwitcher } from "../../components/LanguageSwitcher";
import { revealThemeChange } from "../../lib/motion";

const DESK_PATHS = [
  "/",
  "/patients",
  "/invoices",
  "/samples",
  "/worklist",
  "/results/approvals",
  "/exceptions",
];

const CONTROL_PATHS = [
  "/catalog",
  "/settings/staff",
  "/reports",
  "/settings/tenant",
  "/settings",
  "/settlements",
  "/partners",
  "/settings/branches",
  "/settings/account",
];

export function TenantLayout(): ReactElement {
  const { t } = useTranslation(["common", "auth"]);
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);
  const { resolved, setPreference } = useTheme();

  const [tenantName, setTenantName] = useState<string | null>(null);
  const [tenantCity, setTenantCity] = useState<string>("");
  const [noticeDismissedLocally, setNoticeDismissedLocally] = useState(false);
  const [isSidebarCollapsed, setIsSidebarCollapsed] = useState(false);
  const [isMobileMenuOpen, setIsMobileMenuOpen] = useState(false);
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

  // Group permitted items Veyla-style: DESK (daily work) vs CONTROLS (config)
  const deskNav = useMemo(() => {
    const all = [...navigation.operations, ...navigation.management];
    return DESK_PATHS.map((path) => all.find((item) => item.to === path)).filter(
      (item): item is NavItem => Boolean(item),
    );
  }, [navigation]);

  const controlsNav = useMemo(() => {
    const all = [...navigation.operations, ...navigation.management];
    return CONTROL_PATHS.map((path) =>
      all.find((item) => item.to === path),
    ).filter((item): item is NavItem => Boolean(item));
  }, [navigation]);

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

  // Circular reveal theme toggle — the shared helper owns the View
  // Transition, the clip-path origin and the reduced-motion fallback.
  const toggleTheme = useCallback(
    (event: React.MouseEvent<HTMLButtonElement>) => {
      const next = resolved === "dark" ? "light" : "dark";
      revealThemeChange(
        { clientX: event.clientX, clientY: event.clientY },
        () => setPreference(next),
      );
    },
    [resolved, setPreference],
  );

  // Compute breadcrumb label
  const breadcrumb = useMemo(() => {
    const p = location.pathname;
    if (p === "/") return { section: "Desk", page: t("nav.home") || "Overview" };
    if (p.startsWith("/patients")) return { section: "Desk", page: t("nav.patients") };
    if (p.startsWith("/invoices")) return { section: "Desk", page: t("nav.invoices") };
    if (p.startsWith("/samples")) return { section: "Desk", page: t("nav.samples") };
    if (p.startsWith("/worklist")) return { section: "Desk", page: t("nav.worklist") };
    if (p.startsWith("/results")) return { section: "Desk", page: t("nav.approvals") };
    if (p.startsWith("/exceptions")) return { section: "Desk", page: t("nav.exceptions") };
    if (p.startsWith("/reports")) return { section: "Controls", page: t("nav.reports") };
    if (p.startsWith("/catalog")) return { section: "Controls", page: t("nav.catalog") };
    if (p.startsWith("/settings/staff")) return { section: "Controls", page: t("nav.staff") };
    if (p.startsWith("/settings/branches")) return { section: "Controls", page: t("nav.branches") };
    if (p.startsWith("/settings/account")) return { section: "Controls", page: t("nav.account") };
    if (p.startsWith("/settings")) return { section: "Controls", page: t("nav.settings") };
    if (p.startsWith("/settlements")) return { section: "Controls", page: t("nav.settlements") };
    if (p.startsWith("/partners")) return { section: "Controls", page: t("nav.partners") };
    return { section: "Desk", page: "Overview" };
  }, [location.pathname, t]);

  if (!accessToken || !user) {
    return <Navigate to="/login" replace />;
  }

  if (!isRoleEnabled(user.role, user.enabled_roles)) {
    return <Navigate to="/login" replace />;
  }

  if (user && !canAccessPath(user.role, location.pathname)) {
    return <Navigate to={roleHome(user.role)} replace />;
  }

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

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
    if (to === "/settings") {
      return (
        location.pathname === "/settings" ||
        location.pathname === "/settings/tenant"
      );
    }
    return location.pathname === to || location.pathname.startsWith(`${to}/`);
  };

  const renderNavSection = (label: string, items: NavItem[]) => {
    if (items.length === 0) return null;
    return (
      <div className="space-y-1">
        {!isSidebarCollapsed ? (
          <p className="px-3 text-[11px] font-bold uppercase tracking-wider text-[var(--color-text-muted)] mb-1">
            {label}
          </p>
        ) : null}
        <nav className="space-y-0.5">
          {items.map((item) => {
            const active = isLinkActive(item.to);
            return (
              <Link
                key={item.to}
                to={item.to}
                title={isSidebarCollapsed ? t(`nav.${item.labelKey}`) : undefined}
                onClick={() => setIsMobileMenuOpen(false)}
                className={`group flex items-center justify-between px-3 py-2 rounded-full text-xs font-semibold transition-colors ${
                  active
                    ? "bg-[var(--veyla-black)] text-[var(--color-surface)] dark:bg-[var(--color-surface)] dark:text-[var(--veyla-black)] shadow-[var(--shadow-veyla-pill)]"
                    : "text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--veyla-well)]"
                }`}
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span
                    aria-hidden="true"
                    className="material-symbols-outlined text-[19px] shrink-0"
                  >
                    {item.icon}
                  </span>
                  {!isSidebarCollapsed ? (
                    <span className="truncate">{t(`nav.${item.labelKey}`)}</span>
                  ) : null}
                </div>
                {!isSidebarCollapsed ? (
                  <>
                    {item.to === "/results/approvals" &&
                      badges.pendingApprovals > 0 && (
                        <span className="ms-2 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#e6f4ea] text-[#0e6b3a] dark:bg-[rgba(82,183,136,0.2)] dark:text-[#7cd3a2]">
                          {badges.pendingApprovals}
                        </span>
                      )}
                    {item.to === "/exceptions" && badges.exceptions > 0 && (
                      <span className="ms-2 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[#fee2e2] text-[#b91c1c] dark:bg-[rgba(239,68,68,0.2)] dark:text-[#fca5a5]">
                        {badges.exceptions}
                      </span>
                    )}
                    {item.to === "/settlements" &&
                      badges.draftSettlements > 0 && (
                        <span className="ms-2 px-2 py-0.5 rounded-full text-[10px] font-mono font-bold bg-[var(--veyla-well)] text-[var(--color-text-muted)] border border-[var(--color-border)]">
                          {badges.draftSettlements}
                        </span>
                      )}
                  </>
                ) : null}
              </Link>
            );
          })}
        </nav>
      </div>
    );
  };

  return (
    <div className="min-h-screen bg-[var(--veyla-page)] text-[var(--color-body)] flex font-sans">
      {/* Sidebar Overlay on Mobile */}
      {isMobileMenuOpen ? (
        <div
          aria-hidden="true"
          className="fixed inset-0 z-40 bg-black/40 backdrop-blur-sm lg:hidden"
          onClick={() => setIsMobileMenuOpen(false)}
        />
      ) : null}

      {/* Veyla Left Sidebar */}
      <aside
        className={`fixed lg:sticky top-0 z-50 h-screen bg-[var(--veyla-card)] border-e border-[var(--color-border)] shadow-[var(--shadow-veyla-card)] flex flex-col justify-between transition-all duration-300 ease-in-out ${
          isSidebarCollapsed ? "w-20" : "w-64"
        } ${
          isMobileMenuOpen
            ? "translate-x-0"
            : "-translate-x-full lg:translate-x-0 rtl:translate-x-full rtl:lg:translate-x-0"
        }`}
      >
        {/* Sidebar Header: Logo & Collapse Toggle */}
        <div className="p-4 border-b border-[var(--color-card-border)] flex items-center justify-between gap-2">
          <Link
            to="/"
            className="flex items-center gap-2.5 min-w-0 group"
            title={t("topbar.dashboard_title")}
          >
            <div className="w-9 h-9 rounded-full bg-[var(--veyla-teal)] text-[var(--veyla-teal-text)] flex items-center justify-center shrink-0 shadow-sm">
              <svg
                aria-hidden="true"
                className="w-5 h-5"
                viewBox="0 0 24 24"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.2"
                strokeLinecap="round"
                strokeLinejoin="round"
              >
                <path d="M9 3h6" />
                <path d="M10 3v6l-4.5 9.5A1.8 1.8 0 0 0 7.1 21h9.8a1.8 1.8 0 0 0 1.6-2.5L14 9V3" />
              </svg>
            </div>
            {!isSidebarCollapsed ? (
              <div className="min-w-0">
                <span className="block font-bold text-sm text-[var(--color-text)] tracking-tight truncate">
                  {tenantName ?? "LabFlow"}
                </span>
                <span className="block text-[10px] font-bold uppercase tracking-wider text-[var(--color-text-muted)]">
                  LIS Workspace
                </span>
              </div>
            ) : null}
          </Link>

          <button
            type="button"
            onClick={() => setIsSidebarCollapsed((prev) => !prev)}
            aria-label={isSidebarCollapsed ? "Expand sidebar" : "Collapse sidebar"}
            className="hidden lg:flex w-7 h-7 rounded-full items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-text)] hover:bg-[var(--veyla-well)] transition-colors"
          >
            <span
              aria-hidden="true"
              className="material-symbols-outlined text-[18px]"
            >
              {isSidebarCollapsed ? "chevron_right" : "chevron_left"}
            </span>
          </button>
        </div>

        {/* Grouped Nav Items: DESK & CONTROLS */}
        <div className="flex-1 overflow-y-auto px-3 py-4 space-y-6">
          {renderNavSection("DESK", deskNav)}
          {renderNavSection("CONTROLS", controlsNav)}
        </div>

        {/* Sidebar Footer: Settings, Help, Account card with queue-progress ring */}
        <div className="p-3 border-t border-[var(--color-card-border)] space-y-2 bg-[var(--veyla-card)]">
          {!isSidebarCollapsed ? (
            <div className="flex items-center justify-between px-2 text-xs text-[var(--color-text-muted)]">
              <Link
                to="/settings/tenant"
                className="hover:text-[var(--color-text)] font-semibold transition-colors inline-flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[15px]">
                  settings
                </span>
                <span>Settings</span>
              </Link>
              <a
                href="#help"
                onClick={(e) => {
                  e.preventDefault();
                  alert(
                    "LabFlow Help & Documentation is active. For technical assistance, contact your lab administrator.",
                  );
                }}
                className="hover:text-[var(--color-text)] font-semibold transition-colors inline-flex items-center gap-1"
              >
                <span className="material-symbols-outlined text-[15px]">
                  help
                </span>
                <span>Help</span>
              </a>
            </div>
          ) : null}

          {/* Account Card with Queue-Progress Ring */}
          <div className="bg-[var(--veyla-well)] rounded-2xl p-2.5 flex items-center justify-between gap-2 border border-[var(--color-border)]">
            <div className="flex items-center gap-2.5 min-w-0">
              <div className="relative shrink-0">
                <div className="w-8 h-8 rounded-full bg-[var(--veyla-teal)] text-[var(--veyla-teal-text)] font-bold text-xs flex items-center justify-center">
                  {userInitials}
                </div>
                {badges.pendingApprovals > 0 ? (
                  <span
                    title={`${badges.pendingApprovals} pending in queue`}
                    className="absolute -top-1 -right-1 w-3.5 h-3.5 rounded-full bg-[var(--color-brand)] border-2 border-[var(--veyla-well)] text-[8px] font-mono font-bold text-white flex items-center justify-center"
                  >
                    •
                  </span>
                ) : null}
              </div>
              {!isSidebarCollapsed ? (
                <div className="min-w-0">
                  <p className="text-xs font-bold text-[var(--color-text)] truncate">
                    {displayName}
                  </p>
                  <p className="text-[10px] text-[var(--color-text-muted)] font-medium truncate">
                    {userRole}
                  </p>
                </div>
              ) : null}
            </div>

            <button
              onClick={handleLogout}
              type="button"
              title={t("topbar.logout")}
              aria-label={t("topbar.logout")}
              className="w-7 h-7 rounded-full flex items-center justify-center text-[var(--color-text-muted)] hover:text-[var(--color-danger)] hover:bg-[var(--veyla-card)] transition-colors shrink-0"
            >
              <span className="material-symbols-outlined text-[17px]">
                logout
              </span>
            </button>
          </div>
        </div>
      </aside>

      {/* Main Workspace Area */}
      <div className="flex-1 flex flex-col min-w-0">
        {/* Veyla Top Bar */}
        <header className="sticky top-0 z-30 h-16 bg-[var(--veyla-card)]/90 backdrop-blur-md border-b border-[var(--color-border)] px-4 sm:px-6 flex items-center justify-between gap-3 shadow-sm">
          {/* Left: Mobile Toggle + Breadcrumb */}
          <div className="flex items-center gap-3 min-w-0">
            <button
              type="button"
              onClick={() => setIsMobileMenuOpen((p) => !p)}
              className="lg:hidden w-8 h-8 rounded-full flex items-center justify-center text-[var(--color-text)] hover:bg-[var(--veyla-well)]"
              aria-label="Toggle navigation"
            >
              <span className="material-symbols-outlined text-[20px]">
                menu
              </span>
            </button>

            <nav aria-label="Breadcrumb" className="flex items-center gap-1.5 text-xs text-[var(--color-text-muted)] truncate">
              <span className="font-semibold text-[var(--color-text)]">{breadcrumb.section}</span>
              <span>/</span>
              <span className="text-[var(--color-text-muted)] truncate">{breadcrumb.page}</span>
            </nav>
          </div>

          {/* Right: System Status, Lang, Theme Toggle, Bell, Tenant Info, "+ New" Button */}
          <div className="flex items-center gap-2 sm:gap-3 shrink-0">
            {/* System Status Pill */}
            <div className="hidden sm:inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-[11px] font-semibold bg-[var(--veyla-well)] text-[var(--color-text)] border border-[var(--color-border)]">
              <span
                aria-hidden="true"
                className="w-2 h-2 rounded-full bg-[var(--color-success)] animate-pulse"
              />
              <span>Live • System normal</span>
            </div>

            {/* Language Switcher */}
            <div className="flex items-center">
              <LanguageSwitcher compact />
            </div>

            {/* Circular Reveal Theme Toggle */}
            <button
              type="button"
              onClick={toggleTheme}
              aria-label={
                resolved === "dark"
                  ? "Switch to Light theme"
                  : "Switch to Dark theme"
              }
              title={
                resolved === "dark"
                  ? "Switch to Light theme"
                  : "Switch to Dark theme"
              }
              className="w-8 h-8 rounded-full flex items-center justify-center bg-[var(--veyla-well)] text-[var(--color-text)] hover:bg-[var(--veyla-teal)]/40 transition-colors border border-[var(--color-border)]"
            >
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px]"
              >
                {resolved === "dark" ? "light_mode" : "dark_mode"}
              </span>
            </button>

            {/* Notification Bell */}
            <button
              type="button"
              title="Notifications"
              aria-label="Notifications"
              onClick={() => navigate("/exceptions")}
              className="relative w-8 h-8 rounded-full flex items-center justify-center bg-[var(--veyla-well)] text-[var(--color-text)] hover:bg-[var(--veyla-teal)]/40 transition-colors border border-[var(--color-border)]"
            >
              <span
                aria-hidden="true"
                className="material-symbols-outlined text-[18px]"
              >
                notifications
              </span>
              {badges.exceptions > 0 ? (
                <span className="absolute top-1 end-1 w-2 h-2 rounded-full bg-[var(--color-danger)] ring-2 ring-[var(--veyla-card)]" />
              ) : null}
            </button>

            {/* Tenant Chip */}
            <div className="hidden md:flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-[var(--veyla-well)] text-[var(--color-text)] border border-[var(--color-border)]">
              <span className="truncate max-w-[120px]">
                {tenantName ?? "Apexlab"}
              </span>
              {tenantCity ? (
                <span className="text-[var(--color-text-muted)] font-normal truncate">
                  • {tenantCity}
                </span>
              ) : null}
            </div>

            {/* Global "+ New" Quick-Create Button */}
            <button
              type="button"
              onClick={() => navigate("/invoices/new")}
              className="inline-flex items-center gap-1 px-3.5 py-1.5 rounded-full font-bold text-xs bg-[var(--veyla-black)] text-[var(--color-surface)] dark:bg-[var(--color-surface)] dark:text-[var(--veyla-black)] shadow-[var(--shadow-veyla-pill)] hover:opacity-90 active:scale-95 transition-all"
            >
              <span className="text-base leading-none">+</span>
              <span>New</span>
            </button>
          </div>
        </header>

        {/* Content Outlet */}
        <main className="flex-1 p-4 sm:p-6 lg:p-8 max-w-7xl w-full mx-auto">
          <Outlet />
        </main>
      </div>

      {/* Dismissible Post-Login Notices */}
      {showNotice && noticeKind === "password" && (
        <PostLoginNotice
          title="Change Your Password"
          body={t("auth:modal.body")}
          primaryLabel="Change Now"
          onPrimary={() => {
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
