import React, { useState } from "react";
import { Link, useLocation, useNavigate } from "react-router-dom";
import { usePlatformAuthStore } from "./platformAuthStore";

interface NavItem {
  name: string;
  path: string;
  icon: string;
  phase2?: boolean;
}

const NAV_ITEMS: NavItem[] = [
  { name: "Overview", path: "/platform/overview", icon: "dashboard" },
  { name: "Labs", path: "/platform/tenants", icon: "biotech" },
  {
    name: "Subscriptions",
    path: "/platform/subscriptions",
    icon: "payments",
    phase2: true,
  },
  {
    name: "Access",
    path: "/platform/access",
    icon: "admin_panel_settings",
    phase2: true,
  },
  { name: "Users", path: "/platform/users", icon: "group", phase2: true },
  {
    name: "Demo Requests",
    path: "/platform/demo-requests",
    icon: "contact_page",
    phase2: true,
  },
  {
    name: "Health",
    path: "/platform/health",
    icon: "monitor_heart",
    phase2: true,
  },
  {
    name: "Audit Log",
    path: "/platform/audit",
    icon: "receipt_long",
    phase2: true,
  },
  {
    name: "Settings",
    path: "/platform/settings",
    icon: "settings",
    phase2: true,
  },
];

export function PlatformLayout({
  children,
}: {
  children: React.ReactNode;
}): JSX.Element {
  const location = useLocation();
  const navigate = useNavigate();
  const platformUser = usePlatformAuthStore((state) => state.platformUser);
  const logout = usePlatformAuthStore((state) => state.logout);
  const [searchQuery, setSearchQuery] = useState("");

  const handleSearchKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === "Enter" && searchQuery.trim()) {
      navigate(`/platform/tenants?q=${encodeURIComponent(searchQuery.trim())}`);
    }
  };

  const handleLogout = async () => {
    await logout();
    navigate("/platform/login");
  };

  return (
    <div className="bg-surface font-body-md text-on-surface antialiased min-h-screen">
      {/* Fixed Sidebar */}
      <aside className="fixed left-0 top-0 h-full w-64 bg-inverse-surface z-50 flex flex-col justify-between select-none">
        <div className="flex flex-col">
          {/* Brand Header */}
          <div className="h-14 px-space-md flex items-center justify-between border-b border-white/10 bg-inverse-surface">
            <Link
              to="/platform/overview"
              className="flex items-center gap-space-sm"
            >
              <img
                src="/logo.svg"
                alt="LabFlow Platform Logo"
                className="h-8 w-8 object-contain rounded"
              />
              <span className="font-headline-sm text-headline-sm text-surface-container-lowest tracking-tight">
                LabFlow
              </span>
            </Link>
            <span className="bg-primary-container text-surface-container-lowest font-code-sm text-[11px] uppercase px-space-xs py-space-2xs rounded tracking-wider font-semibold">
              PLATFORM
            </span>
          </div>

          {/* Navigation Links */}
          <nav className="flex flex-col gap-space-2xs px-space-sm mt-space-sm">
            {NAV_ITEMS.map((item) => {
              const isActive =
                location.pathname === item.path ||
                (item.path === "/platform/tenants" &&
                  location.pathname.startsWith("/platform/tenants"));

              return (
                <Link
                  key={item.path}
                  to={item.path}
                  className={`flex items-center justify-between px-space-sm py-space-xs rounded transition-colors ${
                    isActive
                      ? "bg-primary-container text-on-primary-container font-label-md shadow-sm"
                      : "text-outline-variant hover:bg-white/5 hover:text-surface-container-lowest"
                  }`}
                >
                  <div className="flex items-center gap-space-sm">
                    <span className="material-symbols-outlined text-[18px]">
                      {item.icon}
                    </span>
                    <span className="font-label-md text-label-md">
                      {item.name}
                    </span>
                  </div>
                  {item.phase2 && (
                    <span className="text-[10px] font-code-sm uppercase px-1 py-0.5 rounded bg-white/10 text-outline-variant">
                      P2
                    </span>
                  )}
                </Link>
              );
            })}
          </nav>
        </div>

        {/* Sidebar Footer */}
        <div className="p-space-md border-t border-white/10 bg-inverse-surface">
          <div className="flex items-center justify-between text-outline-variant font-code-sm text-code-sm">
            <span className="uppercase tracking-wider">Node: PK-ISB-01</span>
            <span className="flex h-2.5 w-2.5 rounded-full bg-primary-fixed-dim shadow-[0_0_8px_rgba(133,216,156,0.8)]"></span>
          </div>
        </div>
      </aside>

      {/* Main Content Area */}
      <div className="pl-64">
        {/* Fixed Top Bar */}
        <header className="fixed top-0 left-64 right-0 h-14 bg-surface-container-lowest border-b border-outline-variant/40 z-40 flex items-center justify-between px-space-xl">
          <div className="flex items-center gap-space-xl flex-1 max-w-xl">
            <div className="relative w-full max-w-md">
              <span className="material-symbols-outlined absolute left-space-sm top-1/2 -translate-y-1/2 text-outline text-[18px]">
                search
              </span>
              <input
                className="w-full h-8 pl-8 pr-12 bg-surface-container-low text-on-surface placeholder:text-outline border border-outline-variant/60 rounded font-body-sm text-body-sm focus:outline-none focus:border-primary focus:ring-1 focus:ring-primary"
                placeholder="Search labs, tenants, audit records..."
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onKeyDown={handleSearchKeyDown}
              />
              <div className="absolute right-space-xs top-1/2 -translate-y-1/2 flex items-center gap-space-2xs px-space-xs py-space-2xs bg-surface-container-lowest border border-outline-variant/60 rounded">
                <span className="font-code-sm text-code-sm text-outline">
                  Ctrl+K
                </span>
              </div>
            </div>
          </div>

          <div className="flex items-center gap-space-lg">
            {/* System Status Pill */}
            <div className="flex items-center gap-space-xs px-space-sm py-space-2xs bg-surface-container-low border border-outline-variant/40 rounded">
              <span className="flex h-2 w-2 rounded-full bg-primary animate-pulse"></span>
              <span className="font-label-sm text-label-sm text-on-surface-variant font-medium">
                All Systems Live
              </span>
            </div>

            {/* Operator User Block */}
            <div className="flex items-center gap-space-md border-l border-outline-variant/40 pl-space-lg">
              <div className="flex flex-col text-right">
                <div className="flex items-center justify-end gap-space-xs">
                  <span className="font-title-sm text-title-sm text-on-surface">
                    {platformUser?.email.split("@")[0] || "Kamran"}
                  </span>
                  <span className="h-1.5 w-1.5 rounded-full bg-primary"></span>
                </div>
                <span className="font-label-sm text-label-sm text-outline">
                  Platform Owner
                </span>
              </div>
              <button
                onClick={handleLogout}
                title="Sign Out"
                className="w-8 h-8 rounded-full bg-primary text-on-primary flex items-center justify-center hover:bg-primary-container transition-colors shadow-sm"
              >
                <span className="material-symbols-outlined text-[18px]">
                  logout
                </span>
              </button>
            </div>
          </div>
        </header>

        {/* Content Body */}
        <main className="w-full pt-14 min-h-screen bg-surface px-space-xl py-space-lg">
          {children}
        </main>
      </div>
    </div>
  );
}
