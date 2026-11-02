import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatientHistoryScreen } from "@/features/patients/PatientHistoryScreen";
import { patientService } from "@/features/patients/patientService";
import type { PatientDetail } from "@/features/patients/types";

describe("Screen 12: Patient History (12-patient-history.html & Doc 03 §5.1)", () => {
  const mockPatient: PatientDetail = {
    id: "p-300",
    mrn: "MRN-2026-00417",
    name: "Muhammad Imran",
    sex: "M",
    phone: "+92 300 8472910",
    date_of_birth: "1984-06-12",
    branch_id: "br-01",
    branch_name: "Gulberg Main Branch",
    created_at: "2025-01-14T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    last_visit: "20 Oct 2026",
    is_cross_branch: false,
    contacts: [],
    consents: [],
  };

  let mockService: typeof patientService;
  const mockOnBack = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...patientService,
      getPatient: vi.fn().mockResolvedValue(mockPatient),
    };
  });

  it("renders patient history header, MRN, and ledger notices", async () => {
    render(
      <PatientHistoryScreen
        patientId="p-300"
        service={mockService}
        onBack={mockOnBack}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", {
          name: /patient history — muhammad imran/i,
        }),
      ).toBeInTheDocument();
      expect(screen.getAllByText("MRN-2026-00417")[0]).toBeInTheDocument();
      expect(screen.getByText(/partitioned ledger scope/i)).toBeInTheDocument();
      expect(
        screen.getByText(/patient registration & demographic enrolment/i),
      ).toBeInTheDocument();
    });
  });

  it("triggers onBack when clicking back button", async () => {
    const user = userEvent.setup();
    render(
      <PatientHistoryScreen
        patientId="p-300"
        service={mockService}
        onBack={mockOnBack}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("MRN-2026-00417")[0]).toBeInTheDocument();
    });

    const backBtn = screen.getByRole("button", { name: /patients/i });
    await user.click(backBtn);

    expect(mockOnBack).toHaveBeenCalledTimes(1);
  });
});
