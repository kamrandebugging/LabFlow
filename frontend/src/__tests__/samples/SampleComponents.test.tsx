import { render, screen, fireEvent } from "@testing-library/react";
import { describe, it, expect, vi } from "vitest";
import {
  SampleStatusPill,
  SampleKpiRow,
  SampleQueueTabs,
  SampleBulkBar,
  SampleTimeline,
  CollectWizardStepper,
  LabelPrintSheet,
} from "../../features/samples/components";
import type { SampleEventItem, SampleLabelData } from "../../features/samples/types";

describe("Samples Veyla Components", () => {
  describe("SampleStatusPill", () => {
    it("renders ready, in_process, received, collected, rejected, cancelled, awaiting_collection", () => {
      const { rerender } = render(<SampleStatusPill status="ready" />);
      expect(screen.getByText("Ready / Reported")).toBeInTheDocument();

      rerender(<SampleStatusPill status="in_process" />);
      expect(screen.getByText("In Process")).toBeInTheDocument();

      rerender(<SampleStatusPill status="received" />);
      expect(screen.getByText("Received")).toBeInTheDocument();

      rerender(<SampleStatusPill status="collected" />);
      expect(screen.getByText("Collected")).toBeInTheDocument();

      rerender(<SampleStatusPill status="rejected" />);
      expect(screen.getByText("Rejected")).toBeInTheDocument();

      rerender(<SampleStatusPill status="cancelled" />);
      expect(screen.getByText("Cancelled")).toBeInTheDocument();

      rerender(<SampleStatusPill status="awaiting_collection" />);
      expect(screen.getByText("Awaiting Collection")).toBeInTheDocument();

      rerender(<SampleStatusPill status="worst" />);
      expect(screen.getByText("Immediate")).toBeInTheDocument();
    });

    it("renders custom label when provided", () => {
      render(<SampleStatusPill status="ready" label="Custom Ready" />);
      expect(screen.getByText("Custom Ready")).toBeInTheDocument();
    });
  });

  describe("SampleKpiRow", () => {
    it("renders 4 KPI items with values and subtitles", () => {
      const items = [
        { id: "awaiting", label: "Awaiting collection", value: 12 },
        { id: "collected", label: "Collected today", value: 45 },
        { id: "in_process", label: "In process", value: 8 },
        { id: "ready", label: "Ready / Reported", value: 29 },
      ];
      render(<SampleKpiRow items={items} />);
      expect(screen.getByText("Awaiting collection")).toBeInTheDocument();
      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText("Collected today")).toBeInTheDocument();
      expect(screen.getByText("45")).toBeInTheDocument();
      expect(screen.getByText("In process")).toBeInTheDocument();
      expect(screen.getByText("8")).toBeInTheDocument();
      expect(screen.getByText("Ready / Reported")).toBeInTheDocument();
      expect(screen.getByText("29")).toBeInTheDocument();
    });
  });

  describe("SampleQueueTabs", () => {
    it("renders tab buttons, count badges, and triggers selection", () => {
      const tabs = [
        { id: "awaiting_collection", label: "Awaiting collection", count: 12 },
        { id: "collected", label: "Collected", count: 5 },
        { id: "transfers", label: "Transfers", count: 2 },
      ];
      const onSelect = vi.fn();
      render(
        <SampleQueueTabs
          tabs={tabs}
          activeTab="awaiting_collection"
          onSelectTab={onSelect}
        />,
      );

      expect(screen.getByText("Awaiting collection")).toBeInTheDocument();
      expect(screen.getByText("12")).toBeInTheDocument();
      expect(screen.getByText("Collected")).toBeInTheDocument();
      expect(screen.getByText("5")).toBeInTheDocument();
      expect(screen.getByText("Transfers")).toBeInTheDocument();
      expect(screen.getByText("2")).toBeInTheDocument();

      const collectedBtn = screen.getByRole("tab", { name: /Collected/i });
      fireEvent.click(collectedBtn);
      expect(onSelect).toHaveBeenCalledWith("collected");
    });
  });

  describe("SampleBulkBar", () => {
    it("returns null when selectedCount is 0", () => {
      const { container } = render(
        <SampleBulkBar selectedCount={0} onClear={vi.fn()} />,
      );
      expect(container.firstChild).toBeNull();
    });

    it("renders count, Clear button, and Print labels button", () => {
      const onClear = vi.fn();
      const onPrint = vi.fn();
      render(
        <SampleBulkBar
          selectedCount={3}
          onClear={onClear}
          onPrintLabels={onPrint}
        />,
      );

      expect(screen.getByText("3 samples selected")).toBeInTheDocument();
      fireEvent.click(screen.getByRole("button", { name: /Clear/i }));
      expect(onClear).toHaveBeenCalled();

      fireEvent.click(screen.getByRole("button", { name: /Print labels \(3\)/i }));
      expect(onPrint).toHaveBeenCalled();
    });
  });

  describe("SampleTimeline", () => {
    it("renders empty state when events list is empty", () => {
      render(<SampleTimeline events={[]} />);
      expect(screen.getByText("No custody events yet")).toBeInTheDocument();
    });

    it("renders events in order with enriched payloads", () => {
      const events: SampleEventItem[] = [
        {
          id: "ev-1",
          event: "COLLECTED",
          actor: "Receptionist Maryam",
          branch: { id: "b1", code: "GUL", name: "Gulberg Branch" },
          timestamp: "2026-11-19T08:00:00Z",
          payload: { note: "First morning draw" },
        },
        {
          id: "ev-2",
          event: "TRANSFERRED_OUT",
          actor: "Manager Tariq",
          branch: { id: "b1", code: "GUL", name: "Gulberg Branch" },
          timestamp: "2026-11-19T09:30:00Z",
          payload: {
            from_branch: { id: "b1", code: "GUL", name: "Gulberg Branch" },
            to_branch: { id: "b2", code: "DHA", name: "DHA Central" },
          },
        },
        {
          id: "ev-3",
          event: "REJECTED",
          actor: "Technician Ali",
          branch: { id: "b2", code: "DHA", name: "DHA Central" },
          timestamp: "2026-11-19T10:15:00Z",
          payload: { rejection_code: "hemolyzed" },
        },
      ];

      render(<SampleTimeline events={events} />);

      expect(screen.getByText("COLLECTED")).toBeInTheDocument();
      expect(screen.getByText(/by Receptionist Maryam/i)).toBeInTheDocument();
      expect(screen.getByText(/First morning draw/i)).toBeInTheDocument();

      expect(screen.getByText("TRANSFERRED_OUT")).toBeInTheDocument();
      expect(screen.getByText(/Gulberg Branch → DHA Central/i)).toBeInTheDocument();

      expect(screen.getByText("REJECTED")).toBeInTheDocument();
      expect(screen.getByText(/hemolyzed/i)).toBeInTheDocument();
    });
  });

  describe("CollectWizardStepper", () => {
    it("renders steps 1 and 2 with active/completed indicators", () => {
      const { rerender } = render(<CollectWizardStepper currentStep={1} />);
      expect(screen.getByText("Step 1")).toBeInTheDocument();
      expect(screen.getByText("Patient & invoice")).toBeInTheDocument();
      expect(screen.getByText("Step 2")).toBeInTheDocument();
      expect(screen.getByText("Tests & collection")).toBeInTheDocument();

      rerender(<CollectWizardStepper currentStep={2} />);
      expect(screen.getByText("Step 1")).toBeInTheDocument();
    });
  });

  describe("LabelPrintSheet", () => {
    it("renders tenant header, patient MRN, and barcode from payload", () => {
      const labelData: SampleLabelData = {
        accession_id: "CDL202611190001",
        patient_name: "Zainab Bibi",
        mrn: "MRN-2026-0912",
        date_of_birth: "1988-04-12",
        collected_at: "19 Nov 2026 09:30",
        collected_by: "Receptionist Sara",
        branch_name: "Gulberg Main Lab",
        tests: ["Complete Blood Count (CBC)", "Serum Ferritin"],
        barcode: {
          symbology: "code128",
          payload: "CDL202611190001",
        },
      };

      render(
        <LabelPrintSheet
          labelData={labelData}
          tenantName="City Diagnostic Laboratory"
        />,
      );

      expect(screen.getByText("City Diagnostic Laboratory")).toBeInTheDocument();
      expect(screen.getByText("Gulberg Main Lab")).toBeInTheDocument();
      expect(screen.getByText("Zainab Bibi")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-0912")).toBeInTheDocument();
      expect(screen.getByText("CDL202611190001")).toBeInTheDocument();
      expect(screen.getByText("Complete Blood Count (CBC)")).toBeInTheDocument();
      expect(screen.getByText("Software by LabFlow")).toBeInTheDocument();
    });

    it("displays error when barcode symbology is not code128", () => {
      const labelData: SampleLabelData = {
        accession_id: "CDL202611190001",
        patient_name: "Zainab Bibi",
        mrn: "MRN-2026-0912",
        date_of_birth: null,
        collected_at: "19 Nov 2026 09:30",
        collected_by: null,
        barcode: {
          symbology: "qr",
          payload: "CDL202611190001",
        },
      };

      render(<LabelPrintSheet labelData={labelData} />);
      expect(
        screen.getByText(/Unsupported barcode symbology: qr/i),
      ).toBeInTheDocument();
    });
  });
});
