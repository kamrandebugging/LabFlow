import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
  within,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { InvoiceDetailScreen } from "@/features/billing/InvoiceDetailScreen";
import { NewInvoiceScreen } from "@/features/billing/NewInvoiceScreen";
import type { InvoiceDetail } from "@/features/billing/types";
import { PatientDetailsScreen } from "@/features/patients/PatientDetailsScreen";
import { PatientHistoryScreen } from "@/features/patients/PatientHistoryScreen";
import { RegisterPatientScreen } from "@/features/patients/RegisterPatientScreen";
import type { PatientDetail, PatientSummary } from "@/features/patients/types";
import { billingService } from "@/features/billing/billingService";
import { catalogService } from "@/features/catalog/catalogService";
import { patientService } from "@/features/patients/patientService";
import i18n from "@/i18n";

vi.mock("@/features/billing/billingService", () => ({
  billingService: {
    getInvoice: vi.fn(),
    createInvoice: vi.fn(),
    recordPayment: vi.fn(),
    cancelInvoice: vi.fn(),
  },
}));

vi.mock("@/features/catalog/catalogService", () => ({
  catalogService: {
    listTests: vi.fn(),
    listPanels: vi.fn(),
  },
}));

vi.mock("@/features/patients/patientService", () => ({
  patientService: {
    listPatients: vi.fn(),
    getPatient: vi.fn(),
    createPatient: vi.fn(),
    updatePatient: vi.fn(),
    deletePatient: vi.fn(),
  },
  DuplicatePatientError: class DuplicatePatientError extends Error {},
}));

const patient: PatientSummary = {
  id: "pat-123",
  mrn: "MRN-2026-00417",
  name: "Muhammad Imran",
  phone: "03001234567",
  sex: "M",
  branch_id: "00000000-0000-0000-0000-000000000001",
  is_cross_branch: false,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

const secondPatient: PatientSummary = {
  ...patient,
  id: "pat-456",
  mrn: "MRN-26-000005",
  name: "Usman Tariq",
  phone: "03007654321",
};

const partialInvoice: InvoiceDetail = {
  id: "inv-1",
  invoice_number: "INV-A5FE2C34",
  patient_id: patient.id,
  patient_name: patient.name,
  patient_mrn: patient.mrn,
  patient_phone: "+92 300 1234567",
  branch_id: "br-01",
  branch_name: "Gulberg Branch",
  status: "partial",
  subtotal: "2000.00",
  discount_amount: "0.00",
  total: "2000.00",
  net_paid: "1200.00",
  items: [
    {
      id: "item-1",
      test_id: "test-01",
      description: "Complete Blood Count",
      unit_price: "2000.00",
      quantity: 1,
      line_total: "2000.00",
    },
  ],
  payments: [
    {
      id: "pay-1",
      invoice_id: "inv-1",
      kind: "payment",
      method: "cash",
      amount: "1200.00",
      created_at: "2026-10-20T10:20:00Z",
    },
  ],
  created_at: "2026-10-20T10:15:00Z",
};

const paidInvoice: InvoiceDetail = {
  ...partialInvoice,
  status: "paid",
  net_paid: "2000.00",
  payments: [
    {
      id: "pay-1",
      invoice_id: "inv-1",
      kind: "payment",
      method: "cash",
      amount: "2000.00",
      created_at: "2026-10-20T10:20:00Z",
    },
  ],
};

const patientRecord: PatientDetail = {
  id: patient.id,
  mrn: patient.mrn,
  name: patient.name,
  sex: "M",
  phone: patient.phone,
  date_of_birth: "1992-05-10",
  branch_id: "br-01",
  branch_name: "Gulberg Branch",
  created_at: "2026-01-14T10:00:00Z",
  updated_at: "2026-10-20T10:00:00Z",
  is_cross_branch: false,
  contacts: [],
  consents: [],
};

beforeEach(() => {
  vi.clearAllMocks();
  vi.mocked(catalogService.listTests).mockResolvedValue([
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
  ]);
  vi.mocked(catalogService.listPanels).mockResolvedValue([]);
  vi.mocked(patientService.listPatients).mockResolvedValue([]);
  vi.mocked(patientService.getPatient).mockResolvedValue(patientRecord);
  vi.mocked(billingService.getInvoice).mockResolvedValue(partialInvoice);
});

afterEach(async () => {
  await i18n.changeLanguage("en");
});

describe("Item 1 — invoice footer aligns to the inline-end, Cancel first", () => {
  it("orders the footer Cancel → Create and still submits the same payload", async () => {
    const onSuccess = vi.fn();
    vi.mocked(billingService.createInvoice).mockResolvedValue(partialInvoice);

    render(<NewInvoiceScreen onSuccess={onSuccess} />);

    const testSelect = screen.getByLabelText(/Add individual test/i);
    await waitFor(() => expect(testSelect).toBeEnabled());
    fireEvent.change(testSelect, { target: { value: "CBC" } });
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /Complete Blood Count/ }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("option", { name: /Complete Blood Count/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));

    const footerButtons = screen
      .getByRole("button", { name: /^Cancel$/i })
      .parentElement?.querySelectorAll("button");
    expect(Array.from(footerButtons ?? []).map((b) => b.textContent)).toEqual([
      "Cancel",
      "Create Invoice",
    ]);

    fireEvent.change(
      screen.getByPlaceholderText(/Search by MRN, Name, Phone or CNIC/i),
      { target: { value: "Muhammad" } },
    );
    vi.mocked(patientService.listPatients).mockResolvedValue([patient]);
    await waitFor(() => {
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    });
    fireEvent.click(screen.getByText("Muhammad Imran").closest("button")!);

    fireEvent.click(screen.getByRole("button", { name: /Create invoice/i }));

    await waitFor(() => {
      expect(billingService.createInvoice).toHaveBeenCalledWith(
        expect.objectContaining({
          patient_id: "pat-123",
          items: [expect.objectContaining({ test_id: "test-01", qty: 1 })],
          discount_amount: "0.00",
          discount_reason: null,
        }),
      );
    });
    expect(onSuccess).toHaveBeenCalled();
  });
});

describe("Item 2 — New invoice zero-results state", () => {
  it("shows one non-option status row and wires the register action", async () => {
    const onRegisterPatient = vi.fn();
    render(<NewInvoiceScreen onRegisterPatient={onRegisterPatient} />);

    fireEvent.change(
      screen.getByPlaceholderText(/Search by MRN, Name, Phone or CNIC/i),
      { target: { value: "nobody" } },
    );

    await waitFor(
      () => {
        expect(
          screen.getByText("No patients found for 'nobody'."),
        ).toBeInTheDocument();
      },
      { timeout: 3000 },
    );

    const registerLink = within(screen.getByRole("status")).getByRole(
      "button",
      { name: /Register new patient/i },
    );
    fireEvent.click(registerLink);
    expect(onRegisterPatient).toHaveBeenCalledTimes(1);

    // The status row is not a selectable patient option.
    const statusRow = screen.getByRole("status");
    expect(statusRow.closest("button")).toBeNull();
    expect(statusRow.querySelector("button")).toBe(registerLink);
  });

  it("renders result rows and no status row when patients match", async () => {
    vi.mocked(patientService.listPatients).mockResolvedValue([
      patient,
      secondPatient,
    ]);
    render(<NewInvoiceScreen onRegisterPatient={vi.fn()} />);

    fireEvent.change(
      screen.getByPlaceholderText(/Search by MRN, Name, Phone or CNIC/i),
      { target: { value: "Mu" } },
    );

    await waitFor(
      () => {
        expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      },
      { timeout: 3000 },
    );
    expect(screen.getByText("Usman Tariq")).toBeInTheDocument();
    expect(screen.queryByText(/No patients found/)).not.toBeInTheDocument();
  });
});

describe("Item 3 — Register patient: Use primary phone", () => {
  const renderRegister = () =>
    render(
      <RegisterPatientScreen
        service={patientService}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

  it("copies Phone into WhatsApp and never auto-consents", async () => {
    const user = userEvent.setup();
    renderRegister();

    const chip = screen.getByRole("button", { name: /Use primary phone/i });
    expect(chip).toBeDisabled();

    await user.type(screen.getByLabelText(/^Phone/i), "03001234567");
    expect(chip).not.toBeDisabled();
    await user.click(chip);

    expect(screen.getByLabelText(/whatsapp number/i)).toHaveValue(
      "03001234567",
    );
    expect(screen.getByLabelText(/consent/i)).not.toBeChecked();

    // Fields stay independent afterwards.
    await user.type(screen.getByLabelText(/whatsapp number/i), "9");
    expect(screen.getByLabelText(/^Phone/i)).toHaveValue("03001234567");
  });
});

describe("Item 4 — Register patient: error focus and submission lock", () => {
  it("moves focus to the alert on a failed submit", async () => {
    const user = userEvent.setup();
    const failing = {
      ...patientService,
      createPatient: vi.fn().mockRejectedValue(new Error("boom")),
    };

    render(<RegisterPatientScreen service={failing} onSuccess={vi.fn()} />);

    await user.type(screen.getByLabelText(/full name/i), "Tariq Mahmood");
    await user.type(screen.getByLabelText(/^Phone/i), "03009876543");
    await user.click(screen.getByRole("button", { name: /register patient/i }));

    const alert = await screen.findByRole("alert");
    await waitFor(() => expect(alert).toHaveFocus());
  });

  it("locks the form while the request is pending", async () => {
    let resolveCreate: (value: PatientSummary) => void = () => {};
    const pending = {
      ...patientService,
      createPatient: vi.fn(
        () =>
          new Promise<PatientSummary>((resolve) => {
            resolveCreate = resolve;
          }),
      ),
    };

    render(
      <RegisterPatientScreen
        service={pending}
        onSuccess={vi.fn()}
        onCancel={vi.fn()}
      />,
    );

    fireEvent.change(screen.getByLabelText(/full name/i), {
      target: { value: "Tariq Mahmood" },
    });
    fireEvent.change(screen.getByLabelText(/^Phone/i), {
      target: { value: "03009876543" },
    });
    fireEvent.click(screen.getByRole("button", { name: /register patient/i }));

    await waitFor(() => expect(pending.createPatient).toHaveBeenCalledTimes(1));

    const form = document.querySelector("form#patientRegistrationForm");
    expect(form).toHaveAttribute("aria-busy", "true");
    expect(screen.getByLabelText(/full name/i)).toHaveAttribute("readonly");
    expect(screen.getByLabelText(/^Phone/i)).toHaveAttribute("readonly");
    expect(screen.getByLabelText(/whatsapp number/i)).toHaveAttribute(
      "readonly",
    );
    expect(screen.getByRole("button", { name: /^Cancel$/i })).toBeDisabled();
    expect(screen.getByRole("button", { name: /registering/i })).toBeDisabled();

    await act(async () => {
      resolveCreate({ ...patient });
    });

    await waitFor(() =>
      expect(screen.getByLabelText(/full name/i)).not.toHaveAttribute(
        "readonly",
      ),
    );
  });
});

describe("Item 6 — Invoice detail payment toast", () => {
  it("confirms a recorded payment with the formatted amount", async () => {
    vi.mocked(billingService.recordPayment).mockResolvedValue({
      id: "pay-2",
      invoice_id: partialInvoice.id,
      kind: "payment",
      method: "cash",
      amount: "800.00",
      created_at: "2026-10-20T10:35:00Z",
    });

    render(<InvoiceDetailScreen invoiceId={partialInvoice.id} />);

    await waitFor(() =>
      expect(
        screen.getByRole("button", { name: /Pay full balance/i }),
      ).toBeInTheDocument(),
    );
    fireEvent.click(screen.getByRole("button", { name: /Pay full balance/i }));
    fireEvent.click(screen.getByRole("button", { name: /Record payment/i }));

    const toast = await screen.findByRole("status");
    expect(toast).toHaveTextContent(/PKR 800\.00/);
    expect(toast).toHaveTextContent(/Payment/);
  });
});

describe("Item 7 — Discount prefix and live Max helper", () => {
  it("keeps the PKR prefix decorative and submits a bare number", async () => {
    vi.mocked(billingService.createInvoice).mockResolvedValue(partialInvoice);
    vi.mocked(patientService.listPatients).mockResolvedValue([patient]);

    const { container } = render(
      <NewInvoiceScreen onSuccess={vi.fn()} initialPatientId="pat-123" />,
    );

    await waitFor(() =>
      expect(screen.getByText(/Muhammad Imran ·/i)).toBeInTheDocument(),
    );

    const testSelect7 = screen.getByLabelText(/Add individual test/i);
    await waitFor(() => expect(testSelect7).toBeEnabled());
    fireEvent.change(testSelect7, { target: { value: "CBC" } });
    await waitFor(() => {
      expect(
        screen.getByRole("option", { name: /Complete Blood Count/ }),
      ).toBeInTheDocument();
    });
    fireEvent.click(
      screen.getByRole("option", { name: /Complete Blood Count/ }),
    );
    fireEvent.click(screen.getByRole("button", { name: /^Add$/i }));

    const prefix = container.querySelector('[aria-hidden="true"]');
    const discountGroup = screen.getByLabelText(/Discount Amount/i)
      .parentElement as HTMLElement;
    const decorativePkr = discountGroup.querySelector('[aria-hidden="true"]');
    expect(prefix).not.toBeNull();
    expect(decorativePkr).not.toBeNull();
    expect(decorativePkr?.textContent).toBe("PKR");

    // Live helper follows the subtotal.
    expect(screen.getByText(/Max: PKR 850\.00/)).toBeInTheDocument();

    fireEvent.change(screen.getByLabelText(/Discount Amount/i), {
      target: { value: "50" },
    });
    fireEvent.change(screen.getByPlaceholderText(/Staff discount/i), {
      target: { value: "Staff family" },
    });
    fireEvent.click(screen.getByRole("button", { name: /Create invoice/i }));

    await waitFor(() => {
      const payload = vi.mocked(billingService.createInvoice).mock
        .calls[0]?.[0];
      expect(payload?.discount_amount).toBe("50.00");
      expect(payload?.discount_amount).not.toContain("PKR");
    });
  });
});

describe("Item 8 — Pay full balance chip and refund collapse", () => {
  it("fills the exact balance and collapses refund while a balance is due", async () => {
    render(<InvoiceDetailScreen invoiceId={partialInvoice.id} />);

    const amount = await screen.findByLabelText(/Amount \(PKR\)/i);
    expect(amount).toHaveValue(null);

    fireEvent.click(screen.getByRole("button", { name: /Pay full balance/i }));
    expect(amount).toHaveValue(800);

    expect(
      screen.queryByPlaceholderText(/Clinical or billing justification/i),
    ).not.toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: /Issue a refund/i }));
    expect(
      screen.getByPlaceholderText(/Clinical or billing justification/i),
    ).toBeInTheDocument();
  });

  it("keeps the refund form expanded when the invoice is fully paid", async () => {
    vi.mocked(billingService.getInvoice).mockResolvedValue(paidInvoice);
    render(<InvoiceDetailScreen invoiceId={paidInvoice.id} />);

    expect(
      await screen.findByPlaceholderText(/Clinical or billing justification/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByRole("button", { name: /Issue a refund/i }),
    ).not.toBeInTheDocument();
  });
});

describe("Item 9 — Refund confirmation modal", () => {
  const openRefundForm = async () => {
    render(<InvoiceDetailScreen invoiceId={partialInvoice.id} />);
    await screen.findByRole("button", { name: /Issue a refund/i });
    fireEvent.click(screen.getByRole("button", { name: /Issue a refund/i }));
    fireEvent.change(screen.getByPlaceholderText("0.00"), {
      target: { value: "200.00" },
    });
    fireEvent.change(
      screen.getByPlaceholderText(/Clinical or billing justification/i),
      { target: { value: "Test cancelled by doctor" } },
    );
    fireEvent.click(screen.getByRole("button", { name: /Record refund/i }));
  };

  it("restates the refund and calls the API exactly once on confirm", async () => {
    vi.mocked(billingService.recordPayment).mockResolvedValue({
      id: "ref-1",
      invoice_id: partialInvoice.id,
      kind: "refund",
      method: "cash",
      amount: "200.00",
      reference: "Test cancelled by doctor",
      created_at: "2026-10-20T10:40:00Z",
    });

    await openRefundForm();

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("PKR 200.00");
    expect(dialog).toHaveTextContent("Cash");
    expect(dialog).toHaveTextContent("Test cancelled by doctor");
    expect(billingService.recordPayment).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Confirm Refund/i }));

    await waitFor(() =>
      expect(billingService.recordPayment).toHaveBeenCalledTimes(1),
    );
    expect(billingService.recordPayment).toHaveBeenCalledWith(
      partialInvoice.id,
      expect.objectContaining({
        kind: "refund",
        amount: "200.00",
        reference: "Test cancelled by doctor",
      }),
    );
  });

  it("fires no call on Back and returns focus to the refund submit", async () => {
    await openRefundForm();

    const submit = screen.getByRole("button", { name: /Record refund/i });
    fireEvent.click(screen.getByRole("button", { name: /^Back$/i }));

    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(billingService.recordPayment).not.toHaveBeenCalled();
    expect(submit).toHaveFocus();
  });
});

describe("Item 10 — Patient delete confirmation modal", () => {
  it("gates delete behind the modal and keeps the record on Keep patient", async () => {
    const onBack = vi.fn();
    render(
      <PatientDetailsScreen
        patientId={patientRecord.id}
        service={patientService}
        canDelete
        onBack={onBack}
      />,
    );

    await screen.findByRole("heading", { name: "Muhammad Imran" });
    fireEvent.click(screen.getByRole("button", { name: /Delete patient/i }));

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveTextContent("Delete Patient Record?");
    expect(dialog).toHaveTextContent("Muhammad Imran");
    expect(dialog).toHaveTextContent("MRN-2026-00417");

    fireEvent.click(screen.getByRole("button", { name: /Keep patient/i }));
    expect(patientService.deletePatient).not.toHaveBeenCalled();
    expect(onBack).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole("button", { name: /Delete patient/i }));
    fireEvent.click(screen.getByRole("button", { name: /Confirm Delete/i }));

    await waitFor(() =>
      expect(patientService.deletePatient).toHaveBeenCalledWith(
        patientRecord.id,
      ),
    );
  });

  it("does not render the delete control without the canDelete permission", async () => {
    render(
      <PatientDetailsScreen
        patientId={patientRecord.id}
        service={patientService}
      />,
    );

    await screen.findByRole("heading", { name: "Muhammad Imran" });
    expect(
      screen.queryByRole("button", { name: /Delete patient/i }),
    ).not.toBeInTheDocument();
  });
});

describe("Item 11 — RTL-safe MRN, phone and PKR chips", () => {
  it("marks identifiers and currency as ltr on every screen", async () => {
    // New invoice: currency + MRN rows
    vi.mocked(patientService.listPatients).mockResolvedValue([patient]);
    const { unmount } = render(<NewInvoiceScreen />);
    await waitFor(() =>
      expect(screen.getByTestId("invoice-total")).toBeTruthy(),
    );
    expect(screen.getByTestId("invoice-total")).toHaveAttribute("dir", "ltr");
    expect(screen.getByTestId("invoice-subtotal")).toHaveAttribute(
      "dir",
      "ltr",
    );
    unmount();

    // Invoice detail: currency chips
    const invoiceView = render(
      <InvoiceDetailScreen invoiceId={partialInvoice.id} />,
    );
    await screen.findByRole("heading", { name: "INV-A5FE2C34" });
    expect(
      screen.getByText("PKR 800.00").closest('[dir="ltr"]'),
    ).not.toBeNull();
    expect(
      screen.getByText(/MRN: MRN-2026-00417/).closest('[dir="ltr"]'),
    ).not.toBeNull();
    invoiceView.unmount();

    // Patient detail: MRN + phone
    const detail = render(
      <PatientDetailsScreen
        patientId={patientRecord.id}
        service={patientService}
      />,
    );
    await screen.findByRole("heading", { name: "Muhammad Imran" });
    expect(
      screen.getAllByText("MRN-2026-00417")[0]?.closest('[dir="ltr"]'),
    ).not.toBeNull();
    expect(
      screen.getByText("03001234567").closest('[dir="ltr"]'),
    ).not.toBeNull();
    detail.unmount();

    // Patient history: MRN + phone
    const history = render(
      <PatientHistoryScreen
        patientId={patientRecord.id}
        service={patientService}
      />,
    );
    await waitFor(() =>
      expect(screen.getAllByText("MRN-2026-00417").length).toBeGreaterThan(0),
    );
    expect(
      screen.getAllByText("MRN-2026-00417")[0]?.closest('[dir="ltr"]'),
    ).not.toBeNull();
    expect(
      screen.getByText("03001234567").closest('[dir="ltr"]'),
    ).not.toBeNull();
    history.unmount();

    // Register: phone and WhatsApp inputs
    const register = render(
      <RegisterPatientScreen service={patientService} onSuccess={vi.fn()} />,
    );
    expect(screen.getByLabelText(/^Phone/i)).toHaveAttribute("dir", "ltr");
    expect(screen.getByLabelText(/whatsapp number/i)).toHaveAttribute(
      "dir",
      "ltr",
    );
    register.unmount();
  });
});

describe("Item 13 — Cancel invoice modal focus management", () => {
  const unpaid: InvoiceDetail = {
    ...partialInvoice,
    status: "unpaid",
    net_paid: "0.00",
    payments: [],
  };

  it("moves focus inside, traps Tab, closes on Escape and restores focus", async () => {
    vi.mocked(billingService.getInvoice).mockResolvedValue(unpaid);
    render(<InvoiceDetailScreen invoiceId={unpaid.id} />);

    const trigger = await screen.findByRole("button", {
      name: /Cancel invoice/i,
    });
    trigger.focus();
    fireEvent.click(trigger);

    const dialog = screen.getByRole("dialog");
    expect(dialog).toHaveAttribute("aria-modal", "true");
    expect(dialog).toHaveAttribute("aria-labelledby");
    await waitFor(() =>
      expect(dialog.contains(document.activeElement)).toBe(true),
    );

    const focusables = dialog.querySelectorAll<HTMLElement>("button, textarea");
    const first = focusables[0] as HTMLElement;
    const last = focusables[focusables.length - 1] as HTMLElement;

    // A reason is required before Confirm is enabled, exactly as today.
    fireEvent.change(screen.getByPlaceholderText(/Patient did not arrive/i), {
      target: { value: "Ordered by mistake" },
    });
    expect(last).not.toBeDisabled();

    last.focus();
    fireEvent.keyDown(document, { key: "Tab" });
    expect(document.activeElement).toBe(first);

    first.focus();
    fireEvent.keyDown(document, { key: "Tab", shiftKey: true });
    expect(document.activeElement).toBe(last);

    fireEvent.keyDown(document, { key: "Escape" });
    expect(screen.queryByRole("dialog")).not.toBeInTheDocument();
    expect(trigger).toHaveFocus();
    expect(billingService.cancelInvoice).not.toHaveBeenCalled();
  });
});

describe("Item 14 — History notice copy in both locales", () => {
  it("shows the plain sentence in EN and UR without changing the key names", async () => {
    render(
      <PatientHistoryScreen
        patientId={patientRecord.id}
        service={patientService}
      />,
    );

    expect(
      await screen.findByText(/showing visit history for this patient only/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText(/partitioned ledger scope/i),
    ).not.toBeInTheDocument();

    await act(async () => {
      await i18n.changeLanguage("ur");
    });

    expect(
      screen.getByText(i18n.t("patients:history.ledger_scope_label")),
    ).toBeInTheDocument();
    expect(i18n.t("patients:history.ledger_scope_label")).toBe(
      "صرف اسی مریض کی وزٹ ہسٹری دکھائی جا رہی ہے",
    );
  });
});
