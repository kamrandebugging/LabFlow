import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { RegisterPatientScreen } from "@/features/patients/RegisterPatientScreen";
import {
  DuplicatePatientError,
  patientService,
} from "@/features/patients/patientService";
import type { PatientSummary } from "@/features/patients/types";

describe("Screen 09: Register Patient (09-register-patient.html & Doc 03 §6.2)", () => {
  const mockCreatedPatient: PatientSummary = {
    id: "p-new-001",
    mrn: "MRN-2026-00999",
    name: "Tariq Mahmood",
    sex: "M",
    phone: "03009876543",
    date_of_birth: "1988-11-20",
    branch_id: "00000000-0000-0000-0000-000000000001",
    branch_name: "Main Branch",
    created_at: "2026-11-02T10:00:00Z",
    updated_at: "2026-11-02T10:00:00Z",
    is_cross_branch: false,
  };

  let mockService: typeof patientService;
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...patientService,
      listPatients: vi.fn(),
      getPatient: vi.fn(),
      createPatient: vi.fn().mockResolvedValue(mockCreatedPatient),
      updatePatient: vi.fn(),
      deletePatient: vi.fn(),
    };
  });

  it("renders registration form inputs according to ISO 15189 spec", () => {
    render(
      <RegisterPatientScreen
        service={mockService}
        onSuccess={mockOnSuccess}
        onCancel={mockOnCancel}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /register patient/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/phone/i)).toBeInTheDocument();
    expect(screen.getByRole("radio", { name: /^male$/i })).toBeInTheDocument();
    expect(
      screen.getByRole("radio", { name: /^female$/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/date of birth/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/whatsapp number/i)).toBeInTheDocument();
  });

  it("submits valid patient data and calls onSuccess", async () => {
    const user = userEvent.setup();
    render(
      <RegisterPatientScreen
        service={mockService}
        onSuccess={mockOnSuccess}
        onCancel={mockOnCancel}
      />,
    );

    await user.type(screen.getByLabelText(/full name/i), "Tariq Mahmood");
    await user.type(screen.getByLabelText(/phone/i), "03009876543");
    await user.click(screen.getByRole("radio", { name: /^male$/i }));
    await user.click(screen.getByRole("button", { name: /register patient/i }));

    await waitFor(() => {
      expect(mockService.createPatient).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Tariq Mahmood",
          phone: "03009876543",
          sex: "M",
          confirm_duplicate: false,
        }),
      );
      expect(mockOnSuccess).toHaveBeenCalledWith(mockCreatedPatient);
    });
  });

  it("displays duplicate detection banner on 409 and supports confirm & register anyway", async () => {
    const user = userEvent.setup();
    const duplicateErr = new DuplicatePatientError({
      code: "possible_duplicate",
      message: "Patient already registered with matching phone number.",
      candidates: [
        {
          id: "cand-1",
          mrn: "MRN-2026-00123",
          name: "Tariq Mahmood",
          sex: "M",
          year_of_birth: 1988,
          branch_id: "br-01",
        },
      ],
    });

    mockService.createPatient = vi
      .fn()
      .mockRejectedValueOnce(duplicateErr)
      .mockResolvedValueOnce(mockCreatedPatient);

    render(
      <RegisterPatientScreen
        service={mockService}
        onSuccess={mockOnSuccess}
        onCancel={mockOnCancel}
      />,
    );

    await user.type(screen.getByLabelText(/full name/i), "Tariq Mahmood");
    await user.type(screen.getByLabelText(/phone/i), "03009876543");
    await user.click(screen.getByRole("button", { name: /register patient/i }));

    await waitFor(() => {
      expect(
        screen.getByTestId("duplicate-warning-banner"),
      ).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00123")).toBeInTheDocument();
    });

    // Click confirm & register anyway
    const confirmBtn = screen.getByRole("button", {
      name: /confirm & register anyway/i,
    });
    await user.click(confirmBtn);

    await waitFor(() => {
      expect(mockService.createPatient).toHaveBeenCalledWith(
        expect.objectContaining({
          name: "Tariq Mahmood",
          phone: "03009876543",
          confirm_duplicate: true,
        }),
      );
      expect(mockOnSuccess).toHaveBeenCalledWith(mockCreatedPatient);
    });
  });
});
