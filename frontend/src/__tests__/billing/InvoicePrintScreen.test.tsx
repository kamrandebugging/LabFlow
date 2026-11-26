import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { InvoicePrintScreen } from "../../features/billing/InvoicePrintScreen";
import type { InvoiceDetail } from "../../features/billing/types";
import { useAuthStore } from "../../features/auth/authStore";
import { settingsService } from "../../features/settings/settingsService";

vi.mock("../../features/settings/settingsService", () => ({
  settingsService: {
    getSettings: vi.fn(),
    getBranches: vi.fn(),
  },
}));

vi.mock("../../features/auth/tenantContext", () => ({
  fetchTenantContext: vi.fn().mockResolvedValue(null),
}));

const mockInvoice: InvoiceDetail = {
  id: "89521878-1111-4444-8888-abcdef123456",
  invoice_number: "INV-89521878",
  patient_id: "pat-001",
  patient_name: "Amina Bibi",
  patient_mrn: "MRN-2026-00012",
  branch_id: "br-01",
  branch_name: "SamplesLab Main",
  status: "paid",
  subtotal: "1500.00",
  discount_amount: "0.00",
  discount_reason: null,
  total: "1500.00",
  net_paid: "1500.00",
  net_revenue: "1500.00",
  balance: "0.00",
  pickup_code: "482910",
  created_at: "2026-11-25T09:30:00Z",
  items: [
    {
      id: "item-1",
      test_id: "test-1",
      panel_id: null,
      description: "Complete Blood Count",
      unit_price: "1500.00",
      quantity: 1,
      line_total: "1500.00",
    },
  ],
  payments: [],
};

describe("Screen 15: InvoicePrintScreen", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      accessToken: "test-token",
      user: {
        id: "user-1",
        email: "rec@sampleslab.test",
        name: "Reception",
        role: "reception",
        branch_ids: ["br-01"],
        totp_enabled: true,
      },
    });
    vi.mocked(settingsService.getSettings).mockResolvedValue({
      brand_display_name: {
        value: "SamplesLab Diagnostics",
        default: "",
        type: "string",
        description: "",
      },
      brand_logo_url: {
        value: "https://cdn.sampleslab.test/logo.png",
        default: "",
        type: "string",
        description: "",
      },
    });
    vi.mocked(settingsService.getBranches).mockResolvedValue([
      {
        id: "br-01",
        code: "MN",
        name: "SamplesLab Main",
        address: "14 Jail Road, Lahore",
        phone: "042-35761234",
        is_collection_centre: false,
        result_entry_enabled: true,
        deleted_at: null,
      },
    ]);
  });

  it("renders tenant logo, branding, and suppresses Chrome headers without hardcoded phone", async () => {
    const mockBilling = {
      getInvoice: vi.fn().mockResolvedValue(mockInvoice),
    };

    const { container } = render(
      <MemoryRouter>
        <InvoicePrintScreen
          invoiceId={mockInvoice.id}
          // @ts-expect-error partial mock
          service={mockBilling}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("SamplesLab Diagnostics")).toBeInTheDocument();
      expect(screen.getByText("14 Jail Road, Lahore")).toBeInTheDocument();
      expect(screen.getByText("042-35761234")).toBeInTheDocument();
    });

    const logo = screen.getByRole("img", { name: "SamplesLab Diagnostics" });
    expect(logo).toHaveAttribute("src", "https://cdn.sampleslab.test/logo.png");

    expect(screen.queryByText(/0320-6744652/)).not.toBeInTheDocument();
    expect(screen.getByText("Software by LabFlow")).toBeInTheDocument();
    expect(
      screen.getByText(/In the print dialog: Margins/i),
    ).toBeInTheDocument();

    const styleEl = container.querySelector("style");
    expect(styleEl?.textContent).toContain(
      "@page { size: A5 portrait; margin: 0; }",
    );
  });

  it("renders prominent lab name, address, and phone when no logo is stored", async () => {
    vi.mocked(settingsService.getSettings).mockResolvedValue({
      brand_display_name: {
        value: "SamplesLab Diagnostics",
        default: "",
        type: "string",
        description: "",
      },
      brand_logo_url: {
        value: "",
        default: "",
        type: "string",
        description: "",
      },
    });
    const mockBilling = {
      getInvoice: vi.fn().mockResolvedValue(mockInvoice),
    };

    render(
      <MemoryRouter>
        <InvoicePrintScreen
          invoiceId={mockInvoice.id}
          // @ts-expect-error partial mock
          service={mockBilling}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("SamplesLab Diagnostics")).toBeInTheDocument();
      expect(screen.getByText("14 Jail Road, Lahore")).toBeInTheDocument();
      expect(screen.getByText("042-35761234")).toBeInTheDocument();
    });
    expect(
      screen.queryByRole("img", { name: "SamplesLab Diagnostics" }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/0320-6744652/)).not.toBeInTheDocument();
  });
});
