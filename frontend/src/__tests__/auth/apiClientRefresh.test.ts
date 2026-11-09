import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { apiRequest, ApiError } from "@/lib/apiClient";
import { useAuthStore } from "@/features/auth/authStore";

describe("apiClient Silent Refresh Integration", () => {
  const origLocation = window.location;

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().clear();
    Object.defineProperty(window, "location", {
      value: {
        pathname: "/patients",
        search: "",
        href: "http://localhost/patients",
      },
      writable: true,
      configurable: true,
    });
  });

  afterEach(() => {
    Object.defineProperty(window, "location", {
      value: origLocation,
      writable: true,
      configurable: true,
    });
    vi.restoreAllMocks();
  });

  it("transparently refreshes on 401 and retries the original request", async () => {
    useAuthStore.getState().setSession("expired_token", {
      id: "owner-1",
      name: "Owner",
      role: "owner",
      branch_ids: ["br-1"],
    });

    let attempt = 0;
    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/v1/patients") {
        attempt++;
        if (attempt === 1) {
          // First attempt fails with 401
          return {
            ok: false,
            status: 401,
            json: async () => ({
              detail: "Given token not valid for any token type",
            }),
          };
        }
        // Second attempt with fresh token succeeds
        return {
          ok: true,
          status: 200,
          json: async () => [{ id: "pat-1", name: "Ahmed Khan" }],
        };
      }
      if (url === "/api/v1/auth/refresh") {
        return {
          ok: true,
          status: 200,
          json: async () => ({
            access: "fresh_rotated_jwt_token",
            expires_in: 900,
          }),
        };
      }
      return { ok: false, status: 404 };
    });

    const result = await apiRequest<Array<{ id: string; name: string }>>(
      "/patients",
      { session: "staff" },
    );

    expect(result).toEqual([{ id: "pat-1", name: "Ahmed Khan" }]);
    expect(attempt).toBe(2);
    expect(useAuthStore.getState().accessToken).toBe("fresh_rotated_jwt_token");
    // Refresh was called exactly once with credentials: include
    expect(global.fetch).toHaveBeenCalledWith("/api/v1/auth/refresh", {
      method: "POST",
      credentials: "include",
    });
  });

  it("clears session and redirects to /login?reason=session_expired when refresh fails", async () => {
    useAuthStore.getState().setSession("expired_token", {
      id: "owner-1",
      name: "Owner",
      role: "owner",
      branch_ids: ["br-1"],
    });

    global.fetch = vi.fn().mockImplementation(async (url: string) => {
      if (url === "/api/v1/patients") {
        return {
          ok: false,
          status: 401,
          json: async () => ({ detail: "Token expired" }),
        };
      }
      if (url === "/api/v1/auth/refresh") {
        return {
          ok: false,
          status: 401,
          json: async () => ({ error: { code: "invalid_refresh_token" } }),
        };
      }
      return { ok: false, status: 404 };
    });

    await expect(
      apiRequest("/patients", { session: "staff" }),
    ).rejects.toThrow(ApiError);

    expect(useAuthStore.getState().accessToken).toBeNull();
    expect(useAuthStore.getState().isAuthenticated).toBe(false);
    expect(window.location.href).toBe("/login?reason=session_expired");
  });
});
