/**
 * Auth service for LabFlow API calls per Doc 07 §5 and Doc 08 §4.
 * Endpoints:
 * - POST /api/v1/auth/login
 * - POST /api/v1/auth/totp/verify
 * - POST /api/v1/auth/logout
 */
import type {
  AuthService,
  LoginCredentials,
  LoginResult,
  LoginSuccessSession,
  TotpVerifyPayload,
} from "./types";

const API_BASE_URL = "/api/v1";

export const defaultAuthService: AuthService = {
  async login(credentials: LoginCredentials): Promise<LoginResult> {
    const response = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include", // sends/receives httpOnly refresh / challenge cookies
      body: JSON.stringify(credentials),
    });

    if (!response.ok) {
      throw new Error("401 invalid_credentials");
    }

    const data = await response.json();
    if (data.totp_required) {
      return {
        totpRequired: true,
      };
    }

    return {
      totpRequired: false,
      session: {
        access: data.access,
        expires_in: data.expires_in,
        user: data.user,
      },
    };
  },

  async verifyTotp(payload: TotpVerifyPayload): Promise<LoginSuccessSession> {
    const response = await fetch(`${API_BASE_URL}/auth/totp/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        code: payload.code,
        is_backup_code: payload.isBackupCode ?? false,
      }),
    });

    if (!response.ok) {
      throw new Error("401 invalid_code");
    }

    const data = await response.json();
    return {
      access: data.access,
      expires_in: data.expires_in,
      user: data.user,
    };
  },

  async logout(): Promise<void> {
    await fetch(`${API_BASE_URL}/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
  },
};
