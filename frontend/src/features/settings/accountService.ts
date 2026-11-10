/**
 * Account Security API service (change password + two-factor management).
 *
 * Mirrors the tenant auth endpoints under /api/v1/auth:
 * - POST /api/v1/auth/password/change
 * - POST /api/v1/auth/totp/enroll
 * - POST /api/v1/auth/totp/enroll/confirm
 * - POST /api/v1/auth/totp/disable
 */

import { useAuthStore } from "../auth/authStore";

function getAuthHeaders(): Record<string, string> {
  const token = useAuthStore.getState().accessToken;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
  };
  if (token) {
    headers["Authorization"] = `Bearer ${token}`;
  }
  return headers;
}

export class AccountApiError extends Error {
  code: string;
  status: number;

  constructor(message: string, code = "account_error", status = 400) {
    super(message);
    this.name = "AccountApiError";
    this.code = code;
    this.status = status;
  }
}

async function handleResponse<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let code = "error";
    let message = `Server error (${res.status})`;
    try {
      const data = await res.json();
      if (data?.error && typeof data.error === "object") {
        code = data.error.code || code;
        message = data.error.message || message;
      } else if (data?.message) {
        message = data.message;
      } else if (data?.detail) {
        message = data.detail;
      }
    } catch {
      // Non-JSON response
    }
    throw new AccountApiError(message, code, res.status);
  }
  return res.json() as Promise<T>;
}

export const accountService = {
  async changePassword(
    currentPassword: string,
    newPassword: string,
  ): Promise<{ status: string; message: string }> {
    const res = await fetch("/api/v1/auth/password/change", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({
        current_password: currentPassword,
        new_password: newPassword,
      }),
    });
    return handleResponse<{ status: string; message: string }>(res);
  },

  async startTotpEnroll(): Promise<{ secret: string; otpauth_uri: string }> {
    const res = await fetch("/api/v1/auth/totp/enroll", {
      method: "POST",
      headers: getAuthHeaders(),
    });
    return handleResponse<{ secret: string; otpauth_uri: string }>(res);
  },

  async confirmTotpEnroll(code: string): Promise<{ backup_codes: string[] }> {
    const res = await fetch("/api/v1/auth/totp/enroll/confirm", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ code: code.trim() }),
    });
    return handleResponse<{ backup_codes: string[] }>(res);
  },

  async disableTotp(
    currentPassword: string,
  ): Promise<{ status: string; message: string }> {
    const res = await fetch("/api/v1/auth/totp/disable", {
      method: "POST",
      headers: getAuthHeaders(),
      body: JSON.stringify({ current_password: currentPassword }),
    });
    return handleResponse<{ status: string; message: string }>(res);
  },
};
