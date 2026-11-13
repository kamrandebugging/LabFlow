import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { ProvisionScreen } from "../../features/platform/ProvisionScreen";
import { platformService } from "../../features/platform/platformService";

vi.mock("../../features/platform/platformService", () => ({
  platformService: {
    listPlans: vi.fn(),
    provisionTenant: vi.fn(),
  },
}));

function renderScreen() {
  const client = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter>
        <ProvisionScreen />
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("ProvisionScreen one-time credential", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    Element.prototype.scrollIntoView = vi.fn();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
    vi.mocked(platformService.listPlans).mockResolvedValue({
      plans: [
        {
          id: "plan-growth",
          name: "Growth",
          price: "5000.00",
          max_branches: 5,
          max_staff: 20,
          is_active: true,
        },
      ],
    });
    vi.mocked(platformService.provisionTenant).mockResolvedValue({
      id: "tenant-1",
      slug: "muselab1",
      name: "Muse Lab",
      schema_name: "tenant_muselab1",
      status: "provisioning",
      domain: "muselab1.localhost",
      plan_id: "plan-growth",
      subscription_id: "sub-1",
      owner_email: "owner@muselab.pk",
      owner_name: "Dr Muse",
      temp_password: "LBF-TEST-24#",
      created_at: "2026-11-13T00:00:00Z",
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("reveals the server-issued credential and scrolls it into view", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.type(
      screen.getByPlaceholderText("e.g. Al-Razi Diagnostic Centre Lahore"),
      "Muse Lab",
    );
    await user.type(
      screen.getByPlaceholderText("e.g. Dr. Salman Tariq"),
      "Dr Muse",
    );
    await user.type(
      screen.getByPlaceholderText("owner@lab.pk"),
      "owner@muselab.pk",
    );

    await user.click(
      screen.getByRole("button", { name: /create lab & grant access/i }),
    );

    expect(await screen.findByText("LBF-TEST-24#")).toBeInTheDocument();
    expect(Element.prototype.scrollIntoView).toHaveBeenCalled();
  });

  it("copies the credential when the credential value is clicked", async () => {
    const user = userEvent.setup();
    const writeText = vi.spyOn(navigator.clipboard, "writeText");
    renderScreen();

    await user.type(
      screen.getByPlaceholderText("e.g. Al-Razi Diagnostic Centre Lahore"),
      "Muse Lab",
    );
    await user.type(
      screen.getByPlaceholderText("e.g. Dr. Salman Tariq"),
      "Dr Muse",
    );
    await user.type(
      screen.getByPlaceholderText("owner@lab.pk"),
      "owner@muselab.pk",
    );
    await user.click(
      screen.getByRole("button", { name: /create lab & grant access/i }),
    );

    const credential = await screen.findByRole("button", {
      name: /copy one-time temporary credential/i,
    });
    await user.click(credential);

    expect(writeText).toHaveBeenCalledWith("LBF-TEST-24#");
    expect(await screen.findByText("Copied")).toBeInTheDocument();
  });
});
