import type { ReactElement } from "react";
import { useEffect, useMemo, useState } from "react";
import { Link, Navigate, Outlet, useLocation, useNavigate } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { fetchTenantContext, getSubdomainTenant } from "../auth/tenantContext";
import { partnersService } from "../partners/partnersService";
import { reportsService } from "../reports/reportsService";
import { sampleService } from "../samples/sampleService";

export function TenantLayout(): ReactElement {
  const navigate = useNavigate();
  const location = useLocation();
  const user = useAuthStore((state) => state.user);
  const accessToken = useAuthStore((state) => state.accessToken);
  const logout = useAuthStore((state) => state.logout);

  const [tenantName, setTenantName] = useState<string>(() => {
    const sub = getSubdomainTenant();
    return sub?.name || "LabFlow";
  });
  const [lang, setLang] = useState<"en" | "ur">("en");
  const [badges, setBadges] = useState({
    pendingApprovals: 0,
    draftSettlements: 0,
    exceptions: 0,
  });

  const userInitials = useMemo(() => {
    if (user?.name) {
      const parts = user.name.trim().split(/\s+/);
      if (parts.length >= 2 && parts[0] && parts[1]) {
        return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
      }
      return user.name.slice(0, 2).toUpperCase();
    }
    if (user?.email) {
      return user.email.slice(0, 2).toUpperCase();
    }
    return "AR";
  }, [user]);

  const displayName = useMemo(() => {
    return user?.name || user?.email || "Ali Raza";
  }, [user]);

  const userRole = useMemo(() => {
    if (!user?.role) return "Staff";
    return user.role.charAt(0).toUpperCase() + user.role.slice(1);
  }, [user?.role]);

  useEffect(() => {
    let active = true;

    void fetchTenantContext().then((info) => {
      if (active && info?.name) {
        setTenantName(info.name);
      }
    });

    const loadBadges = async () => {
      if (!accessToken) return;
      try {
        const [sampleRes, stRes, exRes] = await Promise.allSettled([
          sampleService.listSamples(),
          partnersService.getSettlements({ status: "draft" }),
          reportsService.getExceptions(),
        ]);

        let pendingApprovals = 0;
        if (sampleRes.status === "fulfilled" && sampleRes.value?.results) {
          pendingApprovals = sampleRes.value.results.filter(
            (s) => s.status === "ready",
          ).length;
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

  if (!accessToken) {
    return <Navigate to="/login" replace />;
  }

  const handleLogout = () => {
    logout();
    navigate("/login", { replace: true });
  };

  const isLinkActive = (to: string) => {
    if (to === "/") {
      return location.pathname === "/";
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
                {tenantName}
              </span>
              <span className="px-1.5 py-0.5 rounded text-[10px] uppercase font-semibold tracking-wider bg-[#86f2e4]/60 text-[#006f66]">
                LabFlow
              </span>
            </div>
            <p className="text-xs text-slate-400">All branches • Main Branch</p>
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
        <div className="flex flex-col">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
            Lab Operations
          </div>
          <nav className="flex flex-col gap-0.5">
            <Link
              to="/"
              className={linkClass("/")}
            >
              <span className="material-symbols-outlined text-[18px]">
                home
              </span>
              <span>Home</span>
            </Link>
            <Link
              to="/patients"
              className={linkClass("/patients")}
            >
              <span className="material-symbols-outlined text-[18px]">
                personal_injury
              </span>
              <span>Patients</span>
            </Link>
            <Link
              to="/invoices"
              className={linkClass("/invoices")}
            >
              <span className="material-symbols-outlined text-[18px]">
                receipt_long
              </span>
              <span>Invoices &amp; Payments</span>
            </Link>
            <Link
              to="/samples"
              className={linkClass("/samples")}
            >
              <span className="material-symbols-outlined text-[18px]">
                colorize
              </span>
              <span>Samples</span>
            </Link>
            <Link
              to="/worklist"
              className={linkClass("/worklist")}
            >
              <span className="material-symbols-outlined text-[18px]">
                assignment
              </span>
              <span>Worklist</span>
            </Link>
            <Link
              to="/worklist"
              className="flex items-center gap-2.5 px-3 py-2 rounded-lg text-sm text-slate-700 hover:bg-slate-50 hover:text-slate-900 transition-colors"
            >
              <span className="material-symbols-outlined text-[18px]">
                edit_note
              </span>
              <span>Results Entry</span>
            </Link>
            <Link
              to="/results/approvals"
              className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                isLinkActive("/results/approvals")
                  ? "bg-[#86f2e4]/70 text-[#005c55] font-semibold"
                  : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  verified
                </span>
                <span>Approvals</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-teal-800 font-semibold">
                {badges.pendingApprovals}
              </span>
            </Link>
            <Link
              to="/exceptions"
              className={linkClass("/exceptions")}
            >
              <span className="material-symbols-outlined text-[18px]">
                notification_important
              </span>
              <span>Critical Notifications</span>
            </Link>
            <Link
              to="/reports"
              className={linkClass("/reports")}
            >
              <span className="material-symbols-outlined text-[18px]">
                lab_profile
              </span>
              <span>Reports</span>
            </Link>
            <Link
              to="/exceptions"
              className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                isLinkActive("/exceptions")
                  ? "bg-[#86f2e4]/70 text-[#005c55] font-semibold"
                  : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  warning
                </span>
                <span>Exceptions</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-red-100 text-red-700 font-semibold">
                {badges.exceptions}
              </span>
            </Link>
          </nav>
        </div>

        <div className="flex flex-col">
          <div className="text-[11px] font-semibold text-slate-400 uppercase tracking-wider mb-1 px-3">
            Management
          </div>
          <nav className="flex flex-col gap-0.5">
            <Link
              to="/partners"
              className={linkClass("/partners")}
            >
              <span className="material-symbols-outlined text-[18px]">
                handshake
              </span>
              <span>Partners &amp; Share Ledger</span>
            </Link>
            <Link
              to="/settlements"
              className={`flex items-center justify-between px-3 py-2 rounded-lg text-sm transition-colors ${
                isLinkActive("/settlements")
                  ? "bg-[#86f2e4]/70 text-[#005c55] font-semibold"
                  : "text-slate-700 hover:bg-slate-50 hover:text-slate-900"
              }`}
            >
              <div className="flex items-center gap-2.5">
                <span className="material-symbols-outlined text-[18px]">
                  account_balance_wallet
                </span>
                <span>Settlements</span>
              </div>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-700 font-semibold">
                {badges.draftSettlements}
              </span>
            </Link>
            <Link
              to="/catalog"
              className={linkClass("/catalog")}
            >
              <span className="material-symbols-outlined text-[18px]">
                medical_services
              </span>
              <span>Catalog</span>
            </Link>
            <Link
              to="/settings"
              className={linkClass("/settings")}
            >
              <span className="material-symbols-outlined text-[18px]">
                settings
              </span>
              <span>Settings</span>
            </Link>
          </nav>
        </div>
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
