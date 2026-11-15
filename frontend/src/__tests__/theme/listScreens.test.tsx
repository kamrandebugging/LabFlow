import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { PatientListScreen } from "../../features/patients/PatientListScreen";
import { patientService } from "../../features/patients/patientService";
import type { PatientSummary } from "../../features/patients/types";
import { billingService } from "../../features/billing/billingService";
import { InvoicesListScreen } from "../../features/billing/InvoicesListScreen";
import type { InvoiceSummary } from "../../features/billing/types";
import i18n from "../../i18n";

vi.mock("../../features/billing/billingService", () => ({
  billingService: {
    listInvoices: vi.fn(),
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    recordPayment: vi.fn(),
    cancelInvoice: vi.fn(),
  },
}));

const patientRows: PatientSummary[] = [
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
];

const invoiceRows: InvoiceSummary[] = [
  {
    id: "inv-uuid-001",
    patient_id: "pat-uuid-001",
    patient_name: "Muhammad Imran",
    patient_mrn: "MRN-2026-00417",
    branch_id: "br-01",
    branch_name: "Gulberg Branch",
    status: "paid",
    subtotal: "3850.00",
    discount_amount: "0.00",
    total: "3850.00",
    net_paid: "3850.00",
    items_summary: "Complete Blood Count, HbA1c",
    created_at: "2026-10-20T10:15:00Z",
  },
];

function patientServiceMock(
  rows: PatientSummary[],
): typeof patientService {
  return {
    ...patientService,
    listPatients: vi.fn().mockResolvedValue(rows),
    getPatient: vi.fn(),
    createPatient: vi.fn(),
    updatePatient: vi.fn(),
    deletePatient: vi.fn(),
  };
}

describe("Patients + Invoices themed list screens", () => {
  beforeEach(async () => {
    vi.clearAllMocks();
    await i18n.changeLanguage("en");
  });

  it("renders the patients header, sync badge, search, refresh and columns", async () => {
    render(
      <PatientListScreen
        service={patientServiceMock(patientRows)}
        onNewPatient={vi.fn()}
        onSelectPatient={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /patients/i }),
    ).toBeInTheDocument();
    expect(screen.getByText(/branch sync active/i)).toBeInTheDocument();
    expect(
      screen.getByRole("searchbox", { name: /search by name, phone or mrn/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /refresh list/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /new patient/i }),
    ).toBeInTheDocument();

    for (const column of [
      /^patient$/i,
      /^mrn$/i,
      /^phone$/i,
      /^branch$/i,
      /^last visit$/i,
      /^actions$/i,
    ]) {
      expect(screen.getByRole("columnheader", { name: column })).toBeInTheDocument();
    }

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
    });
  });

  it("renders the patients empty state with the existing helper line and no invented rows", async () => {
    render(
      <PatientListScreen
        service={patientServiceMock([])}
        onNewPatient={vi.fn()}
        onSelectPatient={vi.fn()}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText(/no patients found/i)).toBeInTheDocument();
    });
    expect(
      screen.getByText(/register your first patient using the button above/i),
    ).toBeInTheDocument();
    expect(screen.queryByText(/MRN-/)).not.toBeInTheDocument();
  });

  it("keeps patient search wired to the existing service query", async () => {
    const user = userEvent.setup();
    const service = patientServiceMock(patientRows);
    render(<PatientListScreen service={service} onSelectPatient={vi.fn()} />);

    await user.type(
      screen.getByRole("searchbox", { name: /search by name, phone or mrn/i }),
      "Imran",
    );

    await waitFor(() => {
      expect(service.listPatients).toHaveBeenCalledWith({ q: "Imran" });
    });
  });

  it("renders the Daily Total verbatim, including an API zero", async () => {
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: [],
      daily_total: "0.00",
    });

    render(<InvoicesListScreen />);

    expect(await screen.findByText("PKR 0.00")).toBeInTheDocument();
    expect(screen.getByText(/daily total:/i)).toBeInTheDocument();
    expect(billingService.listInvoices).toHaveBeenCalledWith({
      status: undefined,
    });
  });

  it("renders the invoices empty state, zero count and disabled pagination", async () => {
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: [],
      daily_total: "0.00",
    });

    render(<InvoicesListScreen />);

    await waitFor(() => {
      expect(
        screen.getByText(/no invoices found matching your criteria/i),
      ).toBeInTheDocument();
    });
    expect(screen.getByText(/showing 0 invoices/i)).toBeInTheDocument();
    expect(screen.queryByText(/INV-/)).not.toBeInTheDocument();

    const previous = screen.getByRole("button", { name: /^previous$/i });
    const next = screen.getByRole("button", { name: /^next$/i });
    expect(previous).toBeDisabled();
    expect(next).toBeDisabled();
    expect(previous).toHaveAttribute("aria-disabled", "true");
    expect(next).toHaveAttribute("aria-disabled", "true");
  });

  it("renders the invoice columns, status text and the status filter", async () => {
    vi.mocked(billingService.listInvoices).mockResolvedValue({
      results: invoiceRows,
      daily_total: "9999.00",
    });

    render(<InvoicesListScreen />);

    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("PKR 3850.00")).toBeInTheDocument();
    });
    expect(screen.getByText("PKR 9999.00")).toBeInTheDocument();

    expect(
      screen.getAllByText(i18n.t("status.invoice.paid")).length,
    ).toBeGreaterThan(0);
    expect(
      screen.getByRole("columnheader", { name: /invoice #/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("columnheader", { name: /total \(pkr\)/i }),
    ).toBeInTheDocument();

    const statusSelect = screen.getByLabelText(/filter by status/i);
    fireEvent.change(statusSelect, { target: { value: "unpaid" } });

    await waitFor(() => {
      expect(billingService.listInvoices).toHaveBeenCalledWith(
        expect.objectContaining({ status: "unpaid" }),
      );
    });
  });
});
