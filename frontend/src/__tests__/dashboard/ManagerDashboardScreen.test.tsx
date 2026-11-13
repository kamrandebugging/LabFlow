import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import { ManagerDashboardScreen } from "../../features/dashboard/ManagerDashboardScreen";
import { billingService } from "../../features/billing/billingService";
import { patientService } from "../../features/patients/patientService";
import { reportsService } from "../../features/reports/reportsService";
import { resultsService } from "../../features/results/resultsService";
import { sampleService } from "../../features/samples/sampleService";
import type { ApprovalQueueItem } from "../../features/results/types";
import type { SampleSummary } from "../../features/samples/types";

vi.mock("../../features/patients/patientService", () => ({
  patientService: { listPatients: vi.fn() },
}));
vi.mock("../../features/billing/billingService", () => ({
  billingService: { listInvoices: vi.fn() },
}));
vi.mock("../../features/results/resultsService", () => ({
  resultsService: { getApprovalsQueue: vi.fn() },
}));
vi.mock("../../features/reports/reportsService", () => ({
  reportsService: { getExceptions: vi.fn() },
}));
vi.mock("../../features/samples/sampleService", () => ({
  sampleService: { listSamples: vi.fn() },
}));

const manager = {
  id: "manager-1",
  email: "manager@lab.pk",
  display_name: "Sana Malik",
  role: "manager" as const,
  branch_ids: ["b1"],
};

function approval(
  id: string,
  critical: boolean,
  patient: string,
): ApprovalQueueItem {
  return {
    result_id: id,
    sample_id: `sample-${id}`,
    accession_id: `ACC-${id}`,
    patient_id: `patient-${id}`,
    patient_name: patient,
    patient_mrn: `MRN-${id}`,
    test_id: `test-${id}`,
    test_name: "Complete Blood Count",
    value: "4.1",
    unit: "10^9/L",
    flag: critical ? "critical_low" : "normal",
    is_critical: critical,
    entered_by_name: "technician@lab.pk",
    entered_at: new Date().toISOString(),
    waiting_time: "20m",
  };
}

function sample(id: string, status: SampleSummary["status"]): SampleSummary {
  return {
    id,
    accession_id: `ACC-${id}`,
    invoice_id: `invoice-${id}`,
    patient_id: `patient-${id}`,
    patient_name: "Patient",
    patient_mrn: `MRN-${id}`,
    branch_id: "b1",
    branch_name: "Main Branch",
    status,
    tests: ["CBC"],
    collected_at: new Date().toISOString(),
  };
}

describe("Manager dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", manager);
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
      {
        id: "p2",
        mrn: "MRN-2",
        name: "Older Patient",
        sex: "F",
        branch_id: "b1",
        created_at: new Date(Date.now() - 48 * 60 * 60 * 1000).toISOString(),
        updated_at: new Date().toISOString(),
        is_cross_branch: false,
      },
    ]);
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: [],
      daily_total: "5650.00",
    });
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValue([
      approval("1", true, "Critical Patient"),
      approval("2", false, "Routine Patient"),
      approval("3", false, "Third Patient"),
    ]);
    vi.mocked(reportsService.getExceptions).mockResolvedValue({
      results: [],
      counts: {
        total: 3,
        failed_generation: 0,
        failed_delivery: 1,
        late_transfer: 2,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    });
    const sampleRows = [
      sample("1", "collected"),
      sample("2", "collected"),
      sample("3", "received"),
      sample("4", "in_process"),
      sample("5", "ready"),
      sample("6", "rejected"),
    ];
    vi.mocked(sampleService.listSamples).mockImplementation(
      async ({ status } = {}) => {
        const rows = status
          ? sampleRows.filter((row) => row.status === status)
          : sampleRows;
        return { results: rows, total: rows.length };
      },
    );
  });

  it("renders the manager metrics from the real APIs", async () => {
    render(
      <MemoryRouter>
        <ManagerDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Branch operations" }),
    ).toBeInTheDocument();

    expect(
      within(await screen.findByTestId("stat-registrations-today")).getByText(
        "1",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-revenue-today")).getByText("PKR 5650.00"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-pending-approvals")).getByText("3"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-exceptions")).getByText("3"),
    ).toBeInTheDocument();

    expect(screen.getByText("2 late sample transfers")).toBeInTheDocument();
    expect(screen.getByText("1 failed report deliveries")).toBeInTheDocument();
    expect(screen.getByText("Ali Raza")).toBeInTheDocument();
  });

  it("renders unavailable states instead of zero when a service fails", async () => {
    vi.mocked(resultsService.getApprovalsQueue).mockRejectedValue(
      new Error("offline"),
    );
    vi.mocked(patientService.listPatients).mockRejectedValue(
      new Error("offline"),
    );

    render(
      <MemoryRouter>
        <ManagerDashboardScreen />
      </MemoryRouter>,
    );

    await screen.findByText("Unavailable — the patient API did not respond.");

    expect(
      within(screen.getByTestId("stat-pending-approvals")).getByText("—"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-registrations-today")).getByText("—"),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("No patients were registered today."),
    ).not.toBeInTheDocument();
  });

  it("shows no approval action or invoice creation on the manager screen", async () => {
    render(
      <MemoryRouter>
        <ManagerDashboardScreen />
      </MemoryRouter>,
    );

    await screen.findByTestId("stat-pending-approvals");

    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).not.toBeInTheDocument();
    expect(screen.queryByText(/new invoice/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /approvals/i }),
    ).not.toBeInTheDocument();
  });
});
