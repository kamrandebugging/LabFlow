/**
 * Platform operator auth transport.
 *
 * These calls deliberately use raw fetch rather than the shared api client:
 * they establish the session, so there is no bearer token to attach and no
 * refresh to retry with. Tokens live in memory only.
 */

const BASE = "/api/v1/platform/auth";

export interface PlatformUserPayload {
  id: string;
  email: string;
  role: string;
  totp_enabled: boolean;
}

export interface PlatformSessionPayload {
  access: string;
  expires_in: number;
  user: PlatformUserPayload;
}

export interface LoginPayload {
  totp_required?: boolean;
  challenge_id?: string;
  access?: string;
  expires_in?: number;
  user?: PlatformUserPayload;
}

export interface ProblemPayload {
  detail?: string;
  title?: string;
  code?: string;
}

async function post<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${BASE}${path}`, {
    method: "POST",
    credentials: "include",
    headers: {
      "Content-Type": "application/json",
      Accept: "application/json",
    },
    body: JSON.stringify(body ?? {}),
  });

  if (!response.ok) {
    let problem: ProblemPayload | null = null;
    try {
      problem = (await response.json()) as ProblemPayload;
    } catch {
      problem = null;
    }
    const error = new Error(
      problem?.detail || problem?.title || "Request failed.",
    ) as Error & { status?: number; code?: string };
    error.status = response.status;
    error.code = problem?.code;
    throw error;
  }

  return (await response.json()) as T;
}

export const platformAuthService = {
  /** Step 1: password. Returns either totp_required or a full session. */
  login(email: string, password: string): Promise<LoginPayload> {
    return post<LoginPayload>("/login", { email, password });
  },

  /**
   * Step 2: TOTP (or a backup code) against the login challenge.
   * The challenge is single-use and expires, so both ids are required.
   */
  verifyTotp(
    code: string,
    email: string,
    challengeId: string,
  ): Promise<PlatformSessionPayload> {
    return post<PlatformSessionPayload>("/totp/verify", {
      email,
      challenge_id: challengeId,
      code,
    });
  },

  /** Start enrolment: returns the shared secret and otpauth URI once. */
  enrollTotp(): Promise<{ secret: string; otpauth_uri: string }> {
    return post<{ secret: string; otpauth_uri: string }>("/totp/enroll", {});
  },

  /** Confirm enrolment with a live code; returns single-use backup codes. */
  confirmEnrollment(code: string): Promise<string[]> {
    return post<{ backup_codes: string[] }>("/totp/enroll/confirm", { code }).then(
      (result) => result.backup_codes,
    );
  },

  /** Cookie-based refresh. Returns a new session, or throws when expired. */
  refresh(): Promise<PlatformSessionPayload> {
    return post<PlatformSessionPayload>("/refresh", {});
  },

  logout(): Promise<{ detail?: string }> {
    return post<{ detail?: string }>("/logout", {});
  },

  requestPasswordReset(email: string): Promise<{ detail?: string }> {
    return post<{ detail?: string }>("/password-reset/request", { email });
  },

  confirmPasswordReset(
    token: string,
    newPassword: string,
  ): Promise<{ detail?: string }> {
    return post<{ detail?: string }>("/password-reset/confirm", {
      token,
      new_password: newPassword,
    });
  },
};
