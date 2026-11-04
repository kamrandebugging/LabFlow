import { create } from "zustand";
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
    const resolvedUser: AuthUser = user || {
      id: "8a86c9bb-73aa-4326-b6a1-1b06a9500771",
      email: "owner@labflow.app",
      name: "Lab Administrator",
      role: "owner",
      branch_ids: ["b13d89c6-3cd7-4ed2-a5f0-05dd62826610"],
    };
    set({
      accessToken: access,
      user: resolvedUser,
      isAuthenticated: true,
      requiresTotp: false,
      pendingEmail: null,
      error: null,
    });
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
