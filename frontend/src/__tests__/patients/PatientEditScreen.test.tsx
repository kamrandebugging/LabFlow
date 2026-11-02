import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatientEditScreen } from "@/features/patients/PatientEditScreen";
import { patientService } from "@/features/patients/patientService";
import type { PatientDetail } from "@/features/patients/types";

describe("Screen 11: Patient Edit (11-patient-edit.html & Doc 03 §6.2)", () => {
  const mockPatient: PatientDetail = {
    id: "p-200",
    mrn: "MRN-2026-00555",
    name: "Zainab Bibi",
    sex: "F",
    phone: "03001122334",
    date_of_birth: "1995-08-22",
    branch_id: "br-01",
    branch_name: "Main Branch",
    created_at: "2026-02-01T10:00:00Z",
    updated_at: "2026-10-20T10:00:00Z",
    is_cross_branch: false,
    version: 3,
    contacts: [],
    consents: [],
  };

  let mockService: typeof patientService;
  const mockOnSuccess = vi.fn();
  const mockOnCancel = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...patientService,
      getPatient: vi.fn().mockResolvedValue(mockPatient),
      updatePatient: vi.fn().mockResolvedValue(mockPatient),
    };
  });

  it("pre-fills form with existing patient demographics", async () => {
    render(
      <PatientEditScreen
        patientId="p-200"
        service={mockService}
        onSuccess={mockOnSuccess}
        onCancel={mockOnCancel}
      />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue("Zainab Bibi")).toBeInTheDocument();
      expect(screen.getByDisplayValue("03001122334")).toBeInTheDocument();
      expect(screen.getByRole("radio", { name: /^female$/i })).toBeChecked();
    });
  });

  it("submits updated demographics with version lock", async () => {
    const user = userEvent.setup();
    render(
      <PatientEditScreen
        patientId="p-200"
        service={mockService}
        onSuccess={mockOnSuccess}
        onCancel={mockOnCancel}
      />,
    );

    await waitFor(() => {
      expect(screen.getByDisplayValue("Zainab Bibi")).toBeInTheDocument();
    });

    const nameInput = screen.getByLabelText(/full name/i);
    await user.clear(nameInput);
    await user.type(nameInput, "Zainab Tariq");

    const saveBtn = screen.getByRole("button", { name: /save changes/i });
    await user.click(saveBtn);

    await waitFor(() => {
      expect(mockService.updatePatient).toHaveBeenCalledWith(
        "p-200",
        expect.objectContaining({
          name: "Zainab Tariq",
          phone: "03001122334",
          sex: "F",
        }),
        3,
      );
      expect(mockOnSuccess).toHaveBeenCalledTimes(1);
    });
  });
});
