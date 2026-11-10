/**
 * Component tests for Reports Management Suite (Screens 26–30).
 * Covers:
 * - Screen 26: ReportsListScreen (/reports)
 * - Screen 27: ReportDetailScreen (/reports/:id)
 * - Screen 28: PatientReportAccessScreen (/report-access/:token)
 * - Screen 29: LinkExpiredScreen (/link-expired)
 * - Screen 30: ExceptionsScreen (/exceptions)
 */

import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useAuthStore } from "../../features/auth/authStore";
import { reportsService } from "../../features/reports/reportsService";
import {
  ReportsListScreen,
  ReportDetailScreen,
  PatientReportAccessScreen,
  LinkExpiredScreen,
  ExceptionsScreen,
} from "../../features/reports";

// Mock reportsService
vi.mock("../../features/reports/reportsService", () => ({
  reportsService: {
    getReports: vi.fn(),
    getReport: vi.fn(),
    regenerateReport: vi.fn(),
    deliverReport: vi.fn(),
    issueAccessToken: vi.fn(),
    revokeAccessToken: vi.fn(),
    getExceptions: vi.fn(),
    checkPublicReportAccess: vi.fn(),
  },
}));

describe("Screen 26: Reports List (/reports)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-01",
        email: "owner@labflow.pk",
        name: "Ali Raza",
        role: "owner",
        branch_ids: ["br-01"],
      },
    });
  });

  it("renders header, filter controls, and reports table", async () => {
    vi.mocked(reportsService.getReports).mockResolvedValueOnce({
      results: [
        {
          id: "rep-001",
          status: "final",
          generation_status: "completed",
          generation_error: null,
          current_version: 1,
          published_at: "2026-10-20T10:00:00Z",
          created_at: "2026-10-20T09:00:00Z",
          sample: {
            id: "smp-001",
            accession_id: "CDL20261020000041",
            collected_at: "2026-10-20T08:30:00Z",
            branch: { id: "br-01", name: "Main Lab" },
            patient: {
              id: "pat-01",
              name: "Muhammad Imran",
              mrn: "MRN-2026-00417",
            },
            tests: [
              { id: "t-1", name: "CBC", code: "CBC" },
              { id: "t-2", name: "HbA1c", code: "HbA1c" },
            ],
          },
          latest_delivery: {
            channel: "whatsapp",
            status: "delivered",
            sent_at: "2026-10-20T11:00:00Z",
          },
        },
      ],
      next_cursor: null,
    });

    render(
      <MemoryRouter initialEntries={["/reports"]}>
        <ReportsListScreen />
      </MemoryRouter>,
    );

    expect(screen.getByText("Loading clinical reports…")).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("CDL20261020000041")).toBeInTheDocument();
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
      expect(screen.getByText("CBC, HbA1c")).toBeInTheDocument();
      expect(screen.getAllByText("Final").length).toBeGreaterThan(0);
    });
  });

  it("shows honest empty state when zero reports are found", async () => {
    vi.mocked(reportsService.getReports).mockResolvedValueOnce({
      results: [],
      next_cursor: null,
    });

    render(
      <MemoryRouter initialEntries={["/reports"]}>
        <ReportsListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("No reports found")).toBeInTheDocument();
      expect(
        screen.getByText("No clinical reports have been generated yet."),
      ).toBeInTheDocument();
    });
  });

  it("opens quick delivery modal and dispatches delivery", async () => {
    const user = userEvent.setup();
    vi.mocked(reportsService.getReports).mockResolvedValueOnce({
      results: [
        {
          id: "rep-001",
          status: "final",
          generation_status: "completed",
          generation_error: null,
          current_version: 1,
          published_at: "2026-10-20T10:00:00Z",
          created_at: "2026-10-20T09:00:00Z",
          sample: {
            id: "smp-001",
            accession_id: "CDL20261020000041",
            collected_at: "2026-10-20T08:30:00Z",
            branch: { id: "br-01", name: "Main Lab" },
            patient: {
              id: "pat-01",
              name: "Muhammad Imran",
              mrn: "MRN-001",
              phone: "+92 300 1234567",
            },
            tests: [{ id: "t-1", name: "CBC", code: "CBC" }],
          },
          latest_delivery: null,
        },
      ],
      next_cursor: null,
    });

    vi.mocked(reportsService.getReport).mockResolvedValueOnce({
      id: "rep-001",
      status: "final",
      generation_status: "completed",
      generation_error: null,
      current_version: 1,
      published_at: "2026-10-20T10:00:00Z",
      created_at: "2026-10-20T09:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
      sample: {
        id: "smp-001",
        accession_id: "CDL20261020000041",
        status: "completed",
        collected_at: "2026-10-20T08:30:00Z",
        branch: { id: "br-01", name: "Main Lab" },
      },
      patient: {
        id: "pat-01",
        full_name: "Muhammad Imran",
        mrn: "MRN-001",
        age_years: 34,
        gender: "M",
        phone: "+92 300 1234567",
        email: null,
        contacts: [
          {
            id: "contact-wa-01",
            kind: "whatsapp",
            value: "03001234567",
            is_primary: true,
          },
        ],
      },
      results: [],
      versions: [],
      deliveries: [],
      access_tokens: [],
    });

    vi.mocked(reportsService.deliverReport).mockResolvedValueOnce({
      id: "del-01",
      report_id: "rep-001",
      channel: "whatsapp",
      contact_id: "contact-wa-01",
      status: "sent",
      created_at: "2026-10-20T11:00:00Z",
    });

    render(
      <MemoryRouter initialEntries={["/reports"]}>
        <ReportsListScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("CDL20261020000041")).toBeInTheDocument();
    });

    const deliverBtn = screen.getByRole("button", { name: /deliver/i });
    await user.click(deliverBtn);

    expect(screen.getByText("Deliver Clinical Report")).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getByDisplayValue("03001234567")).toBeInTheDocument();
    });
    const sendBtn = screen.getByRole("button", { name: /send report/i });
    await user.click(sendBtn);

    await waitFor(() => {
      expect(reportsService.deliverReport).toHaveBeenCalledWith("rep-001", {
        channel: "whatsapp",
        contact_id: "contact-wa-01",
      });
    });
  });
});

describe("Screen 27: Report Detail (/reports/:id)", () => {
  const mockReportDetail = {
    id: "rep-001",
    status: "final" as const,
    generation_status: "completed" as const,
    generation_error: null,
    current_version: 1,
    published_at: "2026-10-20T10:00:00Z",
    created_at: "2026-10-20T09:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    sample: {
      id: "smp-001",
      accession_id: "CDL20261020000041",
      status: "completed",
      collected_at: "2026-10-20T08:30:00Z",
      branch: { id: "br-01", name: "Main Reference Lab" },
    },
    patient: {
      id: "pat-01",
      full_name: "Muhammad Imran",
      mrn: "MRN-2026-00417",
      age_years: 42,
      gender: "Male",
      phone: "+92 300 1234567",
      email: "m.imran@email.com",
    },
    results: [
      {
        id: "res-01",
        test_name: "Potassium (K+)",
        test_code: "K+",
        value: "4.5",
        unit: "mmol/L",
        flag: "normal",
        status: "approved",
        amend_reason: null,
      },
    ],
    versions: [
      {
        id: "v-01",
        version: 1,
        pdf_key: "reports/v1.pdf",
        generated_by_id: "usr-01",
        generated_by_email: "staff@labflow.pk",
        created_at: "2026-10-20T10:00:00Z",
      },
    ],
    deliveries: [
      {
        id: "del-01",
        channel: "whatsapp" as const,
        status: "delivered" as const,
        contact_id: "pat-01",
        contact_value: "+92 300 1234567",
        contact_type: "phone",
        contact_kind: "phone",
        attempts: 1,
        next_attempt_at: null,
        last_error: null,
        sent_at: "2026-10-20T10:05:00Z",
        created_at: "2026-10-20T10:05:00Z",
      },
    ],
    access_tokens: [
      {
        id: "tok-01",
        expires_at: "2026-10-27T10:00:00Z",
        revoked_at: null,
        is_active: true,
      },
    ],
  };

  beforeEach(() => {
    vi.clearAllMocks();
    useAuthStore.setState({
      isAuthenticated: true,
      user: {
        id: "usr-01",
        email: "owner@labflow.pk",
        name: "Ali Raza",
        role: "owner",
        branch_ids: ["br-01"],
      },
    });
  });

  it("renders specimen preview, results, and right sidebar cards", async () => {
    vi.mocked(reportsService.getReport).mockResolvedValueOnce(mockReportDetail);

    render(
      <MemoryRouter initialEntries={["/reports/rep-001"]}>
        <Routes>
          <Route path="/reports/:id" element={<ReportDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041")[0]).toBeInTheDocument();
      expect(screen.getAllByText("Muhammad Imran")[0]).toBeInTheDocument();
      expect(screen.getByText("Potassium (K+)")).toBeInTheDocument();
      expect(screen.getByText("4.5")).toBeInTheDocument();
      expect(screen.getByText("Patient Access Link")).toBeInTheDocument();
    });
  });

  it("issues access token when clicking Reissue link", async () => {
    const user = userEvent.setup();
    vi.mocked(reportsService.getReport).mockResolvedValue(mockReportDetail);
    vi.mocked(reportsService.issueAccessToken).mockResolvedValueOnce({
      token_id: "tok-new-01",
      link: "/report-access/sample-new-token-123",
      expires_at: "2026-10-27T10:00:00Z",
    });

    render(
      <MemoryRouter initialEntries={["/reports/rep-001"]}>
        <Routes>
          <Route path="/reports/:id" element={<ReportDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Patient Access Link")).toBeInTheDocument();
    });

    const reissueBtn = screen.getByRole("button", { name: /reissue link/i });
    await user.click(reissueBtn);

    await waitFor(() => {
      expect(reportsService.issueAccessToken).toHaveBeenCalledWith("rep-001");
      expect(
        screen.getByText("/report-access/sample-new-token-123"),
      ).toBeInTheDocument();
    });
  });

  it("blocks delivery and explains why when no contact is stored", async () => {
    const user = userEvent.setup();
    vi.mocked(reportsService.getReport).mockResolvedValueOnce({
      ...mockReportDetail,
      patient: { ...mockReportDetail.patient, contacts: [] },
    });

    render(
      <MemoryRouter initialEntries={["/reports/rep-001"]}>
        <Routes>
          <Route path="/reports/:id" element={<ReportDetailScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Patient Access Link")).toBeInTheDocument();
    });

    await user.click(screen.getByRole("button", { name: /^deliver$/i }));

    expect(
      screen.getByText(/No stored whatsapp contact for this patient/i),
    ).toBeInTheDocument();
    expect(screen.getByRole("button", { name: /^send$/i })).toBeDisabled();
    expect(reportsService.deliverReport).not.toHaveBeenCalled();
  });
});

describe("Screen 28: Patient Report Access (/report-access/:token)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("verifies public token and offers Download Official PDF button", async () => {
    vi.mocked(reportsService.checkPublicReportAccess).mockResolvedValueOnce({
      status: 200,
      redirectUrl: "/api/v1/report-access/valid-public-token",
    });

    render(
      <MemoryRouter initialEntries={["/report-access/valid-public-token"]}>
        <Routes>
          <Route
            path="/report-access/:token"
            element={<PatientReportAccessScreen />}
          />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByText("Direct Token Access · Verified"),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("link", { name: /download official pdf/i }),
      ).toHaveAttribute("href", "/api/v1/report-access/valid-public-token");
    });
  });

  it("redirects to /link-expired when token is expired (410)", async () => {
    vi.mocked(reportsService.checkPublicReportAccess).mockResolvedValueOnce({
      status: 410,
      error: {
        code: "link_expired",
        message: "This report link has expired.",
        details: { phone: "+92 42 35712345" },
      },
    });

    render(
      <MemoryRouter initialEntries={["/report-access/expired-token"]}>
        <Routes>
          <Route
            path="/report-access/:token"
            element={<PatientReportAccessScreen />}
          />
          <Route path="/link-expired" element={<LinkExpiredScreen />} />
        </Routes>
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("This link has expired")).toBeInTheDocument();
      expect(screen.getByText("+92 42 35712345")).toBeInTheDocument();
    });
  });
});

describe("Screen 29: Link Expired (/link-expired)", () => {
  it("renders calm card with guidance and lab phone", () => {
    render(
      <MemoryRouter initialEntries={["/link-expired"]}>
        <LinkExpiredScreen />
      </MemoryRouter>,
    );

    expect(screen.getByText("This link has expired")).toBeInTheDocument();
    expect(
      screen.getByText(
        "Please call the lab — our staff can reissue your report link.",
      ),
    ).toBeInTheDocument();
    expect(screen.getByText("+92 42 35712345")).toBeInTheDocument();
    expect(screen.getByText("Back to home")).toBeInTheDocument();
  });
});

describe("Screen 30: Exceptions Queue (/exceptions)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it("renders populated exceptions categorized by kinds", async () => {
    vi.mocked(reportsService.getExceptions).mockResolvedValueOnce({
      results: [
        {
          id: "x-01",
          kind: "late_transfer",
          title: "Late transfer: Gulberg -> DHA",
          severity: "warning",
          reference_id: "smp-01",
          reference_code: "CDL20261019000012",
          patient_name: "Fatima Noor",
          branch_name: "Gulberg",
          created_at: "2026-10-19T16:40:00Z",
          details: { hours_late: 18.0 },
        },
        {
          id: "x-02",
          kind: "failed_generation",
          title: "Report generation failed (CDL20261020000099)",
          severity: "error",
          reference_id: "rep-99",
          reference_code: "CDL20261020000099",
          patient_name: "Ali Ahmed",
          branch_name: "Main Lab",
          created_at: "2026-10-20T10:00:00Z",
          details: { generation_error: "Rendering timeout" },
        },
      ],
      counts: {
        total: 2,
        failed_generation: 1,
        failed_delivery: 0,
        late_transfer: 1,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    });

    render(
      <MemoryRouter initialEntries={["/exceptions"]}>
        <ExceptionsScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("2 Actionable")).toBeInTheDocument();
      expect(screen.getByText("Late Specimen Transfers")).toBeInTheDocument();
      expect(screen.getByText("Failed PDF Generations")).toBeInTheDocument();
      expect(screen.getByText("CDL20261019000012")).toBeInTheDocument();
      expect(screen.getByText("CDL20261020000099")).toBeInTheDocument();
    });
  });

  it("renders honest empty state when zero exceptions exist", async () => {
    vi.mocked(reportsService.getExceptions).mockResolvedValueOnce({
      results: [],
      counts: {
        total: 0,
        failed_generation: 0,
        failed_delivery: 0,
        late_transfer: 0,
        critical_unacknowledged: 0,
        stuck_sample: 0,
      },
    });

    render(
      <MemoryRouter initialEntries={["/exceptions"]}>
        <ExceptionsScreen />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("0 Actionable")).toBeInTheDocument();
      expect(screen.getByText("No active exceptions")).toBeInTheDocument();
      expect(
        screen.getByText(
          "All clinical transfers, report generations, deliveries, and critical notifications are operating within target SLAs.",
        ),
      ).toBeInTheDocument();
    });
  });
});
