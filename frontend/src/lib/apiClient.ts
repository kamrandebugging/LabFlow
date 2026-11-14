/**
 * Shared API client — the single fetch wrapper for the app.
 *
 * Responsibilities:
 * - prefix every call with /api/v1
 * - attach the bearer token of the requested session family
 * - parse RFC 9457 Problem+JSON into a typed error
 * - on 401, refresh the session exactly once (single-flight) and retry once
 */

import { getSession, type SessionKind } from "./sessionBridge";
import { errorKeyForCode, errorKeyForStatus } from "./errors";

const API_PREFIX = "/api/v1";

export interface ProblemDetails {
  type?: string;
  title?: string;
  status?: number;
  detail?: string;
  code?: string;
  error?:
    | {
        code?: string;
        message?: string;
        [key: string]: unknown;
      }
    | string;
  errors?: Record<string, string[] | string>;
  required?: string;
  [key: string]: unknown;
}

export class ApiError extends Error {
  readonly status: number;
  readonly problem: ProblemDetails | null;
  readonly code: string | null;
  /** Safe i18n key for user-facing text; never the server's detail. */
  readonly i18nKey: string;

  constructor(
    status: number,
    problem: ProblemDetails | null,
    fallback: string,
  ) {
    const errObj =
      problem?.error && typeof problem.error === "object"
        ? (problem.error as { code?: string; message?: string })
        : null;
    const errStr = typeof problem?.error === "string" ? problem.error : null;

    const rawMsg =
      errObj?.message ||
      errStr ||
      problem?.detail ||
      problem?.title ||
      (problem?.code && typeof problem.code === "string"
        ? problem.code
        : null) ||
      (problem && typeof problem === "object"
        ? (Object.values(problem).find(
            (v) =>
              typeof v === "string" ||
              (Array.isArray(v) && typeof v[0] === "string"),
          ) as string | string[] | undefined)
        : null) ||
      fallback;
    const resolvedMsg = Array.isArray(rawMsg) ? rawMsg[0] : rawMsg;
    super(String(resolvedMsg || fallback));
    this.name = "ApiError";
    this.status = status;
    this.problem = problem;
    this.code = errObj?.code || problem?.code || errStr || null;
    this.i18nKey = this.code
      ? errorKeyForCode(this.code)
      : errorKeyForStatus(status);
  }
}

export interface RequestOptions {
  method?: "GET" | "POST" | "PATCH" | "PUT" | "DELETE";
  headers?: Record<string, string>;
  body?: unknown;
  query?: Record<string, string | number | boolean | null | undefined>;
  session?: SessionKind;
  signal?: AbortSignal;
  /** Skip the automatic refresh-and-retry (used by refresh calls themselves). */
  noRetry?: boolean;
}

const inFlightRefresh: Partial<Record<SessionKind, Promise<string | null>>> =
  {};

async function refreshOnce(kind: SessionKind): Promise<string | null> {
  const existing = inFlightRefresh[kind];
  if (existing) return existing;

  const binding = getSession(kind);
  if (!binding) return null;

  const pending = binding
    .refresh()
    .catch(() => null)
    .then((token) => {
      delete inFlightRefresh[kind];
      if (!token) binding.onExpired();
      return token;
    });

  inFlightRefresh[kind] = pending;
  return pending;
}

/**
 * Refresh a session through the same single-flight promise used by the 401
 * retry path, so concurrent callers (boot gate double-mount, parallel 401s)
 * never present the same rotating refresh token twice.
 */
export function refreshSession(
  kind: SessionKind = "staff",
): Promise<string | null> {
  return refreshOnce(kind);
}

function buildUrl(path: string, query?: RequestOptions["query"]): string {
  const url = path.startsWith("/api/") ? path : `${API_PREFIX}${path}`;
  if (!query) return url;

  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(query)) {
    if (value === undefined || value === null || value === "") continue;
    params.set(key, String(value));
  }
  const search = params.toString();
  return search ? `${url}?${search}` : url;
}

async function parseProblem(
  response: Response,
): Promise<ProblemDetails | null> {
  try {
    const data: unknown = await response.json();
    if (data && typeof data === "object") return data as ProblemDetails;
    return null;
  } catch {
    return null;
  }
}

export async function apiRequest<T>(
  path: string,
  options: RequestOptions = {},
): Promise<T> {
  const {
    method = "GET",
    body,
    query,
    session = "staff",
    signal,
    noRetry,
  } = options;

  const send = async (token: string | null): Promise<Response> => {
    const headers: Record<string, string> = {
      Accept: "application/json",
      ...(options.headers || {}),
    };
    if (body !== undefined) headers["Content-Type"] = "application/json";
    if (token) headers.Authorization = `Bearer ${token}`;

    return fetch(buildUrl(path, query), {
      method,
      headers,
      credentials: "include",
      signal,
      ...(body === undefined ? {} : { body: JSON.stringify(body) }),
    });
  };

  const binding = session ? getSession(session) : null;
  let response = await send(binding?.getAccessToken() ?? null);

  if (response.status === 401 && session && binding && !noRetry) {
    const fresh = await refreshOnce(session);
    if (fresh) {
      response = await send(fresh);
    }
  }

  if (response.status === 204) {
    return undefined as T;
  }

  if (!response.ok) {
    const problem = await parseProblem(response);
    const fallback =
      response.status >= 500
        ? `Server error (${response.status})`
        : `Request failed with status ${response.status}.`;
    throw new ApiError(response.status, problem, fallback);
  }

  return (await response.json()) as T;
}
