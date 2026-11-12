import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import { billingService } from "../../features/billing/billingService";
import { ReceptionistDashboardScreen } from "../../features/dashboard/ReceptionistDashboardScreen";
import { patientService } from "../../features/patients/patientService";
import { sampleService } from "../../features/samples/sampleService";
import type { InvoiceSummary } from "../../features/billing/types";

vi.mock("../../features/patients/patientService", () => ({
  patientService: { listPatients: vi.fn() },
}));
vi.mock("../../features/billing/billingService", () => ({
  billingService: { listInvoices: vi.fn() },
}));
vi.mock("../../features/samples/sampleService", () => ({
  sampleService: { listSamples: vi.fn() },
}));

const reception = {
  id: "reception-1",
  email: "reception@lab.pk",
  display_name: "Bilal Ahmed",
  role: "reception" as const,
  branch_ids: ["b1"],
};

const unpaid: InvoiceSummary = {
  id: "inv-1",
  patient_id: "p1",
  patient_name: "Sana Bibi",
  patient_mrn: "MRN-1",
  branch_id: "b1",
  branch_name: "Main Branch",
  status: "unpaid",
  subtotal: "1000.00",
  discount_amount: "0.00",
  total: "1000.00",
  net_paid: "0.00",
  created_at: new Date().toISOString(),
};

const partial: InvoiceSummary = {
  ...unpaid,
  id: "inv-2",
  patient_id: "p2",
  patient_name: "Usman Ali",
  patient_mrn: "MRN-2",
  status: "partial",
  total: "1000.00",
  net_paid: "200.00",
};

describe("Receptionist dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", reception);
    vi.mocked(patientService.listPatients).mockResolvedValue([
      {
        id: "p1",
        mrn: "MRN-1",
        name: "Ali Raza",
        sex: "M",
        branch_id: "b1",
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        is_cross_branch: false,
      },
    ]);
    vi.mocked(billingService.listInvoices).mockImplementation(
      async ({ status } = {}) => {
        if (status === "unpaid") {
          return { results: [unpaid], next_cursor: null };
        }
        if (status === "partial") {
          return { results: [partial], next_cursor: null };
        }
        return { results: [unpaid, partial], next_cursor: null };
      },
    );
    vi.mocked(sampleService.listSamples).mockResolvedValue({
      results: [
        {
          id: "s1",
          accession_id: "ACC-1",
          invoice_id: "inv-1",
          patient_id: "p1",
          patient_name: "Ali Raza",
          patient_mrn: "MRN-1",
          branch_id: "b1",
          branch_name: "Main Branch",
          status: "collected",
          tests: ["CBC"],
          collected_at: new Date().toISOString(),
        },
        {
          id: "s2",
          accession_id: "ACC-2",
          invoice_id: "inv-2",
          patient_id: "p2",
          patient_name: "Usman Ali",
          patient_mrn: "MRN-2",
          branch_id: "b1",
          branch_name: "Main Branch",
          status: "collected",
          tests: ["LFT"],
          collected_at: new Date().toISOString(),
        },
      ],
      total: 2,
    });
  });

  it("renders today's registrations, unpaid invoices and collected samples", async () => {
    render(
      <MemoryRouter>
        <ReceptionistDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Front desk" }),
    ).toBeInTheDocument();

    expect(
      within(await screen.findByTestId("stat-registrations-today")).getByText(
        "1",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-unpaid-invoices")).getByText("2"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-unpaid-invoices")).getByText(
        /PKR 1800\.00/,
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-receipt")).getByText("2"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-collection")).getByText("—"),
    ).toBeInTheDocument();

    expect(screen.getAllByText("Ali Raza").length).toBeGreaterThan(0);
    expect(screen.getByText("Sana Bibi")).toBeInTheDocument();
    expect(screen.getAllByText("Usman Ali").length).toBeGreaterThan(0);
  });

  it("shows unavailable invoice and sample states instead of zero", async () => {
    vi.mocked(billingService.listInvoices).mockRejectedValue(
      new Error("offline"),
    );
    vi.mocked(sampleService.listSamples).mockRejectedValue(
      new Error("offline"),
    );

    render(
      <MemoryRouter>
        <ReceptionistDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Unavailable — the invoice API did not respond."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-unpaid-invoices")).getByText("—"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-receipt")).getByText("—"),
    ).toBeInTheDocument();
  });

  it("does not expose approvals or the technician worklist", async () => {
    render(
      <MemoryRouter>
        <ReceptionistDashboardScreen />
      </MemoryRouter>,
    );

    await screen.findByTestId("stat-unpaid-invoices");

    expect(
      screen.queryByRole("link", { name: /approvals/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/^worklist$/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).not.toBeInTheDocument();
  });
});
