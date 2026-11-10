/**
 * Platform operator session store — memory only.
 *
 * Deliberately NOT persisted (no localStorage, no sessionStorage): a reload
 * re-establishes the session from the httpOnly refresh cookie. It also never
 * touches the staff auth store, so the staff `owner@labflow.app` development
 * fallback can never leak into a platform session.
 */

import { create } from "zustand";

import { refreshSession } from "../../lib/apiClient";
import { registerSession } from "../../lib/sessionBridge";
import {
  platformAuthService,
  type PlatformSessionPayload,
  type PlatformUserPayload,
} from "./platformAuthService";

/** One generic message: never reveal whether the account exists. */
const GENERIC_LOGIN_ERROR =
  "Sign-in failed. Check your email, password and authenticator code.";

type LoginResult = "totp" | "session" | "error";

interface PlatformAuthState {
  accessToken: string | null;
  platformUser: PlatformUserPayload | null;
  pendingEmail: string | null;
  pendingChallengeId: string | null;
  isLoading: boolean;
  error: string | null;
  isAuthenticated: boolean;
  login: (email: string, password: string) => Promise<{ kind: LoginResult }>;
  verifyTotp: (code: string) => Promise<boolean>;
  applySession: (session: PlatformSessionPayload) => void;
  restore: () => Promise<boolean>;
  logout: () => Promise<void>;
  clear: () => void;
}

export const usePlatformAuthStore = create<PlatformAuthState>((set, get) => ({
  accessToken: null,
  platformUser: null,
  pendingEmail: null,
  pendingChallengeId: null,
  isLoading: false,
  error: null,
  isAuthenticated: false,

  applySession: (session) =>
    set({
      accessToken: session.access,
      platformUser: session.user,
      isAuthenticated: true,
      pendingEmail: null,
      pendingChallengeId: null,
      error: null,
      isLoading: false,
    }),

  login: async (email, password) => {
    set({ isLoading: true, error: null });
    try {
      const payload = await platformAuthService.login(email, password);
      if (payload.totp_required || !payload.access || !payload.user) {
        set({
          pendingEmail: email,
          pendingChallengeId: payload.challenge_id ?? null,
          platformUser: null,
          accessToken: null,
          isAuthenticated: false,
          isLoading: false,
        });
        return { kind: "totp" };
      }
      get().applySession({
        access: payload.access,
        expires_in: payload.expires_in ?? 900,
        user: payload.user,
      });
      return { kind: "session" };
    } catch {
      set({
        error: GENERIC_LOGIN_ERROR,
        isLoading: false,
        isAuthenticated: false,
      });
      return { kind: "error" };
    }
  },

  verifyTotp: async (code) => {
    const { pendingEmail, pendingChallengeId } = get();
    if (!pendingEmail || !pendingChallengeId) {
      set({ error: GENERIC_LOGIN_ERROR });
      return false;
    }
    set({ isLoading: true, error: null });
    try {
      const session = await platformAuthService.verifyTotp(
        code,
        pendingEmail,
        pendingChallengeId,
      );
      get().applySession(session);
      return true;
    } catch {
      set({ error: GENERIC_LOGIN_ERROR, isLoading: false });
      return false;
    }
  },

  restore: async () => {
    if (get().isAuthenticated && get().accessToken) return true;
    // Use the shared single-flight refresh: concurrent restores (React
    // StrictMode double-effects, parallel 401 retries) must never present the
    // same rotating refresh token twice, which the server treats as reuse and
    // would revoke the operator's session.
    const token = await refreshSession("platform");
    return Boolean(token && get().isAuthenticated);
  },

  logout: async () => {
    try {
      await platformAuthService.logout();
    } catch {
      // The local session is cleared either way; the server cookie may already
      // be gone, and a failed logout must not strand the operator.
    }
    get().clear();
  },

  clear: () =>
    set({
      accessToken: null,
      platformUser: null,
      pendingEmail: null,
      pendingChallengeId: null,
      isAuthenticated: false,
      isLoading: false,
      error: null,
    }),
}));

// Let the shared api client refresh this session on a 401.
registerSession("platform", {
  getAccessToken: () => usePlatformAuthStore.getState().accessToken,
  refresh: async () => {
    try {
      const session = await platformAuthService.refresh();
      if (!session?.access || !session.user) return null;
      usePlatformAuthStore.getState().applySession(session);
      return session.access;
    } catch {
      return null;
    }
  },
  onExpired: () => usePlatformAuthStore.getState().clear(),
});
