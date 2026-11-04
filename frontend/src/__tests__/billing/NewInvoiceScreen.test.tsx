import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { billingService } from "../../features/billing/billingService";
import { NewInvoiceScreen } from "../../features/billing/NewInvoiceScreen";
import type { InvoiceDetail } from "../../features/billing/types";
import { catalogService } from "../../features/catalog/catalogService";
import type {
  DiagnosticPanel,
  DiagnosticTest,
} from "../../features/catalog/types";
import { patientService } from "../../features/patients/patientService";
import type { PatientSummary } from "../../features/patients/types";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    createInvoice: vi.fn(),
  },
}));

vi.mock("../../features/catalog/catalogService", () => ({
  catalogService: {
    listTests: vi.fn(),
    listPanels: vi.fn(),
  },
}));

vi.mock("../../features/patients/patientService", () => ({
  patientService: {
    listPatients: vi.fn(),
  },
}));

const mockTests: DiagnosticTest[] = [
  {
    id: "test-01",
    name: "Complete Blood Count",
    code: "CBC",
    category: "hematology",
    unit: "g/dL",
    price: "850.00",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
  {
    id: "test-02",
    name: "Glycated Hemoglobin",
    code: "HBA1C",
    category: "biochemistry",
    unit: "%",
    price: "1200.00",
    is_active: true,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockPanels: DiagnosticPanel[] = [
  {
    id: "panel-01",
    name: "Cardiovascular Screen",
    code: "CARDIO",
    price: "3200.00",
    is_active: true,
    test_ids: ["test-01"],
    tests: [],
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockPatients: PatientSummary[] = [
  {
    id: "pat-123",
    mrn: "MRN-2026-00417",
    name: "Muhammad Imran",
    phone: "03001234567",
    sex: "M",
    branch_id: "00000000-0000-0000-0000-000000000001",
    is_cross_branch: false,
    created_at: "2026-01-01T00:00:00Z",
    updated_at: "2026-01-01T00:00:00Z",
  },
];

const mockCreatedInvoice: InvoiceDetail = {
  id: "inv-created-uuid",
  patient_id: "pat-123",
  patient_name: "Muhammad Imran",
  patient_mrn: "MRN-2026-00417",
  branch_id: "br-01",
  status: "unpaid",
  subtotal: "850.00",
  discount_amount: "0.00",
  total: "850.00",
  net_paid: "0.00",
  items: [
    {
      id: "line-1",
      test_id: "test-01",
      description: "Complete Blood Count",
      unit_price: "850.00",
      quantity: 1,
      line_total: "850.00",
    },
  ],
  payments: [],
  created_at: "2026-10-20T10:15:00Z",
};

describe("Screen 14: New Invoice (14-new-invoice.html & Doc 03 §5.3, §6.4)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    vi.mocked(catalogService.listTests).mockResolvedValue(mockTests);
    vi.mocked(catalogService.listPanels).mockResolvedValue(mockPanels);
    vi.mocked(patientService.listPatients).mockResolvedValue(mockPatients);
    vi.mocked(billingService.createInvoice).mockResolvedValue(
      mockCreatedInvoice,
    );
  });

  it("renders page header, breadcrumbs, and form sections", async () => {
    render(<NewInvoiceScreen />);

    expect(
      screen.getByRole("heading", { name: "New invoice" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/Draft #INV-NEW/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Patient/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Add individual test/i)).toBeInTheDocument();

    await waitFor(() => {
      expect(catalogService.listTests).toHaveBeenCalled();
      expect(catalogService.listPanels).toHaveBeenCalled();
    });
  });

  it("allows searching and selecting a patient", async () => {
    render(<NewInvoiceScreen />);

    const patientInput = screen.getByPlaceholderText(
      /Search by MRN, Name, Phone or CNIC/i,
    );
    fireEvent.change(patientInput, { target: { value: "Muhammad" } });

    await waitFor(() => {
      expect(patientService.listPatients).toHaveBeenCalledWith({
        q: "Muhammad",
      });
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });

    const selectPatientBtn = screen
      .getByText("Muhammad Imran")
      .closest("button");
    if (selectPatientBtn) fireEvent.click(selectPatientBtn);

    await waitFor(() => {
      expect(screen.getByText(/Muhammad Imran ·/i)).toBeInTheDocument();
      expect(screen.getByText(/Sex: M/i)).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: "Change patient" }),
      ).toBeInTheDocument();
    });
  });

  it("adds tests and panels to line items and calculates totals", async () => {
    render(<NewInvoiceScreen />);

    await waitFor(() => {
      expect(
        screen.getByText(/Complete Blood Count \(CBC\)/i),
      ).toBeInTheDocument();
    });

    // Select test and click Add
    const testSelect = screen.getByLabelText(/Add individual test/i);
    fireEvent.change(testSelect, { target: { value: "test-01" } });

    const addBtn = screen.getByRole("button", { name: /Add/i });
    fireEvent.click(addBtn);

    await waitFor(() => {
      expect(screen.getByTestId("invoice-subtotal")).toHaveTextContent(
        "PKR 850.00",
      );
      expect(screen.getByTestId("invoice-total")).toHaveTextContent(
        "PKR 850.00",
      );
    });
  });

  it("submits the invoice and triggers onSuccess", async () => {
    const handleSuccess = vi.fn();
    render(
      <NewInvoiceScreen onSuccess={handleSuccess} initialPatientId="pat-123" />,
    );

    await waitFor(() => {
      expect(screen.getByText(/Muhammad Imran ·/i)).toBeInTheDocument();
    });

    // Add CBC
    const testSelect = screen.getByLabelText(/Add individual test/i);
    fireEvent.change(testSelect, { target: { value: "test-01" } });
    fireEvent.click(screen.getByRole("button", { name: /Add/i }));

    const submitBtn = screen.getByRole("button", { name: /Create invoice/i });
    fireEvent.click(submitBtn);

    await waitFor(() => {
      expect(billingService.createInvoice).toHaveBeenCalledWith(
        expect.objectContaining({
          patient_id: "pat-123",
          items: expect.arrayContaining([
            expect.objectContaining({
              test_id: "test-01",
              qty: 1,
            }),
          ]),
        }),
      );
      expect(handleSuccess).toHaveBeenCalledWith(mockCreatedInvoice);
    });
  });
});
