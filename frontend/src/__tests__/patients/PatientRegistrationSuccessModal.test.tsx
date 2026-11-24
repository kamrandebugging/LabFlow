import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { PatientRegistrationSuccessModal } from "../../features/patients/components/PatientRegistrationSuccessModal";
import type { PatientSummary } from "../../features/patients/types";

describe("PatientRegistrationSuccessModal", () => {
  const mockPatient: PatientSummary = {
    id: "pat-999",
    mrn: "MRN-26-000412",
    name: "Zainab Tariq",
    sex: "F",
    phone: "03001234567",
    date_of_birth: "1998-05-14",
    branch_id: "br-01",
    branch_name: "Punjab Clinical Labs - Main",
    referral_partner_name: "Al-Razi Hospital",
    created_at: "2026-11-24T07:30:00Z",
    updated_at: "2026-11-24T07:30:00Z",
    is_cross_branch: false,
  };

  it("renders when open with all patient demographics and MRN", () => {
    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onCreateInvoice={vi.fn()}
        onViewProfile={vi.fn()}
        onRegisterAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /Patient Registered Successfully/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("MRN-26-000412")).toBeInTheDocument();
    expect(screen.getByText("Zainab Tariq")).toBeInTheDocument();
    expect(screen.getByText("03001234567")).toBeInTheDocument();
    expect(screen.getByText("Punjab Clinical Labs - Main")).toBeInTheDocument();
    expect(screen.getByText("Al-Razi Hospital")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <PatientRegistrationSuccessModal
        isOpen={false}
        patient={mockPatient}
        onClose={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onCreateInvoice when Create Invoice is clicked", () => {
    const handleInvoice = vi.fn();
    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onCreateInvoice={handleInvoice}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(screen.getByRole("button", { name: /Create Invoice/i }));
    expect(handleInvoice).toHaveBeenCalledWith("pat-999");
  });

  it("calls onRegisterAnother when Register Another Patient is clicked", () => {
    const handleRegisterAnother = vi.fn();
    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onRegisterAnother={handleRegisterAnother}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Register Another Patient/i }),
    );
    expect(handleRegisterAnother).toHaveBeenCalledTimes(1);
  });

  it("calls onViewProfile when View Patient Profile is clicked", () => {
    const handleView = vi.fn();
    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onViewProfile={handleView}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /View Patient Profile/i }),
    );
    expect(handleView).toHaveBeenCalledWith("pat-999");
  });

  it("calls onClose when Close button or Back to Patients List is clicked", () => {
    const handleClose = vi.fn();
    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onClose={handleClose}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Back to Patients List/i }),
    );
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByTestId("close-patient-modal-btn"));
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it("copies MRN to clipboard when Copy is clicked", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onClose={vi.fn()}
      />,
    );

    const copyBtn = screen.getByTestId("copy-mrn-btn");
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith("MRN-26-000412");
    await waitFor(() => {
      expect(screen.getByText("Copied!")).toBeInTheDocument();
    });
  });

  it("renders translated Urdu text when language is set to 'ur'", async () => {
    const { default: i18n } = await import("../../i18n");
    await i18n.changeLanguage("ur");

    render(
      <PatientRegistrationSuccessModal
        isOpen={true}
        patient={mockPatient}
        onCreateInvoice={vi.fn()}
        onRegisterAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: /مریض کامیابی سے رجسٹر ہو گیا/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /انوائس بنائیں/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ایک اور مریض رجسٹر کریں/i }),
    ).toBeInTheDocument();

    // Reset back to English
    await i18n.changeLanguage("en");
  });
});
