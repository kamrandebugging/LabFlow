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
import { ForcedPasswordChangeScreen } from "../auth/ForcedPasswordChangeScreen";
import {
  canAccessPath,
  navForRole,
  needsTotpEnrolment,
  ROLE_LABELS,
  roleHome,
} from "../auth/access";
import { fetchTenantContext, getSubdomainTenant } from "../auth/tenantContext";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";

export function TenantLayout(): ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);

  // Start blank: the slug-derived name ("Apexlab") is a guess, not the lab's
  // real brand. Render the resolved tenant name only.
  const [tenantName, setTenantName] = useState<string | null>(null);
  const [tenantCity, setTenantCity] = useState<string>("");
  const [lang, setLang] = useState<"en" | "ur">("en");
  const [badges, setBadges] = useState({
    pendingApprovals: 0,
    draftSettlements: 0,
    exceptions: 0,
  });

  const displayName = useMemo(() => {
    return user?.display_name || user?.name || user?.email || "Staff";
  }, [user]);

  const userInitials = useMemo(() => {
    const source = displayName.trim();
    const parts = source.split(/\s+/);
    if (parts.length >= 2 && parts[0] && parts[1]) {
      return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
    }
    return source.slice(0, 2).toUpperCase();
  }, [displayName]);

  const userRole = useMemo(() => {
    if (!user?.role) return "Staff";
    return ROLE_LABELS[user.role] ?? "Staff";
  }, [user?.role]);

  const navigation = useMemo(() => navForRole(user?.role), [user?.role]);

  useEffect(() => {
    let active = true;

    void fetchTenantContext().then((info) => {
      if (!active) return;
      setTenantName(info?.name || getSubdomainTenant()?.name || "LabFlow");
      setTenantCity(info?.city || "");
    });

    const loadBadges = async () => {
      if (!accessToken) return;
      try {
        const [approvalsRes, stRes, exRes] = await Promise.allSettled([
          resultsService.getApprovalsQueue(),
          partnersService.getSettlements({ status: "draft" }),
          reportsService.getExceptions(),
        ]);

        // The badge is the approvals queue itself — counting "ready" samples
        // left a stale number after every result had been approved.
        let pendingApprovals = 0;
        if (approvalsRes.status === "fulfilled") {
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
    };
  }, [location.pathname, accessToken]);

  if (!accessToken || !user) {
    return <Navigate to="/login" replace />;
  }

  // S7: the temporary-password flow is a hard gate, not a dismissible modal.
  if (user?.must_change_password) {
    return <ForcedPasswordChangeScreen />;
  }

  // S6: a mandatory-TOTP role cannot reach the shell before enrolment.
  if (needsTotpEnrolment(user?.role, user?.totp_enabled)) {
    return <Navigate to="/login/enroll" replace />;
  }

  // S3/S15: owner-only screens never render for staff. The API refuses them
  // independently; this only prevents a dead-end screen.
  if (user && !canAccessPath(user.role, location.pathname)) {
    return <Navigate to={roleHome(user.role)} replace />;
  }

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

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
    `flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm transition-colors ${
      isLinkActive(to)
        ? "bg-[#86f2e4]/70 text-[#005c55] font-semibold"
        : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
    }`;

  return (
    <div className="bg-[#faf8ff] text-[#131b2e] antialiased min-h-screen">
      {/* Top Header */}
      <header className="fixed top-0 left-0 right-0 h-16 bg-white border-b border-slate-200/80 z-50 px-6 flex items-center justify-between shadow-[0_1px_8px_rgba(0,0,0,0.02)]">
        <div className="flex items-center gap-4">
          <Link
            to="/"
            className="w-9 h-9 rounded-lg bg-[#005c55] flex items-center justify-center text-white shadow-sm hover:opacity-90 transition-opacity"
            title="LabFlow Dashboard"
          >
            <span className="material-symbols-outlined text-[20px]">
              science
            </span>
          </Link>
          <div>
            <div className="flex items-center gap-1.5">
              <span className="text-base text-slate-900 font-semibold tracking-tight">
                {tenantName ?? "\u00a0"}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold tracking-wider bg-[#86f2e4]/60 text-[#006f66]">
                LabFlow
              </span>
            </div>
            <p className="text-xs text-slate-400">
              {user?.role === "owner" || user?.role === "pathologist"
                ? "All branches"
                : "Branch workspace"}
              {tenantCity ? ` • ${tenantCity}` : ""}
            </p>
          </div>
        </div>

        <div className="flex items-center gap-4">
          <div className="flex items-center bg-slate-100 p-1 rounded-full border border-slate-200/60">
            <button
              onClick={() => setLang("en")}
              className={`px-3 py-1 rounded-full text-xs font-semibold shadow-sm transition-all ${
                lang === "en"
                  ? "bg-white text-[#005c55]"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              type="button"
            >
              English
            </button>
            <button
              onClick={() => setLang("ur")}
              className={`px-3 py-1 rounded-full text-xs transition-colors ${
                lang === "ur"
                  ? "bg-white text-[#005c55] font-semibold shadow-sm"
                  : "text-slate-500 hover:text-slate-900"
              }`}
              type="button"
            >
              اردو
            </button>
          </div>
          <div className="h-6 w-px bg-slate-200" />
          <div className="flex items-center gap-3 pl-1">
            <div className="w-9 h-9 rounded-full bg-[#86f2e4] flex items-center justify-center text-xs font-bold text-[#006f66] ring-2 ring-[#005c55]/20">
              {userInitials}
            </div>
            <div className="hidden sm:flex flex-col text-left">
              <span className="text-xs font-semibold text-slate-900 leading-tight">
                {displayName}
              </span>
              <span className="text-[11px] text-slate-500 leading-tight">
                {userRole}
              </span>
            </div>
            <button
              onClick={handleLogout}
              className="text-slate-400 hover:text-red-600 ml-1 p-1 rounded transition-colors flex items-center"
              title="Log out"
              type="button"
            >
              <span className="material-symbols-outlined text-[20px]">
                logout
              </span>
            </button>
          </div>
        </div>
      </header>

      {/* Left Sidebar */}
      <aside className="fixed left-0 top-16 bottom-0 w-60 bg-white border-r border-slate-200/80 z-40 overflow-y-auto p-4 flex flex-col gap-6">
        {navigation.operations.length > 0 && (
          <div className="flex flex-col">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
              Lab Operations
            </div>
            <nav className="flex flex-col gap-0.5">
              {navigation.operations.map((item) => (
                <Link key={item.to} to={item.to} className={linkClass(item.to)}>
                  <div className="flex items-center gap-2.5">
                    <span className="material-symbols-outlined text-[18px]">
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>
                  {item.to === "/results/approvals" &&
                    badges.pendingApprovals > 0 && (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-teal-800 font-semibold">
                        {badges.pendingApprovals}
                      </span>
                    )}
                  {item.to === "/exceptions" && badges.exceptions > 0 && (
                    <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold">
                      {badges.exceptions}
                    </span>
                  )}
                </Link>
              ))}
            </nav>
          </div>
        )}

        {navigation.management.length > 0 && (
          <div className="flex flex-col">
            <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
              Management
            </div>
            <nav className="flex flex-col gap-0.5">
              {navigation.management.map((item) => (
                <Link key={item.to} to={item.to} className={linkClass(item.to)}>
                  <div className="flex items-center gap-2.5">
                    <span className="material-symbols-outlined text-[18px]">
                      {item.icon}
                    </span>
                    <span>{item.label}</span>
                  </div>
                  {item.to === "/settlements" &&
                    badges.draftSettlements > 0 && (
                      <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
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
      <div className="pl-60 min-h-screen flex flex-col bg-[#f8f9ff]">
        <main className="flex-1 pt-16">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
