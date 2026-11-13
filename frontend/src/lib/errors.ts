/**
 * Error catalogue — the only path from an API error to user-facing text.
 *
 * The API's machine-stable `code` selects an i18n key (Doc 07 §7.4/§9.1).
 * Server `detail` is a developer aid and is NEVER shown to a user verbatim,
 * in either language. Every code the backend can emit is listed in
 * errorCodes.json, and `npm run i18n:check` fails the build when a mapped key
 * is missing from either locale.
 */
import errorCodes from "./errorCodes.json";

export type ErrorTranslator = (
  key: string,
  options?: Record<string, unknown>,
) => string;

export const ERROR_CODE_KEYS: Readonly<Record<string, string>> =
  errorCodes as Record<string, string>;

/** Resolve a server code to an i18n key, or the generic fallback. */
export function errorKeyForCode(code: string | null | undefined): string {
  if (code && Object.prototype.hasOwnProperty.call(ERROR_CODE_KEYS, code)) {
    return ERROR_CODE_KEYS[code] as string;
  }
  return "errors.generic";
}

/** Resolve an HTTP status to an i18n key when no code is present. */
export function errorKeyForStatus(status: number): string {
  if (status === 401) return "errors.unauthorized";
  if (status === 403) return "errors.forbidden";
  if (status === 404) return "errors.not_found";
  if (status === 409 || status === 412) return "errors.conflict";
  if (status === 422 || status === 400) return "errors.validation";
  if (status === 429) return "errors.rate_limited";
  if (status >= 500) return "errors.server";
  return "errors.generic";
}

export interface TranslatableError {
  code?: string | null;
  status?: number;
}

/** Turn any thrown value into safe, translated user text. */
export function messageForError(error: unknown, t: ErrorTranslator): string {
  const candidate = error as TranslatableError | null;
  const key =
    candidate && typeof candidate === "object"
      ? candidate.code
        ? errorKeyForCode(candidate.code)
        : typeof candidate.status === "number"
          ? errorKeyForStatus(candidate.status)
          : "errors.generic"
      : "errors.generic";
  return t(key);
}
