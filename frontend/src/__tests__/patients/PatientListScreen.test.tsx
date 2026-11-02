import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { PatientListScreen } from "@/features/patients/PatientListScreen";
import { patientService } from "@/features/patients/patientService";
import type { PatientSummary } from "@/features/patients/types";

describe("Screen 08: Patient List (08-patient-list.html & Doc 03 §5.1)", () => {
  const mockPatients: PatientSummary[] = [
    {
      id: "p-001",
      mrn: "MRN-2026-00417",
      name: "Muhammad Imran",
      sex: "M",
      phone: "+92 300 1234567",
      date_of_birth: "1992-05-10",
      branch_id: "br-01",
      branch_name: "Gulberg Branch",
      last_visit: "20 Oct 2026",
      created_at: "2026-10-20T10:00:00Z",
      updated_at: "2026-10-20T10:00:00Z",
      is_cross_branch: false,
    },
    {
      id: "p-002",
      mrn: "MRN-2026-00418",
      name: "Fatima Noor",
      sex: "F",
      phone: "+92 321 9876543",
      date_of_birth: "1997-02-14",
      branch_id: "br-02",
      branch_name: "DHA Branch",
      last_visit: "20 Oct 2026",
      created_at: "2026-10-20T11:00:00Z",
      updated_at: "2026-10-20T11:00:00Z",
      is_cross_branch: true,
    },
  ];

  let mockService: typeof patientService;
  const mockOnNewPatient = vi.fn();
  const mockOnSelectPatient = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockService = {
      ...patientService,
      listPatients: vi.fn().mockResolvedValue(mockPatients),
      getPatient: vi.fn(),
      createPatient: vi.fn(),
      updatePatient: vi.fn(),
      deletePatient: vi.fn(),
    };
  });

  it("renders header title and table columns correctly", async () => {
    render(
      <PatientListScreen
        service={mockService}
        onNewPatient={mockOnNewPatient}
        onSelectPatient={mockOnSelectPatient}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /patients/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByPlaceholderText(/search by name, phone or mrn/i),
    ).toBeInTheDocument();

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
      expect(screen.getByText("Fatima Noor")).toBeInTheDocument();
      expect(screen.getByText("Cross-Branch")).toBeInTheDocument();
    });
  });

  it("triggers search filtering when query is typed", async () => {
    const user = userEvent.setup();
    render(
      <PatientListScreen
        service={mockService}
        onNewPatient={mockOnNewPatient}
        onSelectPatient={mockOnSelectPatient}
      />,
    );

    const searchInput = screen.getByPlaceholderText(
      /search by name, phone or mrn/i,
    );
    await user.type(searchInput, "Imran");

    await waitFor(() => {
      expect(mockService.listPatients).toHaveBeenCalledWith({ q: "Imran" });
    });
  });

  it("triggers onNewPatient callback when clicking New Patient button", async () => {
    const user = userEvent.setup();
    render(
      <PatientListScreen
        service={mockService}
        onNewPatient={mockOnNewPatient}
        onSelectPatient={mockOnSelectPatient}
      />,
    );

    const newBtn = screen.getByRole("button", { name: /new patient/i });
    await user.click(newBtn);

    expect(mockOnNewPatient).toHaveBeenCalledTimes(1);
  });

  it("triggers onSelectPatient callback when row is clicked", async () => {
    const user = userEvent.setup();
    render(
      <PatientListScreen
        service={mockService}
        onNewPatient={mockOnNewPatient}
        onSelectPatient={mockOnSelectPatient}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const row = screen.getByText("Muhammad Imran").closest("tr");
    expect(row).not.toBeNull();
    if (row) await user.click(row);

    expect(mockOnSelectPatient).toHaveBeenCalledWith("p-001");
  });

  it("renders empty state when no patients return", async () => {
    mockService.listPatients = vi.fn().mockResolvedValue([]);
    render(
      <PatientListScreen
        service={mockService}
        onNewPatient={mockOnNewPatient}
        onSelectPatient={mockOnSelectPatient}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/no patients found/i)).toBeInTheDocument();
    });
  });
});
