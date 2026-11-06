import type { ReactElement, ReactNode } from "react";
import { Building2, LayoutDashboard, LogOut, PlusCircle, ShieldCheck } from "lucide-react";
import { Link, useLocation, useNavigate } from "react-router-dom";

import { usePlatformAuthStore } from "./platformAuthStore";

/** Only the Phase 1 sections exist in the sidebar by design. */
const NAV_ITEMS = [
  { to: "/platform/overview", label: "Overview", Icon: LayoutDashboard },
  { to: "/platform/tenants", label: "Labs", Icon: Building2 },
  { to: "/platform/tenants/new", label: "Provision New Lab", Icon: PlusCircle },
] as const;

export function PlatformLayout({
  children,
}: {
  children: ReactNode;
}): ReactElement {
  const platformUser = usePlatformAuthStore((state) => state.platformUser);
  const logout = usePlatformAuthStore((state) => state.logout);
  const navigate = useNavigate();
  const location = useLocation();

  const handleLogout = async () => {
    await logout();
    navigate("/platform/login", { replace: true });
  };

  return (
    <div
      className="min-h-screen bg-slate-50 text-slate-900"
      style={{
        fontFamily: "'Inter', 'Plus Jakarta Sans', system-ui, sans-serif",
      }}
    >
      <div className="flex min-h-screen">
        <aside className="hidden w-64 flex-col justify-between bg-[#0E6B3A] text-white md:flex">
          <div>
            <div className="flex items-center gap-2 px-6 py-6">
              <ShieldCheck className="h-6 w-6" aria-hidden="true" />
              <div>
                <p
                  className="text-base font-bold leading-tight"
                  style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
                >
                  LabFlow Platform
                </p>
                <p className="text-[11px] uppercase tracking-widest text-emerald-100">
                  Apex Control
                </p>
              </div>
            </div>

            <nav className="mt-2 flex flex-col gap-1 px-3">
              {NAV_ITEMS.map(({ to, label, Icon }) => {
                const active =
                  location.pathname === to ||
                  (to === "/platform/tenants" &&
                    location.pathname.startsWith("/platform/tenants/") &&
                    location.pathname !== "/platform/tenants/new");
                return (
                  <Link
                    key={to}
                    to={to}
                    className={[
                      "flex items-center gap-3 rounded-lg px-3 py-2 text-sm font-medium transition-colors",
                      active
                        ? "bg-white/15 text-white"
                        : "text-emerald-50/80 hover:bg-white/10 hover:text-white",
                    ].join(" ")}
                  >
                    <Icon className="h-4 w-4" aria-hidden="true" />
                    {label}
                  </Link>
                );
              })}
            </nav>
          </div>

          <div className="border-t border-white/15 px-4 py-4">
            <p className="truncate text-sm font-semibold">
              {platformUser?.email ?? "Unknown operator"}
            </p>
            <p className="text-[11px] uppercase tracking-widest text-emerald-100">
              {platformUser?.role ?? "platform"}
            </p>
            <button
              type="button"
              onClick={handleLogout}
              className="mt-3 flex items-center gap-2 rounded-lg border border-white/25 px-3 py-1.5 text-xs font-semibold hover:bg-white/10"
            >
              <LogOut className="h-3.5 w-3.5" aria-hidden="true" />
              Logout
            </button>
          </div>
        </aside>

        <main className="flex-1 overflow-y-auto">{children}</main>
      </div>
    </div>
  );
}
