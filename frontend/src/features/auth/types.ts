/**
 * Auth types for LabFlow per Doc 07 §5 and Doc 08 §4.
 *
 * CRITICAL SECURITY GUARANTEE:
 * Access token lives strictly in memory (Zustand store).
 * NEVER persist to localStorage, sessionStorage, or browser cookies.
 */

export type UserRole =
  "owner" | "manager" | "pathologist" | "technician" | "receptionist" | "admin";

export interface AuthUser {
  id: string;
  name: string;
  email?: string;
  role: UserRole;
  branch_ids: string[];
  /** True while the account is still on the provisioning-issued temp password. */
  must_change_password?: boolean;
  /** True when two-factor authentication is enrolled for the account. */
  totp_enabled?: boolean;
}

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface LoginSuccessSession {
  access: string;
  expires_in: number;
  user: AuthUser;
  totp_enrollment_required?: boolean;
}

export interface LoginResult {
  totpRequired: boolean;
  totpEnrollmentRequired?: boolean;
  challengeToken?: string;
  email?: string;
  session?: LoginSuccessSession;
}

export interface TotpVerifyPayload {
  code: string;
  isBackupCode?: boolean;
  challengeToken?: string;
  email?: string;
}

export interface AuthService {
  login(credentials: LoginCredentials): Promise<LoginResult>;
  verifyTotp(payload: TotpVerifyPayload): Promise<LoginSuccessSession>;
  logout(): Promise<void>;
}

export interface AuthStoreState {
  accessToken: string | null;
  user: AuthUser | null;
  isAuthenticated: boolean;
  requiresTotp: boolean;
  pendingEmail: string | null;
  error: string | null;
  isLoading: boolean;
  setSession: (access: string, user?: AuthUser | null) => void;
  clear: () => void;
  setTotpRequired: (email: string) => void;
  setError: (error: string | null) => void;
  setLoading: (loading: boolean) => void;
  login: (
    credentials: LoginCredentials,
    service?: AuthService,
  ) => Promise<LoginResult>;
  verifyTotp: (
    payload: TotpVerifyPayload,
    service?: AuthService,
  ) => Promise<void>;
  logout: (service?: AuthService) => Promise<void>;
}
