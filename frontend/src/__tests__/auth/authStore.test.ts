/**
 * Unit & Security tests for LabFlow Auth Store
 * Specification: Doc 07 §5.2 (Where the token lives), Doc 08 §4.4
 *
 * CRITICAL SECURITY GUARANTEES:
 * 1. The access token lives strictly in memory (Zustand).
 * 2. Tokens are NEVER persisted to localStorage, sessionStorage, or browser cookies.
 * 3. Auth store exposes: accessToken, user, isAuthenticated, requiresTotp, login, verifyTotp, logout, clear.
 */
import { describe, it, expect, beforeEach, vi, afterEach } from "vitest";
import { useAuthStore } from "@/features/auth/authStore";
import type {
  AuthService,
  AuthUser,
  LoginCredentials,
  TotpVerifyPayload,
} from "@/features/auth/types";

describe("LabFlow AuthStore (Doc 07 §5.2)", () => {
  const mockUser: AuthUser = {
    id: "usr_1001",
    name: "Dr. Ali Raza",
    role: "pathologist",
    branch_ids: ["br_lahore_01"],
  };

  const mockService: AuthService = {
    login: vi.fn(),
    verifyTotp: vi.fn(),
    logout: vi.fn(),
  };

  beforeEach(() => {
    // Reset store state before every test
    useAuthStore.getState().clear();
    vi.clearAllMocks();
    localStorage.clear();
    sessionStorage.clear();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  describe("Initial State", () => {
    it("initializes with no token, no user, and isAuthenticated=false", () => {
      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.requiresTotp).toBe(false);
      expect(state.pendingEmail).toBeNull();
      expect(state.error).toBeNull();
      expect(state.isLoading).toBe(false);
    });
  });

  describe("Security Guarantee: In-Memory Only (Doc 07 §5.2)", () => {
    it("NEVER writes access token to localStorage or sessionStorage during setSession", () => {
      const setItemLocalSpy = vi.spyOn(Storage.prototype, "setItem");
      const setItemSessionSpy = vi.spyOn(sessionStorage, "setItem");

      useAuthStore
        .getState()
        .setSession("jwt_mock_access_token_12345", mockUser);

      // Verify store has it in memory
      expect(useAuthStore.getState().accessToken).toBe(
        "jwt_mock_access_token_12345",
      );
      expect(useAuthStore.getState().isAuthenticated).toBe(true);

      // Verify persistent storage was NOT touched
      expect(localStorage.getItem("accessToken")).toBeNull();
      expect(localStorage.getItem("token")).toBeNull();
      expect(localStorage.getItem("auth")).toBeNull();
      expect(sessionStorage.getItem("accessToken")).toBeNull();
      expect(sessionStorage.getItem("token")).toBeNull();

      expect(setItemLocalSpy).not.toHaveBeenCalled();
      expect(setItemSessionSpy).not.toHaveBeenCalled();
    });

    it("NEVER writes access token to storage on successful login or totp verification", async () => {
      const setItemLocalSpy = vi.spyOn(Storage.prototype, "setItem");

      vi.mocked(mockService.login).mockResolvedValueOnce({
        totpRequired: false,
        session: {
          access: "jwt_token_direct_login",
          expires_in: 900,
          user: mockUser,
        },
      });

      const creds: LoginCredentials = {
        email: "ali.raza@citylab.pk",
        password: "ValidPassword123!",
      };

      await useAuthStore.getState().login(creds, mockService);

      expect(useAuthStore.getState().accessToken).toBe(
        "jwt_token_direct_login",
      );
      expect(localStorage.getItem("accessToken")).toBeNull();
      expect(setItemLocalSpy).not.toHaveBeenCalled();
    });
  });

  describe("Session Management", () => {
    it("setSession updates accessToken, user, and isAuthenticated", () => {
      useAuthStore.getState().setSession("token_abc_999", mockUser);

      const state = useAuthStore.getState();
      expect(state.accessToken).toBe("token_abc_999");
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.requiresTotp).toBe(false);
      expect(state.pendingEmail).toBeNull();
      expect(state.error).toBeNull();
    });

    it("clear wipes all session data from memory", () => {
      useAuthStore.getState().setSession("token_abc_999", mockUser);
      expect(useAuthStore.getState().isAuthenticated).toBe(true);

      useAuthStore.getState().clear();

      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.requiresTotp).toBe(false);
      expect(state.pendingEmail).toBeNull();
      expect(state.error).toBeNull();
    });
  });

  describe("Login Flow (Doc 07 §5.1, §5.2)", () => {
    it("handles login when TOTP is NOT required (direct session)", async () => {
      vi.mocked(mockService.login).mockResolvedValueOnce({
        totpRequired: false,
        session: {
          access: "direct_access_token",
          expires_in: 900,
          user: mockUser,
        },
      });

      const result = await useAuthStore
        .getState()
        .login(
          { email: "tech@citylab.pk", password: "Password123" },
          mockService,
        );

      expect(result.totpRequired).toBe(false);
      const state = useAuthStore.getState();
      expect(state.accessToken).toBe("direct_access_token");
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.requiresTotp).toBe(false);
      expect(state.error).toBeNull();
    });

    it("handles login when TOTP is required (step 2 challenge)", async () => {
      vi.mocked(mockService.login).mockResolvedValueOnce({
        totpRequired: true,
      });

      const result = await useAuthStore
        .getState()
        .login(
          { email: "ali.raza@citylab.pk", password: "Password123" },
          mockService,
        );

      expect(result.totpRequired).toBe(true);
      const state = useAuthStore.getState();
      // Access token must NOT be set yet because 2FA is pending
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.requiresTotp).toBe(true);
      expect(state.pendingEmail).toBe("ali.raza@citylab.pk");
      expect(state.error).toBeNull();
    });

    it("handles login failure with generic error message (Doc 07 §5.1)", async () => {
      vi.mocked(mockService.login).mockRejectedValueOnce(
        new Error("401 invalid_credentials"),
      );

      await expect(
        useAuthStore
          .getState()
          .login(
            { email: "unknown@citylab.pk", password: "WrongPassword" },
            mockService,
          ),
      ).rejects.toThrow();

      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.error).toBe("Email, password or code is not correct");
    });
  });

  describe("TOTP Verification Flow (Doc 07 §5.1)", () => {
    it("completes session on valid TOTP verification", async () => {
      useAuthStore.getState().setTotpRequired("ali.raza@citylab.pk");

      vi.mocked(mockService.verifyTotp).mockResolvedValueOnce({
        access: "verified_access_token_777",
        expires_in: 900,
        user: mockUser,
      });

      const payload: TotpVerifyPayload = { code: "841203" };
      await useAuthStore.getState().verifyTotp(payload, mockService);

      const state = useAuthStore.getState();
      expect(state.accessToken).toBe("verified_access_token_777");
      expect(state.user).toEqual(mockUser);
      expect(state.isAuthenticated).toBe(true);
      expect(state.requiresTotp).toBe(false);
      expect(state.pendingEmail).toBeNull();
      expect(state.error).toBeNull();
    });

    it("sets generic error message when TOTP verification fails", async () => {
      useAuthStore.getState().setTotpRequired("ali.raza@citylab.pk");

      vi.mocked(mockService.verifyTotp).mockRejectedValueOnce(
        new Error("401 invalid_code"),
      );

      const payload: TotpVerifyPayload = { code: "000000" };
      await expect(
        useAuthStore.getState().verifyTotp(payload, mockService),
      ).rejects.toThrow();

      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.isAuthenticated).toBe(false);
      expect(state.error).toBe("Email, password or code is not correct");
    });
  });

  describe("Logout Flow (Doc 07 §5.2)", () => {
    it("calls server logout and clears in-memory session", async () => {
      useAuthStore.getState().setSession("active_token", mockUser);
      expect(useAuthStore.getState().isAuthenticated).toBe(true);

      vi.mocked(mockService.logout).mockResolvedValueOnce();

      await useAuthStore.getState().logout(mockService);

      expect(mockService.logout).toHaveBeenCalledTimes(1);
      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });

    it("clears local store even if server logout call fails", async () => {
      useAuthStore.getState().setSession("active_token", mockUser);

      vi.mocked(mockService.logout).mockRejectedValueOnce(
        new Error("Network failure"),
      );

      await useAuthStore.getState().logout(mockService);

      const state = useAuthStore.getState();
      expect(state.accessToken).toBeNull();
      expect(state.user).toBeNull();
      expect(state.isAuthenticated).toBe(false);
    });
  });
});
