/**
 * Vitest tests for Results Management Suite (Screens 21–25).
 * TDD: RED -> GREEN.
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuthStore } from "../../features/auth/authStore";
import { resultsService } from "../../features/results/resultsService";
import { sampleService } from "../../features/samples/sampleService";
import {
  WorklistScreen,
  ResultEntryScreen,
  ApprovalsQueueScreen,
  ResultDetailScreen,
  AmendResultScreen,
} from "../../features/results";

// Mock dependencies
vi.mock("../../features/results/resultsService", () => ({
  resultsService: {
    getWorklist: vi.fn(),
    getApprovalsQueue: vi.fn(),
    getResultDetail: vi.fn(),
    submitResults: vi.fn(),
    approveResult: vi.fn(),
    amendResult: vi.fn(),
    withdrawResult: vi.fn(),
    recordCriticalNotification: vi.fn(),
  },
}));

vi.mock("../../features/samples/sampleService", () => ({
  sampleService: {
    getSample: vi.fn(),
    listSamples: vi.fn(),
  },
}));

describe("Screen 21: Technician Worklist (/worklist)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-tech-01",
        email: "tech@labflow.pk",
        name: "Usman Tariq",
        role: "technician",
        branch_ids: ["br-01"],
      },
    });
  });

  it("renders header, telemetry badge, and populated worklist table", async () => {
    vi.mocked(resultsService.getWorklist).mockResolvedValueOnce([
      {
        sample_id: "smp-001",
        accession_id: "CDL20261020000041",
        patient_id: "pat-001",
        patient_name: "Muhammad Imran",
        patient_mrn: "MRN-2026-00417",
        tests: ["Complete Blood Count (CBC)"],
        collected_at: new Date(Date.now() - 7500000).toISOString(),
        waiting_time: "2h 5m",
        status: "ready",
      },
      {
        sample_id: "smp-002",
        accession_id: "CDL20261020000038",
        patient_id: "pat-002",
        patient_name: "Fatima Noor",
        patient_mrn: "MRN-2026-00389",
        tests: ["Lipid Profile"],
        collected_at: new Date(Date.now() - 6000000).toISOString(),
        waiting_time: "1h 40m",
        status: "in_process",
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/worklist"]}>
        <Routes>
          <Route path="/worklist" element={<WorklistScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      screen.getByText(/Live Telemetry Synchronized/i),
    ).toBeInTheDocument();
    expect(await screen.findByText("CDL20261020000041")).toBeInTheDocument();
    expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    expect(screen.getByText("2h 5m")).toBeInTheDocument();
    expect(screen.getAllByText("Ready for entry")).toHaveLength(2);
    expect(screen.getAllByText("In process")).toHaveLength(2);
    expect(
      screen.getAllByRole("link", { name: /Enter results/i }),
    ).toHaveLength(2);
  });

  it("renders an honest empty state when worklist contains 0 items", async () => {
    vi.mocked(resultsService.getWorklist).mockResolvedValueOnce([]);

    render(
      <MemoryRouter initialEntries={["/worklist"]}>
        <Routes>
          <Route path="/worklist" element={<WorklistScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/No pending specimens in the worklist/i),
    ).toBeInTheDocument();
  });

  it("renders error state with retry when service call fails", async () => {
    vi.mocked(resultsService.getWorklist).mockRejectedValueOnce(
      new Error("Failed to load clinical worklist."),
    );

    render(
      <MemoryRouter initialEntries={["/worklist"]}>
        <Routes>
          <Route path="/worklist" element={<WorklistScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/Failed to load clinical worklist/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /Retry/i })).toBeInTheDocument();
  });
});

describe("Screen 22: Result Entry (/results/entry/:sampleId)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-tech-01",
        email: "tech@labflow.pk",
        name: "Usman Tariq",
        role: "technician",
        branch_ids: ["br-01"],
      },
    });

    vi.mocked(sampleService.getSample).mockResolvedValue({
      id: "smp-001",
      accession_id: "CDL20261020000041",
      invoice_id: "inv-001",
      patient_id: "pat-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      patient_sex: "M",
      patient_age_years: 34,
      branch_id: "br-01",
      branch_name: "Gulberg Branch",
      status: "received",
      tests: ["Hemoglobin (Hb)", "WBC", "Platelets"],
      collected_at: "2026-10-20T09:15:00Z",
      collected_by: "usr-tech-01",
      sample_tests: [
        {
          id: "st-1",
          test_id: "test-hb",
          test_name: "Hemoglobin (Hb)",
          test_code: "HB",
          invoice_item_id: "item-1",
          category: "Complete Blood Count",
          unit: "g/dL",
          reference_range: {
            low: "13.0",
            high: "17.0",
            unit: "g/dL",
          },
          panel_codes: ["CBC"],
        },
        {
          id: "st-2",
          test_id: "test-wbc",
          test_name: "WBC",
          test_code: "WBC",
          invoice_item_id: "item-1",
          category: "Complete Blood Count",
          unit: "×10⁹/L",
          reference_range: {
            low: "4.0",
            high: "11.0",
            unit: "×10⁹/L",
          },
          panel_codes: ["CBC"],
        },
        {
          id: "st-3",
          test_id: "test-plt",
          test_name: "Platelets",
          test_code: "PLT",
          invoice_item_id: "item-1",
          category: "Complete Blood Count",
          unit: "×10⁹/L",
          reference_range: {
            low: "150",
            high: "410",
            unit: "×10⁹/L",
          },
          panel_codes: ["CBC"],
        },
      ],
    });
  });

  it("renders patient demographics, test parameters, and validates reference ranges", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/results/entry/smp-001"]}>
        <Routes>
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Muhammad Imran")).toBeInTheDocument();
    expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
    expect(screen.getAllByText(/Hemoglobin \(Hb\)/i).length).toBeGreaterThan(0);

    // Find input for Hemoglobin
    const hbInput = screen.getByLabelText(/Hemoglobin.*value/i);
    await user.clear(hbInput);
    await user.type(hbInput, "18.5"); // High: reference is 13.0 - 17.0

    // High flag badge should appear
    expect(await screen.findByText(/High/i)).toBeInTheDocument();

    // Type low value
    await user.clear(hbInput);
    await user.type(hbInput, "10.2"); // Low
    expect(await screen.findByText(/^Low$/i)).toBeInTheDocument();
  });

  it("submits valid results payload and triggers success callback", async () => {
    const user = userEvent.setup();
    vi.mocked(resultsService.submitResults).mockResolvedValueOnce({
      sample_id: "smp-001",
      sample_status: "in_process",
      results: [
        {
          id: "res-001",
          test_id: "test-hb",
          value: "14.2",
          unit: "g/dL",
          flag: "normal",
          status: "entered",
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/results/entry/smp-001"]}>
        <Routes>
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Muhammad Imran");

    // Fill in values for tests
    const inputs = screen.getAllByRole("textbox");
    for (const input of inputs) {
      await user.clear(input);
      await user.type(input, "14.2");
    }

    const saveBtn = screen.getByRole("button", { name: /Save results/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(resultsService.submitResults).toHaveBeenCalledWith(
        "smp-001",
        expect.arrayContaining([
          expect.objectContaining({
            value: "14.2",
          }),
        ]),
      );
    });
  });

  it("blocks submission and shows error if required values are missing", async () => {
    const user = userEvent.setup();

    render(
      <MemoryRouter initialEntries={["/results/entry/smp-001"]}>
        <Routes>
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Muhammad Imran");

    const saveBtn = screen.getByRole("button", { name: /Save results/i });
    await user.click(saveBtn);

    expect(
      await screen.findByText(/Please enter values for all ordered tests/i),
    ).toBeInTheDocument();
    expect(resultsService.submitResults).not.toHaveBeenCalled();
  });

  it("renders 403 Role Denied when user is Receptionist", async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-rec-01",
        email: "rec@labflow.pk",
        name: "Bilal Ahmed",
        role: "reception",
        branch_ids: ["br-01"],
      },
    });

    render(
      <MemoryRouter initialEntries={["/results/entry/smp-001"]}>
        <Routes>
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(
      await screen.findByText(/Access Denied · Role Restricted/i),
    ).toBeInTheDocument();
    expect(
      screen.getByText(
        /Only Technician, Pathologist, or Owner may enter results/i,
      ),
    ).toBeInTheDocument();
  });

  it("allows owner superrole to access result entry", async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-owner-01",
        email: "owner@labflow.pk",
        name: "Lab Owner",
        role: "owner",
        branch_ids: ["br-01"],
      },
    });

    render(
      <MemoryRouter initialEntries={["/results/entry/smp-001"]}>
        <Routes>
          <Route
            path="/results/entry/:sampleId"
            element={<ResultEntryScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText("Muhammad Imran")).toBeInTheDocument();
  });
});

describe("Screen 23: Approvals Queue (/results/approvals)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-path-01",
        email: "ayesha@labflow.pk",
        name: "Dr. Ayesha Khan",
        role: "pathologist",
        branch_ids: ["br-01"],
      },
    });
  });

  it("renders critical banners, items pending sign-off, and quick stats", async () => {
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValueOnce([
      {
        result_id: "res-001",
        sample_id: "smp-001",
        accession_id: "CDL20261020000041",
        patient_id: "pat-001",
        patient_name: "Muhammad Imran",
        patient_mrn: "MRN-2026-00417",
        test_id: "test-k",
        test_name: "Potassium (K+)",
        specimen_type: "Serum",
        value: "6.8",
        unit: "mmol/L",
        flag: "critical_high",
        is_critical: true,
        entered_by_name: "Usman Tariq · 09:40",
        entered_at: new Date(Date.now() - 12000000).toISOString(),
        waiting_time: "3h 20m",
      },
      {
        result_id: "res-002",
        sample_id: "smp-002",
        accession_id: "CDL20261020000038",
        patient_id: "pat-002",
        patient_name: "Ahmed Raza",
        patient_mrn: "MRN-2026-00419",
        test_id: "test-cbc",
        test_name: "Complete Blood Count (CBC)",
        specimen_type: "Whole Blood",
        value: "Normal",
        unit: "",
        flag: "normal",
        is_critical: false,
        entered_by_name: "Usman Tariq · 10:30",
        entered_at: new Date(Date.now() - 9000000).toISOString(),
        waiting_time: "2h 30m",
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/results/approvals"]}>
        <Routes>
          <Route path="/results/approvals" element={<ApprovalsQueueScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Approvals queue/i)).toBeInTheDocument();
    expect(screen.getByText("CRITICAL")).toBeInTheDocument();
    expect(screen.getByText(/6.8 mmol\/L/i)).toBeInTheDocument();
    expect(screen.getByText(/— high/i)).toBeInTheDocument();
    expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    expect(screen.getByText("Ahmed Raza")).toBeInTheDocument();
  });

  it("queue exposes no one-click approval and links to the range-review detail page", async () => {
    const user = userEvent.setup();
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValueOnce([
      {
        result_id: "res-002",
        sample_id: "smp-002",
        accession_id: "CDL20261020000038",
        patient_id: "pat-002",
        patient_name: "Ahmed Raza",
        patient_mrn: "MRN-2026-00419",
        test_id: "test-cbc",
        test_name: "Complete Blood Count (CBC)",
        specimen_type: "Whole Blood",
        value: "Normal",
        unit: "",
        flag: "normal",
        is_critical: false,
        entered_by_name: "Usman Tariq · 10:30",
        entered_at: new Date().toISOString(),
        waiting_time: "1h 15m",
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/results/approvals"]}>
        <Routes>
          <Route path="/results/approvals" element={<ApprovalsQueueScreen />} />
          <Route
            path="/results/:id"
            element={<div>Result detail with reference range</div>}
          />
        </Routes>
      </MemoryRouter>,
    );

    const patientCell = await screen.findByText("Ahmed Raza");
    const row = patientCell.closest("tr");
    expect(row).not.toBeNull();

    // The row exposes only the Reject action; approval is a navigation step.
    expect(within(row as HTMLElement).getAllByRole("button")).toHaveLength(1);
    expect(
      within(row as HTMLElement).getByRole("button", { name: /Reject/i }),
    ).toBeInTheDocument();
    expect(resultsService.approveResult).not.toHaveBeenCalled();

    const reviewLink = within(row as HTMLElement).getByRole("link", {
      name: /Review and approve/i,
    });
    expect(reviewLink).toHaveAttribute("href", "/results/res-002");
    await user.click(reviewLink);

    expect(
      await screen.findByText("Result detail with reference range"),
    ).toBeInTheDocument();
  });

  it("enforces mandatory note when rejecting a result", async () => {
    const user = userEvent.setup();
    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValueOnce([
      {
        result_id: "res-002",
        sample_id: "smp-002",
        accession_id: "CDL20261020000038",
        patient_id: "pat-002",
        patient_name: "Ahmed Raza",
        patient_mrn: "MRN-2026-00419",
        test_id: "test-cbc",
        test_name: "Complete Blood Count (CBC)",
        specimen_type: "Whole Blood",
        value: "Unparseable",
        unit: "",
        flag: "abnormal",
        is_critical: false,
        entered_by_name: "Usman Tariq",
        entered_at: new Date().toISOString(),
        waiting_time: "45m",
      },
    ]);

    render(
      <MemoryRouter initialEntries={["/results/approvals"]}>
        <Routes>
          <Route path="/results/approvals" element={<ApprovalsQueueScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("Ahmed Raza");
    const rejectBtn = screen.getByRole("button", { name: /Reject/i });
    await user.click(rejectBtn);

    // Modal or note prompt appears
    expect(
      await screen.findByText(/Rejection Note Required/i),
    ).toBeInTheDocument();

    const confirmReject = screen.getByRole("button", {
      name: /Confirm Rejection/i,
    });
    await user.click(confirmReject);

    // Should not call service without note
    expect(resultsService.approveResult).not.toHaveBeenCalled();

    // Type note
    const noteInput = screen.getByPlaceholderText(
      /Enter clinical reason for rejection/i,
    );
    await user.type(noteInput, "Specimen clotted. Recollect required.");

    vi.mocked(resultsService.approveResult).mockResolvedValueOnce({
      id: "res-002",
      status: "rejected",
      decision: "rejected",
      note: "Specimen clotted. Recollect required.",
      range_override: false,
      approved_by: "usr-path-01",
    });

    await user.click(confirmReject);

    await waitFor(() => {
      expect(resultsService.approveResult).toHaveBeenCalledWith("res-002", {
        decision: "rejected",
        note: "Specimen clotted. Recollect required.",
      });
    });
  });

  it("allows owner superrole to access approvals queue", async () => {
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-owner-01",
        email: "owner@labflow.pk",
        name: "Lab Owner",
        role: "owner",
        branch_ids: ["br-01"],
      },
    });

    vi.mocked(resultsService.getApprovalsQueue).mockResolvedValueOnce([]);

    render(
      <MemoryRouter initialEntries={["/results/approvals"]}>
        <Routes>
          <Route path="/results/approvals" element={<ApprovalsQueueScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Approvals queue/i)).toBeInTheDocument();
    expect(screen.queryByText(/Access Denied/i)).not.toBeInTheDocument();
  });
});

describe("Screen 24: Result Detail (/results/:id)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-path-01",
        email: "ayesha@labflow.pk",
        name: "Dr. Ayesha Khan",
        role: "pathologist",
        branch_ids: ["br-01"],
      },
    });
  });

  it("renders quantitative metrics, visual gauge, telemetry, and critical notification card", async () => {
    vi.mocked(resultsService.getResultDetail).mockResolvedValueOnce({
      id: "res-001",
      sample_id: "smp-001",
      accession_id: "CDL20261020000041",
      patient_id: "pat-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      patient_sex: "M",
      patient_age_years: 34,
      test_id: "test-k",
      test_name: "Potassium (K+)",
      method: "Ion-Selective Electrode (ISE)",
      specimen_type: "Serum (Gold top)",
      analyzer: "Roche Cobas c501",
      value: "6.8",
      unit: "mmol/L",
      flag: "critical_high",
      is_critical: true,
      status: "entered",
      matched_range: "3.5 – 5.1 mmol/L",
      critical_threshold: "> 6.2 mmol/L",
      entered_by_name: "Usman Tariq",
      entered_at: "2026-10-20T09:38:00Z",
      previous_value: "4.2 mmol/L",
      previous_date: "14 Sep 2026",
      shift_rate: "+61.9% in 36 days",
      delta_note: "Δ +2.6 — exceeds delta limit",
      critical_notification: {
        notified_name: "Dr. Tariq Niazi",
        notified_at: "2026-10-20T10:15:00Z",
        read_back: true,
        recipient_role: "Ward Medical Officer",
      },
    });

    render(
      <MemoryRouter initialEntries={["/results/res-001"]}>
        <Routes>
          <Route path="/results/:id" element={<ResultDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findAllByText(/Potassium \(K\+\)/i)).toHaveLength(2);
    expect(screen.getByText("6.8")).toBeInTheDocument();
    expect(screen.getByText("mmol/L")).toBeInTheDocument();
    expect(screen.getByText(/3.5 – 5.1 mmol\/L/i)).toBeInTheDocument();
    expect(screen.getByText(/Dr. Tariq Niazi/i)).toBeInTheDocument();
    expect(screen.getByText(/Read-back: Yes/i)).toBeInTheDocument();
  });

  it("allows pathologist to approve result with clinical justification note", async () => {
    const user = userEvent.setup();
    vi.mocked(resultsService.getResultDetail).mockResolvedValueOnce({
      id: "res-001",
      sample_id: "smp-001",
      accession_id: "CDL20261020000041",
      patient_id: "pat-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      test_id: "test-k",
      test_name: "Potassium (K+)",
      value: "6.8",
      unit: "mmol/L",
      flag: "critical_high",
      is_critical: true,
      status: "entered",
      matched_range: "3.5 – 5.1 mmol/L",
      entered_by_name: "Usman Tariq",
      entered_at: "2026-10-20T09:38:00Z",
    });

    vi.mocked(resultsService.approveResult).mockResolvedValueOnce({
      id: "res-001",
      status: "approved",
      decision: "approved",
      note: "Panic value verified with ward on-duty consultant.",
      range_override: false,
      approved_by: "usr-path-01",
    });

    render(
      <MemoryRouter initialEntries={["/results/res-001"]}>
        <Routes>
          <Route path="/results/:id" element={<ResultDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText("6.8");
    const noteArea = screen.getByPlaceholderText(
      /Document clinical review rationale/i,
    );
    await user.type(
      noteArea,
      "Panic value verified with ward on-duty consultant.",
    );

    const submitBtn = screen.getByRole("button", { name: /Submit decision/i });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(resultsService.approveResult).toHaveBeenCalledWith("res-001", {
        decision: "approved",
        note: "Panic value verified with ward on-duty consultant.",
        range_override: false,
      });
    });
  });
});

describe("Screen 25: Amend Result (/results/:id/amend)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-path-01",
        email: "ayesha@labflow.pk",
        name: "Dr. Ayesha Khan",
        role: "pathologist",
        branch_ids: ["br-01"],
      },
    });
  });

  it("displays immutable baseline, correction form, and audit chain", async () => {
    vi.mocked(resultsService.getResultDetail).mockResolvedValueOnce({
      id: "res-001",
      sample_id: "smp-001",
      accession_id: "CDL20261020000041",
      patient_id: "pat-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      test_id: "test-k",
      test_name: "Potassium (K+)",
      value: "6.8",
      unit: "mmol/L",
      flag: "critical_high",
      is_critical: true,
      status: "approved",
      matched_range: "3.5 – 5.1 mmol/L",
      entered_by_name: "Usman Tariq",
      entered_at: "2026-10-20T09:38:00Z",
      audit_history: [
        {
          version: "v1.0",
          value: "6.8",
          unit: "mmol/L",
          status: "approved",
          timestamp: "2026-10-20T10:12:00Z",
          actor_name: "Dr. Ayesha Khan",
          note: "Initial assay flagged for high potassium.",
        },
      ],
    });

    render(
      <MemoryRouter initialEntries={["/results/res-001/amend"]}>
        <Routes>
          <Route path="/results/:id/amend" element={<AmendResultScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    expect(await screen.findByText(/Amend result/i)).toBeInTheDocument();
    expect(screen.getByText(/Approved value — read-only/i)).toBeInTheDocument();
    expect(
      screen.getByText(/The original is never edited/i),
    ).toBeInTheDocument();
    expect(screen.getByText("Amendment chain")).toBeInTheDocument();
    expect(screen.getByText("v1.0")).toBeInTheDocument();
  });

  it("submits amendment with mandatory reason and certification", async () => {
    const user = userEvent.setup();
    vi.mocked(resultsService.getResultDetail).mockResolvedValueOnce({
      id: "res-001",
      sample_id: "smp-001",
      accession_id: "CDL20261020000041",
      patient_id: "pat-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      test_id: "test-k",
      test_name: "Potassium (K+)",
      value: "6.8",
      unit: "mmol/L",
      flag: "critical_high",
      is_critical: true,
      status: "approved",
      matched_range: "3.5 – 5.1 mmol/L",
      entered_by_name: "Usman Tariq",
      entered_at: "2026-10-20T09:38:00Z",
    });

    vi.mocked(resultsService.amendResult).mockResolvedValueOnce({
      id: "res-new-002",
      test_id: "test-k",
      value: "5.9",
      unit: "mmol/L",
      flag: "high",
      status: "entered",
      entered_by: "usr-path-01",
      supersedes: "res-001",
      amend_reason:
        "Sample rerun confirmed analyzer drift on electrode cell 3B.",
    });

    render(
      <MemoryRouter initialEntries={["/results/res-001/amend"]}>
        <Routes>
          <Route path="/results/:id/amend" element={<AmendResultScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await screen.findByText(/Approved value — read-only/i);

    const valueInput = screen.getByLabelText(/Corrected value/i);
    await user.clear(valueInput);
    await user.type(valueInput, "5.9");

    const reasonInput = screen.getByLabelText(/Reason for amendment/i);
    await user.type(
      reasonInput,
      "Sample rerun confirmed analyzer drift on electrode cell 3B.",
    );

    const submitBtn = screen.getByRole("button", {
      name: /Submit amendment/i,
    });
    await user.click(submitBtn);

    await waitFor(() => {
      expect(resultsService.amendResult).toHaveBeenCalledWith("res-001", {
        value: "5.9",
        unit: "mmol/L",
        reason: "Sample rerun confirmed analyzer drift on electrode cell 3B.",
      });
    });
  });
});
