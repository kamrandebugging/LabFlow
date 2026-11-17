import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { billingService } from "../../features/billing/billingService";
import { InvoiceDetailScreen } from "../../features/billing/InvoiceDetailScreen";
import { NewInvoiceScreen } from "../../features/billing/NewInvoiceScreen";
import type { InvoiceDetail } from "../../features/billing/types";
import { catalogService } from "../../features/catalog/catalogService";
import { patientService } from "../../features/patients/patientService";
import { PatientDetailsScreen } from "../../features/patients/PatientDetailsScreen";
import { RegisterPatientScreen } from "../../features/patients/RegisterPatientScreen";
import type { PatientDetail } from "../../features/patients/types";
import i18n from "../../i18n";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    recordPayment: vi.fn(),
    recordRefund: vi.fn(),
    cancelInvoice: vi.fn(),
  },
}));

vi.mock("../../features/catalog/catalogService", () => ({
  catalogService: {
    listTests: vi.fn(),
    listPanels: vi.fn(),
  },
}));

const patientRecord: PatientDetail = {
  id: "pat-uuid-001",
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
  consents: [],
  contacts: [],
};

const invoiceDetail: InvoiceDetail = {
  id: "0891a000-0000-0000-0000-000000000000",
  invoice_number: "INV-0891A000",
  patient_id: "pat-uuid-001",
  patient_name: "Muhammad Imran",
  patient_mrn: "MRN-2026-00417",
  patient_phone: "+92 300 1234567",
  branch_id: "br-01",
  branch_name: "Gulberg Branch",
  status: "partial",
  subtotal: "2000.00",
  discount_amount: "200.00",
  discount_reason: "staff family",
  total: "1800.00",
  net_paid: "1000.00",
  items: [
    {
      id: "item-1",
      test_id: "test-haem-01",
      description: "CBC (Complete Blood Count)",
      unit_price: "800.00",
      quantity: 1,
      line_total: "800.00",
    },
    {
      id: "item-2",
      test_id: "test-bio-14",
      description: "HbA1c (Glycated Hemoglobin)",
      unit_price: "1200.00",
      quantity: 1,
      line_total: "1200.00",
    },
  ],
  payments: [],
  created_at: "2026-10-20T10:15:00Z",
};

function patientServiceMock(): typeof patientService {
  return {
    ...patientService,
    getPatient: vi.fn().mockResolvedValue(patientRecord),
    listPatients: vi.fn(),
    createPatient: vi.fn(),
    updatePatient: vi.fn(),
    deletePatient: vi.fn(),
  };
}

describe("Themed patient + invoice form and detail screens", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("en");
    vi.mocked(catalogService.listTests).mockResolvedValue([]);
    vi.mocked(catalogService.listPanels).mockResolvedValue([]);
    vi.mocked(billingService.getInvoice).mockResolvedValue(invoiceDetail);
  });

  it("register form keeps its labels, required markers and empty values", () => {
    render(
      <RegisterPatientScreen
        service={patientServiceMock()}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /register patient/i }),
    ).toBeInTheDocument();
    expect(screen.getByLabelText(/full name/i)).toHaveValue("");
    expect(screen.getByLabelText(/phone/i)).toHaveValue("");
    expect(screen.getByLabelText(/date of birth/i)).toHaveValue("");
    expect(screen.getByLabelText(/whatsapp number/i)).toHaveValue("");
    expect(
      screen.getByRole("radiogroup", { name: /sex/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /register patient/i }),
    ).toBeInTheDocument();

    // Full name, phone and sex are the only required fields on this screen.
    expect(screen.getAllByText("*")).toHaveLength(3);
    expect(screen.queryByText(/MRN-/)).not.toBeInTheDocument();
  });

  it("patient detail renders the API record verbatim, including missing consent", async () => {
    render(
      <PatientDetailsScreen
        patientId={patientRecord.id}
        service={patientServiceMock()}
      />,
    );

    expect(
      await screen.findByRole("heading", { name: "Muhammad Imran" }),
    ).toBeInTheDocument();
    expect(screen.getAllByText("MRN-2026-00417").length).toBeGreaterThan(0);
    expect(screen.getByText("+92 300 1234567")).toBeInTheDocument();
    expect(screen.getByText("Gulberg Branch")).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t("patients:details.active")),
    ).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t("patients:details.consent_none")),
    ).toBeInTheDocument();
  });

  it("new invoice renders the empty panel and API-zero totals without inventing lines", async () => {
    render(<NewInvoiceScreen onSuccess={vi.fn()} onCancel={vi.fn()} />);

    expect(
      screen.getByLabelText(
        new RegExp(i18n.t("billing:new.patient_label"), "i"),
      ),
    ).toBeInTheDocument();
    await waitFor(() => {
      expect(screen.getAllByText("PKR 0.00")).toHaveLength(2);
    });
    expect(screen.getByTestId("invoice-subtotal")).toHaveTextContent(
      "PKR 0.00",
    );
    expect(screen.getByTestId("invoice-total")).toHaveTextContent("PKR 0.00");
    expect(screen.queryByTestId("selected-items-list")).not.toBeInTheDocument();
    expect(screen.getByRole("button", { name: /add/i })).toBeInTheDocument();
  });

  it("invoice detail renders line items, totals and status words verbatim", async () => {
    render(<InvoiceDetailScreen invoiceId={invoiceDetail.id} />);

    expect(
      await screen.findByRole("heading", { name: "INV-0891A000" }),
    ).toBeInTheDocument();
    expect(screen.getByText("CBC (Complete Blood Count)")).toBeInTheDocument();
    expect(screen.getByText("HbA1c (Glycated Hemoglobin)")).toBeInTheDocument();
    expect(screen.getAllByText("PKR 800.00").length).toBeGreaterThan(0);
    expect(screen.getAllByText("PKR 1200.00").length).toBeGreaterThan(0);
    expect(screen.getByText("PKR 2000.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 1800.00")).toBeInTheDocument();
    expect(screen.getByText("PKR 1000.00")).toBeInTheDocument();
    expect(
      screen.getByText(i18n.t("status.invoice.partial")),
    ).toBeInTheDocument();
    expect(screen.getByText(/staff family/i)).toBeInTheDocument();
  });
});
