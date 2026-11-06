import type { ReactElement } from "react";
import { Navigate, useLocation } from "react-router-dom";

import { usePlatformAuthStore } from "./platformAuthStore";

/**
 * Route gate for the platform surface.
 *
 * - unauthenticated -> /platform/login
 * - authenticated but TOTP not enrolled -> /platform/enroll, and enrolment is
 *   the only reachable screen
 * - enrolled -> /platform/enroll redirects to the overview
 *
 * This is a UX guard only; the server (two URLconfs + the totp_required write
 * gate) is the security control.
 */
export function PlatformGuard({
  children,
}: {
  children: ReactElement;
}): ReactElement {
  const isAuthenticated = usePlatformAuthStore(
    (state) => state.isAuthenticated,
  );
  const platformUser = usePlatformAuthStore((state) => state.platformUser);
  const location = useLocation();

  if (!isAuthenticated) {
    return (
      <Navigate
        to="/platform/login"
        replace
        state={{ from: location.pathname }}
      />
    );
  }

  const enrolled = platformUser?.totp_enabled === true;

  if (!enrolled && location.pathname !== "/platform/enroll") {
    return <Navigate to="/platform/enroll" replace />;
  }

  if (enrolled && location.pathname === "/platform/enroll") {
    return <Navigate to="/platform/overview" replace />;
  }

  return children;
}
