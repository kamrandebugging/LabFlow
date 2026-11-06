/**
 * Session bridge — lets the shared fetch wrapper read and refresh tokens
 * without importing either auth store (which would create an import cycle:
 * store -> service -> wrapper -> store).
 *
 * Each auth store registers its own binding on module init.
 */

export type SessionKind = "staff" | "platform";

export interface SessionBinding {
  /** Current in-memory access token, or null when signed out. */
  getAccessToken(): string | null;
  /** Attempt one refresh. Resolves the new access token, or null. */
  refresh(): Promise<string | null>;
  /** Called once when a refresh fails: the store clears itself. */
  onExpired(): void;
}

const bindings: Record<SessionKind, SessionBinding | null> = {
  staff: null,
  platform: null,
};

export function registerSession(
  kind: SessionKind,
  binding: SessionBinding,
): void {
  bindings[kind] = binding;
}

export function getSession(kind: SessionKind): SessionBinding | null {
  return bindings[kind];
}
