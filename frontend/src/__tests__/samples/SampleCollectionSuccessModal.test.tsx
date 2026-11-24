import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent, waitFor } from "@testing-library/react";
import { SampleCollectionSuccessModal } from "../../features/samples/components/SampleCollectionSuccessModal";
import type {
  SampleCreatedResponse,
  SampleCollectionDraft,
} from "../../features/samples/types";

describe("SampleCollectionSuccessModal", () => {
  const mockSample: SampleCreatedResponse = {
    id: "s-12345",
    accession_id: "MUS20261124000001",
    invoice_id: "inv-999",
    branch_id: "br-001",
    status: "collected",
    collected_at: "2026-11-24T06:45:00Z",
    collected_by: "technician@labflow.pk",
  };

  const mockDraft: SampleCollectionDraft = {
    invoice_id: "inv-999",
    invoice_number: "INV-999-001",
    patient_id: "pat-101",
    patient_name: "Muhammad Usman",
    patient_mrn: "MRN-HQ1-000041",
    patient_sex: "M",
    branch_id: "br-001",
    branch_name: "Main Branch",
    selected_item_ids: ["item-1", "item-2"],
    test_labels: ["Complete Blood Count (CBC)", "Serum Ferritin"],
    tubes_required: [
      {
        type: "Lavender (EDTA)",
        specimen: "Whole Blood",
        color: "#8b5cf6",
        count: 1,
      },
      { type: "Gold / SST", specimen: "Serum", color: "#eab308", count: 1 },
    ],
    collected_at: "2026-11-24T06:45:00Z",
    collected_by: "technician@labflow.pk",
    notes: "Patient was fasting.",
  };

  it("renders when open with all sample, patient, and custody details", () => {
    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        collectorName="Usman Phlebotomist"
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", { name: /Sample Collected Successfully/i }),
    ).toBeInTheDocument();
    expect(screen.getByText("MUS20261124000001")).toBeInTheDocument();
    expect(screen.getByText("Muhammad Usman")).toBeInTheDocument();
    expect(screen.getByText("MRN-HQ1-000041")).toBeInTheDocument();
    expect(screen.getByText("technician@labflow.pk")).toBeInTheDocument();
    expect(screen.getByText("Complete Blood Count (CBC)")).toBeInTheDocument();
    expect(screen.getByText("Serum Ferritin")).toBeInTheDocument();
    expect(screen.getByText(/1x Lavender \(EDTA\)/i)).toBeInTheDocument();
    expect(screen.getByText(/1x Gold \/ SST/i)).toBeInTheDocument();
    expect(screen.getByText("Patient was fasting.")).toBeInTheDocument();
  });

  it("does not render when isOpen is false", () => {
    const { container } = render(
      <SampleCollectionSuccessModal
        isOpen={false}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );
    expect(container).toBeEmptyDOMElement();
  });

  it("calls onPrintLabel with sample id when Print Barcode Label is clicked", () => {
    const handlePrint = vi.fn();
    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={handlePrint}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Print Barcode Label/i }),
    );
    expect(handlePrint).toHaveBeenCalledWith("s-12345");
  });

  it("calls onCollectAnother when Collect Another Sample is clicked", () => {
    const handleCollectAnother = vi.fn();
    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={handleCollectAnother}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Collect Another Sample/i }),
    );
    expect(handleCollectAnother).toHaveBeenCalledTimes(1);
  });

  it("calls onViewDetails with sample id when View Sample Details is clicked", () => {
    const handleView = vi.fn();
    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={handleView}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /View Sample Details/i }),
    );
    expect(handleView).toHaveBeenCalledWith("s-12345");
  });

  it("calls onClose when Close button or Back to Samples List is clicked", () => {
    const handleClose = vi.fn();
    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={handleClose}
      />,
    );

    fireEvent.click(
      screen.getByRole("button", { name: /Back to Samples List/i }),
    );
    expect(handleClose).toHaveBeenCalledTimes(1);

    fireEvent.click(screen.getByRole("button", { name: /Close dialog/i }));
    expect(handleClose).toHaveBeenCalledTimes(2);
  });

  it("copies accession id to clipboard when Copy is clicked", async () => {
    const writeTextMock = vi.fn().mockResolvedValue(undefined);
    Object.assign(navigator, {
      clipboard: {
        writeText: writeTextMock,
      },
    });

    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    const copyBtn = screen.getByRole("button", { name: /Copy/i });
    fireEvent.click(copyBtn);

    expect(writeTextMock).toHaveBeenCalledWith("MUS20261124000001");
    await waitFor(() => {
      expect(screen.getByText("Copied!")).toBeInTheDocument();
    });
  });

  it("renders translated Urdu text when language is set to 'ur'", async () => {
    const { default: i18n } = await import("../../i18n");
    await i18n.changeLanguage("ur");

    render(
      <SampleCollectionSuccessModal
        isOpen={true}
        sample={mockSample}
        draft={mockDraft}
        onPrintLabel={vi.fn()}
        onViewDetails={vi.fn()}
        onCollectAnother={vi.fn()}
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("heading", {
        name: /نمونہ کامیابی سے وصول کر لیا گیا/i,
      }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /بار کوڈ لیبل پرنٹ کریں/i }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /ایک اور نمونہ وصول کریں/i }),
    ).toBeInTheDocument();

    // Reset back to English
    await i18n.changeLanguage("en");
  });
});
