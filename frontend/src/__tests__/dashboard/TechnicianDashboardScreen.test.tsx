import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import { TechnicianDashboardScreen } from "../../features/dashboard/TechnicianDashboardScreen";
import { resultsService } from "../../features/results/resultsService";
import { sampleService } from "../../features/samples/sampleService";
import type { ResultDetailRecord } from "../../features/results/types";
import type { WorklistItem } from "../../features/results/types";

vi.mock("../../features/results/resultsService", () => ({
  resultsService: {
    getWorklist: vi.fn(),
    listResults: vi.fn(),
  },
}));
vi.mock("../../features/samples/sampleService", () => ({
  sampleService: { listSamples: vi.fn() },
}));

const technician = {
  id: "tech-1",
  email: "technician@lab.pk",
  display_name: "Usman Tariq",
  role: "technician" as const,
  branch_ids: ["b1"],
};

function workItem(
  id: string,
  patient: string,
  status: WorklistItem["sample_status"],
): WorklistItem {
  return {
    sample_id: `s-${id}`,
    sample_status: status,
    accession_id: `ACC-${id}`,
    patient_id: `p-${id}`,
    patient_name: patient,
    patient_mrn: `MRN-${id}`,
    branch_id: "b1",
    branch_name: "Main Branch",
    tests: ["CBC"],
    collected_at: new Date().toISOString(),
    waiting_time: "35m",
    status:
      status === "in_process"
        ? "in_process"
        : status === "rejected"
          ? "rejected"
          : "ready",
  };
}

function result(id: string, critical: boolean): ResultDetailRecord {
  return {
    id,
    sample_id: `s-${id}`,
    accession_id: `ACC-${id}`,
    patient_id: `p-${id}`,
    patient_name: "Ahmed Raza",
    patient_mrn: `MRN-${id}`,
    test_id: `t-${id}`,
    test_name: "Serum Potassium",
    value: "6.2",
    unit: "mmol/L",
    flag: critical ? "critical_high" : "normal",
    is_critical: critical,
    status: "entered",
    matched_range: "3.5 - 5.1",
    entered_by_name: "technician@lab.pk",
    entered_at: new Date().toISOString(),
  };
}

describe("Technician dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", technician);
    vi.mocked(resultsService.getWorklist).mockResolvedValue([
      workItem("1", "Ahmed Raza", "collected"),
      workItem("2", "Fatima Noor", "received"),
      workItem("3", "Muhammad Imran", "in_process"),
    ]);
    const sampleRows = [
      {
        id: "s1",
        accession_id: "ACC-1",
        invoice_id: "inv-1",
        patient_id: "p1",
        patient_name: "Ahmed Raza",
        patient_mrn: "MRN-1",
        branch_id: "b1",
        branch_name: "Main Branch",
        status: "collected" as const,
        tests: ["CBC"],
        collected_at: new Date().toISOString(),
      },
      {
        id: "s2",
        accession_id: "ACC-2",
        invoice_id: "inv-2",
        patient_id: "p2",
        patient_name: "Fatima Noor",
        patient_mrn: "MRN-2",
        branch_id: "b1",
        branch_name: "Main Branch",
        status: "received" as const,
        tests: ["LFT"],
        collected_at: new Date().toISOString(),
      },
      {
        id: "s3",
        accession_id: "ACC-3",
        invoice_id: "inv-3",
        patient_id: "p3",
        patient_name: "Muhammad Imran",
        patient_mrn: "MRN-3",
        branch_id: "b1",
        branch_name: "Main Branch",
        status: "in_process" as const,
        tests: ["RFT"],
        collected_at: new Date().toISOString(),
      },
    ];
    vi.mocked(sampleService.listSamples).mockImplementation(
      async ({ status } = {}) => {
        const rows = status
          ? sampleRows.filter((row) => row.status === status)
          : sampleRows;
        return { results: rows, total: rows.length };
      },
    );
    vi.mocked(resultsService.listResults).mockResolvedValue([
      result("1", true),
      result("2", false),
    ]);
  });

  it("renders worklist, receipt and critical counts from the real APIs", async () => {
    render(
      <MemoryRouter>
        <TechnicianDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Bench worklist" }),
    ).toBeInTheDocument();

    expect(
      within(await screen.findByTestId("stat-worklist")).getByText("3"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-receipt")).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-result-entry")).getByText("2"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-critical-pending")).getByText("1"),
    ).toBeInTheDocument();

    expect(screen.getAllByText("Ahmed Raza").length).toBeGreaterThan(0);
    expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
    expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
  });

  it("shows an unavailable critical panel instead of a false zero", async () => {
    vi.mocked(resultsService.listResults).mockRejectedValue(
      new Error("offline"),
    );

    render(
      <MemoryRouter>
        <TechnicianDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText("Unavailable — the results API did not respond."),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-critical-pending")).getByText("—"),
    ).toBeInTheDocument();
  });

  it("shows no billing, revenue or approval actions", async () => {
    render(
      <MemoryRouter>
        <TechnicianDashboardScreen />
      </MemoryRouter>,
    );

    await screen.findByTestId("stat-worklist");

    expect(screen.queryByText(/revenue today/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/invoices & payments/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /approve/i }),
    ).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /invoices/i }),
    ).not.toBeInTheDocument();
  });
});
