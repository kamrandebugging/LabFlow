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

let currentChallengeToken: string | null = null;
let currentChallengeEmail: string | null = null;

export const defaultAuthService: AuthService = {
  async login(credentials: LoginCredentials): Promise<LoginResult> {
    currentChallengeToken = null;
    currentChallengeEmail = credentials.email.trim().toLowerCase();

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
      currentChallengeToken = data.challenge_token || null;
      return {
        totpRequired: true,
        challengeToken: data.challenge_token,
        email: currentChallengeEmail,
      };
    }

    return {
      totpRequired: false,
      totpEnrollmentRequired: Boolean(data.totp_enrollment_required),
      session: {
        access: data.access,
        expires_in: data.expires_in,
        user: data.user,
        totp_enrollment_required: Boolean(data.totp_enrollment_required),
      },
    };
  },

  async verifyTotp(payload: TotpVerifyPayload): Promise<LoginSuccessSession> {
    const payloadEmail = payload.email || currentChallengeEmail || undefined;
    const payloadChallenge =
      payload.challengeToken || currentChallengeToken || undefined;

    const response = await fetch(`${API_BASE_URL}/auth/totp/verify`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
      },
      credentials: "include",
      body: JSON.stringify({
        code: payload.code,
        is_backup_code: payload.isBackupCode ?? false,
        challenge_token: payloadChallenge,
        email: payloadEmail,
      }),
    });

    if (!response.ok) {
      let errorMsg = "Email, password or code is not correct";
      try {
        const errJson = await response.json();
        if (errJson?.error?.message) {
          errorMsg = errJson.error.message;
        }
      } catch {
        // Non-JSON response
      }
      throw new Error(errorMsg);
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
