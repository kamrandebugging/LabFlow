import { create } from "zustand";
import { registerSession } from "../../lib/sessionBridge";
import type {
  AuthStoreState,
  AuthUser,
  LoginCredentials,
  LoginResult,
  TotpVerifyPayload,
} from "./types";
import { defaultAuthService } from "./authService";

/**
 * LabFlow In-Memory Auth Store per Doc 07 §5.2.
 *
 * CRITICAL SECURITY GUARANTEES:
 * 1. The access token lives strictly in memory in this Zustand store.
 * 2. NO persistence middleware is ever applied.
 * 3. Never writes to localStorage, sessionStorage, or client-accessible cookies.
 * 4. Generic error message ("Email, password or code is not correct") per Doc 07 §5.1.
 */
export const GENERIC_AUTH_ERROR = "Email, password or code is not correct";

export const useAuthStore = create<AuthStoreState>((set) => ({
  accessToken: null,
  user: null,
  isAuthenticated: false,
  requiresTotp: false,
  pendingEmail: null,
  error: null,
  isLoading: false,

  setSession: (access: string, user?: AuthUser | null) => {
    set((state) => ({
      accessToken: access,
      user: user !== undefined ? user : state.user,
      isAuthenticated: true,
      requiresTotp: false,
      pendingEmail: null,
      error: null,
    }));
  },

  clear: () => {
    set({
      accessToken: null,
      user: null,
      isAuthenticated: false,
      requiresTotp: false,
      pendingEmail: null,
      error: null,
      isLoading: false,
    });
  },

  setTotpRequired: (email: string) => {
    set({
      requiresTotp: true,
      pendingEmail: email,
      isAuthenticated: false,
      accessToken: null,
      user: null,
      error: null,
    });
  },

  setError: (error: string | null) => {
    set({ error });
  },

  setLoading: (isLoading: boolean) => {
    set({ isLoading });
  },

  login: async (
    credentials: LoginCredentials,
    service = defaultAuthService,
  ): Promise<LoginResult> => {
    set({ isLoading: true, error: null });
    try {
      const result = await service.login(credentials);
      if (result.totpRequired) {
        set({
          requiresTotp: true,
          pendingEmail: credentials.email,
          isAuthenticated: false,
          accessToken: null,
          user: null,
          isLoading: false,
        });
        return result;
      }

      if (result.session) {
        set({
          accessToken: result.session.access,
          user: result.session.user,
          isAuthenticated: true,
          requiresTotp: false,
          pendingEmail: null,
          isLoading: false,
        });
        return result;
      }

      set({ isLoading: false });
      return result;
    } catch (err: unknown) {
      set({
        error: GENERIC_AUTH_ERROR,
        isAuthenticated: false,
        accessToken: null,
        user: null,
        isLoading: false,
      });
      throw err;
    }
  },

  verifyTotp: async (
    payload: TotpVerifyPayload,
    service = defaultAuthService,
  ): Promise<void> => {
    set({ isLoading: true, error: null });
    try {
      const session = await service.verifyTotp(payload);
      set({
        accessToken: session.access,
        user: session.user,
        isAuthenticated: true,
        requiresTotp: false,
        pendingEmail: null,
        isLoading: false,
      });
    } catch (err: unknown) {
      set({
        error: GENERIC_AUTH_ERROR,
        isAuthenticated: false,
        accessToken: null,
        isLoading: false,
      });
      throw err;
    }
  },

  logout: async (service = defaultAuthService): Promise<void> => {
    set({ isLoading: true });
    try {
      await service.logout();
    } catch {
      // Per Doc 07 §5.2: even if server logout fails, clear client memory
    } finally {
      set({
        accessToken: null,
        user: null,
        isAuthenticated: false,
        requiresTotp: false,
        pendingEmail: null,
        error: null,
        isLoading: false,
      });
    }
  },
}));

// Register the staff session binding for automatic silent refresh on 401
registerSession("staff", {
  getAccessToken: () => useAuthStore.getState().accessToken,
  refresh: async () => {
    try {
      const response = await fetch("/api/v1/auth/refresh", {
        method: "POST",
        credentials: "include",
      });
      if (!response.ok) {
        return null;
      }
      const data = await response.json();
      if (!data?.access) {
        return null;
      }
      useAuthStore.getState().setSession(data.access, data.user ?? undefined);
      return data.access;
    } catch {
      return null;
    }
  },
  onExpired: () => {
    useAuthStore.getState().clear();
    if (typeof window === "undefined") return;
    const { pathname, search } = window.location;

    // Public and apex routes must not be hijacked by a missing *tenant*
    // session. Opening /platform/login on the apex host (or a report-access
    // link) legitimately has no staff refresh cookie; redirecting here would
    // bounce the operator to the tenant staff login.
    if (pathname.startsWith("/login")) {
      if (!search.includes("reason=session_expired")) {
        window.location.href = "/login?reason=session_expired";
      }
      return;
    }
    if (
      pathname.startsWith("/platform") ||
      pathname.startsWith("/report-access") ||
      pathname.startsWith("/link-expired")
    ) {
      return;
    }
    window.location.href = "/login?reason=session_expired";
  },
});
