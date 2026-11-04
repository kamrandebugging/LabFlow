import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import {
  SampleAccessioningListScreen,
  CollectSampleStep1Screen,
  CollectSampleStep2Screen,
  SampleDetailScreen,
  SampleLabelScreen,
  type SampleDetail,
  type SampleSummary,
  type SampleLabelData,
  type SampleCreatedResponse,
} from "../../features/samples";

const mockSampleSummary: SampleSummary = {
  id: "sample-001",
  accession_id: "CDL20261020000041",
  invoice_id: "inv-001",
  patient_id: "pt-001",
  patient_name: "Muhammad Imran",
  patient_mrn: "MRN-2026-00417",
  patient_sex: "M",
  patient_age_years: 34,
  branch_id: "br-001",
  branch_name: "Gulberg Branch",
  status: "collected",
  tests: ["Complete Blood Count (CBC)", "HbA1c"],
  collected_at: "2026-10-20T09:15:00Z",
  age_display: "0h 45m",
};

const mockSampleDetail: SampleDetail = {
  ...mockSampleSummary,
  patient_dob: "1992-04-12",
  collected_by: "Phleb. Bilal Ahmed",
  custody_location: "Gulberg Branch — bench A",
  bench_code: "BENCH-01",
  sample_tests: [
    {
      id: "st-1",
      test_id: "t-1",
      test_name: "CBC",
      test_code: "CBC",
      invoice_item_id: "ii-1",
      specimen_type: "Whole Blood",
      tube_type: "Lavender EDTA",
    },
    {
      id: "st-2",
      test_id: "t-2",
      test_name: "HbA1c",
      test_code: "HBA1C",
      invoice_item_id: "ii-2",
      specimen_type: "Fluoride Plasma",
      tube_type: "Grey Fluoride",
    },
  ],
  events: [
    {
      id: "evt-1",
      event: "COLLECTED",
      actor: "Bilal Ahmed",
      branch: { id: "br-001", code: "GLB", name: "Gulberg Branch" },
      timestamp: "2026-10-20T09:15:00Z",
      payload: { note: "Specimen drawn and labeled at desk 01" },
    },
  ],
};

const mockLabelData: SampleLabelData = {
  accession_id: "CDL20261020000041",
  patient_name: "Muhammad Imran",
  mrn: "MRN-2026-00417",
  date_of_birth: "1992-04-12",
  collected_at: "2026-10-20T09:15:00Z",
  collected_by: "Bilal Ahmed",
  branch_name: "Gulberg Branch",
  tests: ["CBC", "HbA1c"],
  barcode: {
    symbology: "code128",
    payload: "CDL20261020000041",
  },
};

const mockCreatedResponse: SampleCreatedResponse = {
  id: "sample-001",
  accession_id: "CDL20261020000041",
  invoice_id: "inv-001",
  branch_id: "br-001",
  status: "collected",
  collected_at: "2026-10-20T09:15:00Z",
  collected_by: "Bilal Ahmed",
};

describe("Screen 16: SampleAccessioningListScreen", () => {
  it("renders sample accessions and filter controls", async () => {
    const mockService = {
      listSamples: vi.fn().mockResolvedValue({
        results: [mockSampleSummary],
        total: 1,
      }),
    };

    render(
      <SampleAccessioningListScreen
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
    });
  });

  it("calls onCollectNew when collect sample button is clicked", async () => {
    const mockCollect = vi.fn();
    const mockService = {
      listSamples: vi.fn().mockResolvedValue({
        results: [mockSampleSummary],
        total: 1,
      }),
    };

    render(
      <SampleAccessioningListScreen
        onCollectNew={mockCollect}
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
    });

    const collectBtn = screen.getByRole("button", {
      name: /^collect sample$/i,
    });
    fireEvent.click(collectBtn);
    expect(mockCollect).toHaveBeenCalledTimes(1);
  });
});

describe("Screen 17: CollectSampleStep1Screen", () => {
  it("renders step 1 collection form with patient and tests", async () => {
    const mockBillingService = {
      getInvoice: vi.fn().mockResolvedValue({
        id: "inv-001",
        invoice_number: "INV-2026-0891",
        patient_id: "pt-001",
        patient_name: "Muhammad Imran",
        patient_mrn: "MRN-2026-00417",
        patient_sex: "M",
        patient_age_display: "34y",
        branch_id: "br-001",
        branch_name: "Gulberg Branch",
        status: "settled",
        items: [
          {
            id: "ii-01",
            item_type: "test",
            name: "Complete Blood Count (CBC)",
            unit_price: "1200.00",
            quantity: 1,
            total_price: "1200.00",
          },
        ],
      }),
    };

    render(
      <CollectSampleStep1Screen
        preselectedInvoiceId="inv-001"
        // @ts-expect-error partial mock
        billingServiceInstance={mockBillingService}
      />,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("heading", { name: "Collect sample" }),
      ).toBeInTheDocument();
      expect(
        screen.getByText("Complete Blood Count (CBC)"),
      ).toBeInTheDocument();
    });
  });
});

describe("Screen 18: CollectSampleStep2Screen", () => {
  it("renders step 2 phlebotomy tubes verification and commits collection", async () => {
    const mockCollect = vi.fn().mockResolvedValue(mockCreatedResponse);
    const mockConfirmed = vi.fn();

    const draft = {
      invoice_id: "inv-001",
      patient_id: "pt-001",
      patient_name: "Muhammad Imran",
      patient_mrn: "MRN-2026-00417",
      branch_id: "br-001",
      branch_name: "Gulberg Branch",
      selected_item_ids: ["ii-01"],
      test_labels: ["Complete Blood Count (CBC)"],
      tubes_required: [
        {
          type: "Lavender top (EDTA)",
          color: "#7e22ce",
          specimen: "Whole Blood",
          count: 1,
        },
      ],
      collected_at: "2026-10-20T09:15:00Z",
      collected_by: "Bilal Ahmed",
    };

    render(
      <CollectSampleStep2Screen
        draft={draft}
        onConfirmed={mockConfirmed}
        // @ts-expect-error partial mock
        service={{ collectSample: mockCollect }}
      />,
    );

    expect(
      screen.getByRole("heading", { name: "Collect sample" }),
    ).toBeInTheDocument();
    expect(screen.getByText(/EDTA tube/i)).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", {
      name: /^collect sample$/i,
    });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockCollect).toHaveBeenCalledTimes(1);
    });
  });
});

describe("Screen 19: SampleDetailScreen", () => {
  it("renders sample information card and event timeline", async () => {
    const mockService = {
      getSample: vi.fn().mockResolvedValue(mockSampleDetail),
      receiveSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "received" }),
      rejectSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "rejected" }),
      transferSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "open" }),
    };

    render(
      <SampleDetailScreen
        sampleId="sample-001"
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(screen.getByText("Sample information")).toBeInTheDocument();
      expect(screen.getByText("Event timeline")).toBeInTheDocument();
      expect(screen.getByText("Gulberg Branch — bench A")).toBeInTheDocument();
    });
  });

  it("handles receiving sample and updates state", async () => {
    const mockService = {
      getSample: vi.fn().mockResolvedValue(mockSampleDetail),
      receiveSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "received" }),
    };

    render(
      <SampleDetailScreen
        sampleId="sample-001"
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
    });

    const receiveBtn = screen.getByRole("button", { name: /receive/i });
    fireEvent.click(receiveBtn);

    await waitFor(() => {
      expect(mockService.receiveSample).toHaveBeenCalledWith("sample-001");
    });
  });

  it("opens reject modal and confirms sample rejection", async () => {
    const mockService = {
      getSample: vi.fn().mockResolvedValue(mockSampleDetail),
      rejectSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "rejected" }),
    };

    render(
      <SampleDetailScreen
        sampleId="sample-001"
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
    });

    const rejectBtn = screen.getByRole("button", { name: /reject/i });
    fireEvent.click(rejectBtn);

    expect(screen.getByText("Reject Specimen")).toBeInTheDocument();
    const confirmRejectBtn = screen.getByRole("button", {
      name: /confirm rejection/i,
    });
    fireEvent.click(confirmRejectBtn);

    await waitFor(() => {
      expect(mockService.rejectSample).toHaveBeenCalled();
    });
  });
});

describe("Screen 20: SampleLabelScreen", () => {
  beforeEach(() => {
    window.print = vi.fn();
  });

  it("renders 50x25mm thermal label preview with Code128 barcode", async () => {
    const mockService = {
      getLabel: vi.fn().mockResolvedValue(mockLabelData),
    };

    render(
      <SampleLabelScreen
        sampleId="sample-001"
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Sample label")).toBeInTheDocument();
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(
        screen.getByText("Thermal Specimen Label (50mm × 25mm)"),
      ).toBeInTheDocument();
    });
  });

  it("triggers window.print when print button is clicked", async () => {
    const mockService = {
      getLabel: vi.fn().mockResolvedValue(mockLabelData),
    };

    render(
      <SampleLabelScreen
        sampleId="sample-001"
        // @ts-expect-error partial mock
        service={mockService}
      />,
    );

    await waitFor(() => {
      expect(screen.getByText("Sample label")).toBeInTheDocument();
    });

    const printBtn = screen.getByRole("button", { name: /^print$/i });
    fireEvent.click(printBtn);

    expect(window.print).toHaveBeenCalledTimes(1);
  });
});
