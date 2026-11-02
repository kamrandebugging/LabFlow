import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatientDetailsScreen } from "@/features/patients/PatientDetailsScreen";
import { patientService } from "@/features/patients/patientService";
import type { PatientDetail } from "@/features/patients/types";

describe("Screen 10: Patient Details (10-patient-details.html & Doc 03 §5.1)", () => {
  const mockPatient: PatientDetail = {
    id: "p-100",
    mrn: "MRN-2026-00417",
    name: "Muhammad Imran",
    sex: "M",
    phone: "+92 300 1234567",
    date_of_birth: "1992-05-10",
    branch_id: "br-01",
    branch_name: "Gulberg Branch",
    created_at: "2026-01-14T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    is_cross_branch: false,
    contacts: [
      {
        id: "c-1",
        kind: "phone",
        value: "+92 300 1234567",
        is_primary: true,
        created_at: "2026-01-14T10:00:00Z",
      },
    ],
    consents: [
      {
        id: "cs-1",
        channel: "whatsapp",
        granted_at: "2026-01-14T10:00:00Z",
        granted_by: "staff-1",
        revoked_at: null,
      },
    ],
  };

  let mockService: typeof patientService;
  const mockOnBack = vi.fn();
  const mockOnEdit = vi.fn();
  const mockOnViewHistory = vi.fn();
  const mockOnNewVisit = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...patientService,
      getPatient: vi.fn().mockResolvedValue(mockPatient),
      deletePatient: vi.fn().mockResolvedValue(undefined),
    };
  });

  it("renders patient demographics, MRN badge and active status", async () => {
    render(
      <PatientDetailsScreen
        patientId="p-100"
        service={mockService}
        onBack={mockOnBack}
        onEdit={mockOnEdit}
        onViewHistory={mockOnViewHistory}
        onNewVisit={mockOnNewVisit}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Muhammad Imran" }),
      ).toBeInTheDocument();
      expect(screen.getAllByText("MRN-2026-00417")[0]).toBeInTheDocument();
      expect(screen.getByText("ACTIVE")).toBeInTheDocument();
      expect(screen.getByText("Gulberg Branch")).toBeInTheDocument();
      expect(screen.getByText("Consent Granted")).toBeInTheDocument();
    });
  });

  it("triggers onEdit callback when clicking edit demographics", async () => {
    const user = userEvent.setup();
    render(
      <PatientDetailsScreen
        patientId="p-100"
        service={mockService}
        onEdit={mockOnEdit}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Muhammad Imran" }),
      ).toBeInTheDocument();
    });

    const editBtn = screen.getByRole("button", { name: /edit demographics/i });
    await user.click(editBtn);

    expect(mockOnEdit).toHaveBeenCalledWith("p-100");
  });

  it("triggers onViewHistory callback when clicking audit history", async () => {
    const user = userEvent.setup();
    render(
      <PatientDetailsScreen
        patientId="p-100"
        service={mockService}
        onViewHistory={mockOnViewHistory}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Muhammad Imran" }),
      ).toBeInTheDocument();
    });

    const historyBtn = screen.getByRole("button", { name: /audit history/i });
    await user.click(historyBtn);

    expect(mockOnViewHistory).toHaveBeenCalledWith("p-100");
  });
});
