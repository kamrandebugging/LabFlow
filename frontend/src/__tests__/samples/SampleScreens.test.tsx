import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { MemoryRouter } from "react-router-dom";
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
import { useAuthStore } from "../../features/auth/authStore";

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
  collected_by: "Bilal Ahmed",
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
      required_volume_ml: 3,
    },
    {
      id: "st-2",
      test_id: "t-2",
      test_name: "HbA1c",
      test_code: "HBA1C",
      invoice_item_id: "ii-2",
      specimen_type: "Fluoride Plasma",
      tube_type: "Grey Fluoride",
      required_volume_ml: 2,
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
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "u-1",
        email: "tech@labflow.pk",
        name: "Usman Tariq",
        role: "technician",
        branch_ids: ["br-001"],
      },
    });
  });

  it("renders sample accessions, KPI row, and tabs", async () => {
    const mockService = {
      listSamples: vi.fn().mockResolvedValue({
        results: [mockSampleSummary],
        total: 1,
      }),
      listAwaitingCollection: vi.fn().mockResolvedValue({
        results: [
          {
            invoice_id: "inv-001",
            invoice_item_id: "ii-01",
            patient_id: "pt-001",
            patient_name: "Muhammad Imran",
            patient_mrn: "MRN-2026-00417",
            branch_id: "br-001",
            branch_name: "Gulberg Branch",
            ordered_at: "2026-10-20T08:00:00Z",
            test_id: "t-1",
            test_name: "Complete Blood Count",
            test_code: "CBC",
            panel_id: null,
            panel_name: null,
            description: "Complete Blood Count (CBC)",
            status: "awaiting_collection",
          },
        ],
        total: 1,
      }),
      listTransfers: vi.fn().mockResolvedValue({ results: [], total: 0 }),
    };

    render(
      <MemoryRouter>
        <SampleAccessioningListScreen
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Samples")).toBeInTheDocument();
      expect(screen.getAllByText("Awaiting collection").length).toBeGreaterThan(
        0,
      );
      expect(screen.getByText("All samples")).toBeInTheDocument();
      expect(screen.getByText("Transfers")).toBeInTheDocument();
    });

    // Awaiting tab renders awaiting row and Collect -> action
    expect(screen.getByText("Muhammad Imran")).toBeInTheDocument();
    expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: /Collect →/i }),
    ).toBeInTheDocument();
  });

  it("calls onCollectNew when Collect sample button is clicked", async () => {
    const mockCollect = vi.fn();
    const mockService = {
      listSamples: vi.fn().mockResolvedValue({
        results: [mockSampleSummary],
        total: 1,
      }),
      listAwaitingCollection: vi
        .fn()
        .mockResolvedValue({ results: [], total: 0 }),
      listTransfers: vi.fn().mockResolvedValue({ results: [], total: 0 }),
    };

    render(
      <MemoryRouter>
        <SampleAccessioningListScreen
          onCollectNew={mockCollect}
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Samples")).toBeInTheDocument();
    });

    const collectBtn = screen.getByRole("button", {
      name: /Collect sample/i,
    });
    fireEvent.click(collectBtn);
    expect(mockCollect).toHaveBeenCalledTimes(1);
  });

  it("does not poison the main page when the optional transfers queue returns 404", async () => {
    const notFound = Object.assign(new Error("not found"), {
      status: 404,
      code: "not_found",
    });
    const mockService = {
      listSamples: vi.fn().mockResolvedValue({
        results: [mockSampleSummary],
        total: 1,
      }),
      listAwaitingCollection: vi
        .fn()
        .mockResolvedValue({ results: [], total: 0 }),
      listTransfers: vi.fn().mockRejectedValue(notFound),
    };

    render(
      <MemoryRouter>
        <SampleAccessioningListScreen
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(
        screen.getByRole("tab", { name: /All samples 1/i }),
      ).toBeInTheDocument();
    });

    expect(screen.queryByRole("alert")).toBeNull();
    expect(
      screen.queryByText("The requested record was not found."),
    ).toBeNull();
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
        patient_age: "34",
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

    const onContinueMock = vi.fn();

    render(
      <CollectSampleStep1Screen
        preselectedInvoiceId="inv-001"
        onContinue={onContinueMock}
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
      expect(screen.getByText("MRN-2026-00417")).toBeInTheDocument();
    });

    const continueBtn = screen.getByRole("button", {
      name: /Continue to Step 2/i,
    });
    expect(continueBtn).not.toBeDisabled();
    fireEvent.click(continueBtn);
    expect(onContinueMock).toHaveBeenCalled();
  });
});

describe("Screen 18: CollectSampleStep2Screen", () => {
  it("renders step 2 phlebotomy verification and commits collection", async () => {
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
      notes: "Fasting confirmed",
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
    expect(screen.getByText(/Lavender top \(EDTA\)/i)).toBeInTheDocument();
    expect(
      screen.getByText(
        /Recorded automatically: server time on confirm \/ logged-in user/i,
      ),
    ).toBeInTheDocument();

    const confirmBtn = screen.getByRole("button", {
      name: /^Collect sample$/i,
    });
    fireEvent.click(confirmBtn);

    await waitFor(() => {
      expect(mockCollect).toHaveBeenCalledTimes(1);
      expect(mockConfirmed).toHaveBeenCalledWith(mockCreatedResponse);
      expect(
        screen.getByRole("heading", {
          name: /Sample Collected Successfully/i,
        }),
      ).toBeInTheDocument();
      expect(
        screen.getByText(mockCreatedResponse.accession_id),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Print Barcode Label/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Collect Another Sample/i }),
      ).toBeInTheDocument();
    });
  });
});

describe("Screen 19: SampleDetailScreen", () => {
  beforeEach(() => {
    useAuthStore.setState({
      user: {
        id: "u-1",
        email: "tech@labflow.pk",
        name: "Usman Tariq",
        role: "technician",
        branch_ids: ["br-001"],
      },
    });
  });

  it("renders full page with NO drawer/dialog on load and displays custody timeline", async () => {
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
      <MemoryRouter>
        <SampleDetailScreen
          sampleId="sample-001"
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(screen.getByText("Specimen Status & Custody")).toBeInTheDocument();
      expect(screen.getByText("Patient Identity")).toBeInTheDocument();
      expect(screen.getByText("Chain of Custody Timeline")).toBeInTheDocument();
    });

    // Hard ban on drawers: verify no drawer or modal dialog is rendered on initial load
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("handles receiving sample and updates state", async () => {
    const mockService = {
      getSample: vi.fn().mockResolvedValue(mockSampleDetail),
      receiveSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "received" }),
    };

    render(
      <MemoryRouter>
        <SampleDetailScreen
          sampleId="sample-001"
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
    });

    const receiveBtn = screen.getByRole("button", { name: /receive sample/i });
    fireEvent.click(receiveBtn);

    await waitFor(() => {
      expect(mockService.receiveSample).toHaveBeenCalledWith("sample-001");
    });
  });

  it("opens reject modal with all reasons and confirms rejection", async () => {
    const mockService = {
      getSample: vi.fn().mockResolvedValue(mockSampleDetail),
      rejectSample: vi
        .fn()
        .mockResolvedValue({ id: "sample-001", status: "rejected" }),
    };

    render(
      <MemoryRouter>
        <SampleDetailScreen
          sampleId="sample-001"
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
    });

    const rejectBtn = screen.getByRole("button", { name: /reject sample/i });
    fireEvent.click(rejectBtn);

    expect(screen.getByText("Reject Specimen")).toBeInTheDocument();

    // Select reason
    const select = screen.getByLabelText(/rejection reason code/i);
    fireEvent.change(select, { target: { value: "hemolyzed" } });

    const confirmRejectBtn = screen.getByRole("button", {
      name: /confirm rejection/i,
    });
    expect(confirmRejectBtn).not.toBeDisabled();
    fireEvent.click(confirmRejectBtn);

    await waitFor(() => {
      expect(mockService.rejectSample).toHaveBeenCalledWith("sample-001", {
        reason_code: "hemolyzed",
        note: undefined,
      });
    });
  });
});

describe("Screen 20: SampleLabelScreen", () => {
  beforeEach(() => {
    window.print = vi.fn();
  });

  it("renders thermal label preview with tenant header and barcode", async () => {
    const mockService = {
      getLabel: vi.fn().mockResolvedValue(mockLabelData),
      printLabel: vi.fn().mockResolvedValue(mockLabelData),
    };

    render(
      <MemoryRouter>
        <SampleLabelScreen
          sampleId="sample-001"
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Sample label")).toBeInTheDocument();
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(screen.getByText("LabFlow")).toBeInTheDocument();
      expect(screen.getByText("Software by LabFlow")).toBeInTheDocument();
    });
  });

  it("calls printLabel (POST) and triggers window.print when print button is clicked", async () => {
    const mockService = {
      getLabel: vi.fn().mockResolvedValue(mockLabelData),
      printLabel: vi.fn().mockResolvedValue(mockLabelData),
    };

    render(
      <MemoryRouter>
        <SampleLabelScreen
          sampleId="sample-001"
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(screen.getByText("Sample label")).toBeInTheDocument();
    });

    const printBtn = screen.getByRole("button", { name: /^print$/i });
    fireEvent.click(printBtn);

    await waitFor(() => {
      expect(mockService.printLabel).toHaveBeenCalledWith("sample-001");
      expect(window.print).toHaveBeenCalledTimes(1);
    });
  });

  it("loads and prints all selected labels in bulk mode", async () => {
    const bulkLabels: SampleLabelData[] = [
      { ...mockLabelData, accession_id: "CDL20261020000041" },
      {
        ...mockLabelData,
        accession_id: "CDL20261020000042",
        patient_name: "Fatima Noor",
        barcode: { symbology: "code128", payload: "CDL20261020000042" },
      },
      {
        ...mockLabelData,
        accession_id: "CDL20261020000043",
        patient_name: "Bilal Ahmed",
        barcode: { symbology: "code128", payload: "CDL20261020000043" },
      },
    ];
    const mockService = {
      getLabelsBulk: vi.fn().mockResolvedValue(bulkLabels),
      printLabelsBulk: vi.fn().mockResolvedValue(bulkLabels),
    };

    render(
      <MemoryRouter>
        <SampleLabelScreen
          sampleIds={["s-1", "s-2", "s-3"]}
          // @ts-expect-error partial mock
          service={mockService}
        />
      </MemoryRouter>,
    );

    await waitFor(() => {
      expect(mockService.getLabelsBulk).toHaveBeenCalledWith([
        "s-1",
        "s-2",
        "s-3",
      ]);
      expect(screen.getAllByText("CDL20261020000041").length).toBeGreaterThan(
        0,
      );
      expect(screen.getAllByText("CDL20261020000042").length).toBeGreaterThan(
        0,
      );
      expect(screen.getAllByText("CDL20261020000043").length).toBeGreaterThan(
        0,
      );
    });

    fireEvent.click(screen.getByRole("button", { name: /^print$/i }));
    await waitFor(() => {
      expect(mockService.printLabelsBulk).toHaveBeenCalledWith([
        "s-1",
        "s-2",
        "s-3",
      ]);
      expect(window.print).toHaveBeenCalledTimes(1);
    });
  });
});
