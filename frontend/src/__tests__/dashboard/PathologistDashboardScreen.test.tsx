import { render, screen, within } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { beforeEach, describe, expect, it, vi } from "vitest";

import { useAuthStore } from "../../features/auth/authStore";
import { PathologistDashboardScreen } from "../../features/dashboard/PathologistDashboardScreen";
import { resultsService } from "../../features/results/resultsService";
import type {
  ApprovalQueueItem,
  ResultDetailRecord,
} from "../../features/results/types";

vi.mock("../../features/results/resultsService", () => ({
  resultsService: {
    getApprovalsQueue: vi.fn(),
    listResults: vi.fn(),
  },
}));

const pathologist = {
  id: "path-1",
  email: "pathologist@lab.pk",
  display_name: "Dr. Ayesha Khan",
  role: "pathologist" as const,
  branch_ids: [],
};

function approval(id: string, critical: boolean): ApprovalQueueItem {
  return {
    result_id: id,
    sample_id: `s-${id}`,
    accession_id: `ACC-${id}`,
    patient_id: `p-${id}`,
    patient_name: critical ? "Critical Patient" : "Routine Patient",
    patient_mrn: `MRN-${id}`,
    test_id: `t-${id}`,
    test_name: "Serum Potassium",
    value: critical ? "6.2" : "4.2",
    unit: "mmol/L",
    flag: critical ? "critical_high" : "normal",
    is_critical: critical,
    entered_by_name: "technician@lab.pk",
    entered_at: new Date().toISOString(),
    waiting_time: "18m",
  };
}

function approved(
  id: string,
  patient: string,
  approvedAt = new Date().toISOString(),
): ResultDetailRecord {
  return {
    id,
    sample_id: `s-${id}`,
    accession_id: `ACC-${id}`,
    patient_id: `p-${id}`,
    patient_name: patient,
    patient_mrn: `MRN-${id}`,
    test_id: `t-${id}`,
    test_name: "Lipid Profile",
    value: "4.8",
    unit: "mmol/L",
    flag: "normal",
    is_critical: false,
    status: "approved",
    matched_range: "3.5 - 5.1",
    entered_by_name: "technician@lab.pk",
    entered_at: approvedAt,
    approved_at: approvedAt,
  };
}

describe("Pathologist dashboard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.getState().setSession("token", pathologist);
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValue([
      approval("1", true),
      approval("2", false),
      approval("3", false),
    ]);
    vi.mocked(resultsService.listResults).mockResolvedValue([
      approved("1", "Fatima Noor"),
      approved("2", "Muhammad Imran"),
    ]);
  });

  it("renders approval queue counts and recent approvals", async () => {
    render(
      <MemoryRouter>
        <PathologistDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByRole("heading", { name: "Clinical approvals" }),
    ).toBeInTheDocument();

    expect(
      within(await screen.findByTestId("stat-awaiting-verification")).getByText(
        "3",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-critical")).getByText("1"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-routine")).getByText("2"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-recent-approvals")).getByText("2"),
    ).toBeInTheDocument();

    expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
    expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    expect(screen.getByText("Critical Patient")).toBeInTheDocument();
  });

  it("orders recent approvals newest first", async () => {
    vi.mocked(resultsService.listResults).mockResolvedValue([
      approved("old", "Older Patient", "2026-11-10T08:00:00Z"),
      approved("new", "Newest Patient", "2026-11-12T08:00:00Z"),
    ]);

    render(
      <MemoryRouter>
        <PathologistDashboardScreen />
      </MemoryRouter>,
    );

    const panel = await screen.findByTestId("panel-recent-approvals");
    // The panel mounts while its table is still loading; wait for the rows
    // instead of reading them synchronously and racing the fetch.
    const rows = await within(panel).findAllByRole("row");
    expect(rows[1]).toHaveTextContent("Newest Patient");
    expect(rows[2]).toHaveTextContent("Older Patient");
  });

  it("shows an unavailable queue instead of a false zero", async () => {
    vi.mocked(resultsService.getApprovalsQueue).mockRejectedValue(
      new Error("offline"),
    );

    render(
      <MemoryRouter>
        <PathologistDashboardScreen />
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(
        "Unavailable — the approvals API did not respond.",
      ),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-awaiting-verification")).getByText("—"),
    ).toBeInTheDocument();
    expect(
      within(screen.getByTestId("stat-critical")).getByText("—"),
    ).toBeInTheDocument();
  });

  it("shows no invoice or payment actions", async () => {
    render(
      <MemoryRouter>
        <PathologistDashboardScreen />
      </MemoryRouter>,
    );

    await screen.findByTestId("stat-awaiting-verification");

    expect(screen.queryByText(/new invoice/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/record payment/i)).not.toBeInTheDocument();
    expect(
      screen.queryByRole("link", { name: /invoices/i }),
    ).not.toBeInTheDocument();
  });
});
