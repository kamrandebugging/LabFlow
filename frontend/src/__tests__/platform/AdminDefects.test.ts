import { afterEach, describe, expect, it, vi } from "vitest";

import { tenantDomain } from "../../features/platform/domain";
import { platformService } from "../../features/platform/platformService";

function installFetch(
  handler: (url: string) => { status?: number; body: unknown },
): void {
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string) => {
      const result = handler(url);
      const status = result.status ?? 200;
      return {
        ok: status >= 200 && status < 300,
        status,
        json: async () => result.body,
        headers: new Headers(),
      } as unknown as Response;
    }),
  );
}

afterEach(() => {
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe("D1 — subscription detail uses the real nested API shape", () => {
  it("reads tenant and plan from the flat detail payload and loads plans", async () => {
    installFetch((url) => {
      if (url.includes("/platform/plans")) {
        return {
          body: {
            plans: [
              {
                id: "plan-1",
                name: "Growth",
                price: "5999.00",
                max_branches: 3,
                max_staff: 10,
                is_active: true,
              },
            ],
          },
        };
      }
      return {
        body: {
          id: "sub-1",
          tenant: {
            id: "t-1",
            name: "Nazeer Diagnostic Hub",
            slug: "nazeerhub",
            city: "Lahore",
            province: "Punjab",
            owner_name: "Dr. Nazeer",
            owner_email: "owner@nazeerhub.pk",
            owner_phone: "+92 300 1234567",
            status: "active",
          },
          plan: { id: "plan-1", name: "Growth", price: "5999.00" },
          billing_cycle: "monthly",
          status: "active",
          starts_at: "2026-01-01T00:00:00Z",
          ends_at: null,
          next_due: "2026-12-01T00:00:00Z",
          payments: [
            {
              id: "pay-1",
              amount: "5999.00",
              method: "Bank Transfer",
              reference: "RAAST-1",
              notes: "",
              paid_date: "2026-11-01",
              recorded_by_email: "admin@labflow.app",
              created_at: "2026-11-01T10:00:00Z",
            },
          ],
        },
      };
    });

    const detail = await platformService.getSubscription("sub-1");

    expect(detail.tenant.name).toBe("Nazeer Diagnostic Hub");
    expect(detail.tenant.slug).toBe("nazeerhub");
    expect(detail.plan.name).toBe("Growth");
    expect(detail.plan.price).toBe("5999.00");
    expect(detail.payments[0]?.recorded_by_email).toBe("admin@labflow.app");
    expect(detail.available_plans).toHaveLength(1);
  });
});

describe("D2 — audit requests only send contract-defined filters", () => {
  it("getTenantAudit never sends limit", async () => {
    installFetch(() => ({ body: { audit: [], audits: [] } }));

    await platformService.getTenantAudit("tenant-1");

    const calls = (fetch as ReturnType<typeof vi.fn>).mock.calls;
    const url = String(calls[0]?.[0]);
    expect(url).toContain("entity_type=tenant");
    expect(url).toContain("tenant_id=tenant-1");
    expect(url).not.toContain("limit");
  });

  it("getAuditLog never sends limit", async () => {
    installFetch(() => ({ body: { audit: [], audits: [] } }));

    await platformService.getAuditLog({ action: "tenant.created" });

    const url = String((fetch as ReturnType<typeof vi.fn>).mock.calls[0]?.[0]);
    expect(url).toContain("action=tenant.created");
    expect(url).not.toContain("limit");
  });
});

describe("D4 — subscription summary reads the real field names", () => {
  it("maps mrr and overdue_amount from the API summary", async () => {
    installFetch(() => ({
      body: {
        subscriptions: [
          {
            id: "sub-1",
            tenant: { id: "t1", name: "Lab", slug: "lab", city: "" },
            plan: { id: "p1", name: "Growth", price: "5999.00" },
            billing_cycle: "monthly",
            amount: "5999.00",
            status: "active",
            starts_at: "2026-01-01T00:00:00Z",
            ends_at: null,
            next_due: null,
            last_payment: null,
          },
        ],
        summary: {
          mrr: "225991.00",
          overdue_count: 2,
          overdue_amount: "11998.00",
          lifetime_sold_count: 1,
          lifetime_revenue: "9999.00",
          founding_slots_used: 3,
          founding_slots_total: 10,
        },
      },
    }));

    const res = await platformService.listSubscriptions();

    expect(res.summary.mrr).toBe("225991.00");
    expect(res.summary.overdue_amount).toBe("11998.00");
    expect(res.subscriptions[0]?.tenant.name).toBe("Lab");
    expect(res.subscriptions[0]?.last_payment).toBeNull();
  });
});

describe("D5 — tenant domain resolution", () => {
  it("prefers the API-supplied domain", () => {
    expect(tenantDomain("nazeerhub", "nazeerhub.example.pk")).toBe(
      "nazeerhub.example.pk",
    );
  });

  it("falls back to the configured platform base domain only", () => {
    vi.stubEnv("VITE_PLATFORM_BASE_DOMAIN", "lab.local");
    expect(tenantDomain("nazeerhub", null)).toBe("nazeerhub.lab.local");
  });

  it("returns null when neither source is configured", () => {
    vi.stubEnv("VITE_PLATFORM_BASE_DOMAIN", "");
    expect(tenantDomain("nazeerhub", null)).toBeNull();
  });
});
