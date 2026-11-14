import { beforeEach, describe, expect, it, vi } from "vitest";
import { render, screen } from "@testing-library/react";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { MemoryRouter, Route, Routes } from "react-router-dom";

import { LabDetailScreen } from "../../features/platform/LabDetailScreen";
import { platformService } from "../../features/platform/platformService";
import type { TenantDetail } from "../../features/platform/types";

vi.mock("../../features/platform/platformService", () => ({
  platformService: {
    getTenant: vi.fn(),
    suspendTenant: vi.fn(),
    reactivateTenant: vi.fn(),
    retryProvisioning: vi.fn(),
  },
}));

const tenant = {
  id: "tenant-lahore-21",
  slug: "lahore21",
  name: "Lahore 21 Diagnostics",
  status: "active",
  created_at: "2026-11-01T00:00:00Z",
  updated_at: "2026-11-01T00:00:00Z",
  schema_name: "tenant_lahore21",
  domains: [{ domain: "lahore21.localhost", is_primary: true }],
  subscription: null,
  plan: null,
  branches_used: 1,
  branches_limit: 3,
  staff_count: 2,
  schema_size_bytes: 1024,
  migration_state: {
    schema_exists: true,
    applied_migrations: 1,
    pending_migrations: 0,
    in_sync: true,
    latest_applied: null,
  },
  provisioning: {
    current_step: null,
    completed_steps: [],
    failed_step: null,
    error: null,
    owner_email: "owner@lahore21.localhost",
    last_action: null,
    last_action_at: null,
  },
} as TenantDetail;

describe("Platform Launch Console", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(platformService.getTenant).mockResolvedValue(tenant);
  });

  it("links to the tenant login page, not the tenant root", async () => {
    render(
      <QueryClientProvider client={new QueryClient()}>
        <MemoryRouter initialEntries={["/platform/tenants/tenant-lahore-21"]}>
          <Routes>
            <Route path="/platform/tenants/:id" element={<LabDetailScreen />} />
          </Routes>
        </MemoryRouter>
      </QueryClientProvider>,
    );

    const label = await screen.findByText("Launch Console");
    const link = label.closest("a");
    expect(link).toHaveAttribute("href", "http://lahore21.localhost/login");
  });
});
