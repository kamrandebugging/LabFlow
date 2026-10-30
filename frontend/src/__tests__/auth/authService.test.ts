/**
 * Unit & Integration tests for defaultAuthService
 * Specification: Doc 07 §5, Doc 08 §4.4
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { defaultAuthService } from "@/features/auth/authService";

describe("defaultAuthService (Doc 07 §5)", () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    global.fetch = originalFetch;
  });

  describe("login()", () => {
    it("returns session when totp_required is false", async () => {
      const mockResponse = {
        access: "jwt_token_123",
        expires_in: 900,
        user: {
          id: "u1",
          name: "Dr. Ali",
          role: "owner",
          branch_ids: ["b1"],
        },
      };

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => mockResponse,
      } as unknown as Response);

      const result = await defaultAuthService.login({
        email: "ali@citylab.pk",
        password: "ValidPassword123!",
      });

      expect(result.totpRequired).toBe(false);
      expect(result.session).toEqual(mockResponse);
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/v1/auth/login",
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          body: JSON.stringify({
            email: "ali@citylab.pk",
            password: "ValidPassword123!",
          }),
        }),
      );
    });

    it("returns totpRequired: true when response specifies totp_required", async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => ({ totp_required: true }),
      } as unknown as Response);

      const result = await defaultAuthService.login({
        email: "ali@citylab.pk",
        password: "ValidPassword123!",
      });

      expect(result.totpRequired).toBe(true);
      expect(result.session).toBeUndefined();
    });

    it("throws 401 invalid_credentials error when status is not ok", async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 401,
      } as unknown as Response);

      await expect(
        defaultAuthService.login({
          email: "unknown@citylab.pk",
          password: "Bad",
        }),
      ).rejects.toThrow("401 invalid_credentials");
    });
  });

  describe("verifyTotp()", () => {
    it("returns session on successful TOTP verification", async () => {
      const mockSession = {
        access: "verified_jwt_token",
        expires_in: 900,
        user: {
          id: "u1",
          name: "Dr. Ali",
          role: "owner",
          branch_ids: ["b1"],
        },
      };

      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
        json: async () => mockSession,
      } as unknown as Response);

      const result = await defaultAuthService.verifyTotp({
        code: "841203",
        isBackupCode: false,
      });

      expect(result).toEqual(mockSession);
      expect(global.fetch).toHaveBeenCalledWith(
        "/api/v1/auth/totp/verify",
        expect.objectContaining({
          method: "POST",
          credentials: "include",
          body: JSON.stringify({
            code: "841203",
            is_backup_code: false,
          }),
        }),
      );
    });

    it("throws 401 invalid_code error when verification fails", async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: false,
        status: 401,
      } as unknown as Response);

      await expect(
        defaultAuthService.verifyTotp({
          code: "000000",
        }),
      ).rejects.toThrow("401 invalid_code");
    });
  });

  describe("logout()", () => {
    it("calls POST /api/v1/auth/logout with credentials include", async () => {
      global.fetch = vi.fn().mockResolvedValueOnce({
        ok: true,
      } as unknown as Response);

      await defaultAuthService.logout();

      expect(global.fetch).toHaveBeenCalledWith(
        "/api/v1/auth/logout",
        expect.objectContaining({
          method: "POST",
          credentials: "include",
        }),
      );
    });
  });
});
