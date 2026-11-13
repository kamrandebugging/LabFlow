import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";

import { ReferenceRangesManager } from "../../features/catalog/ReferenceRangesManager";
import type { ReferenceRange } from "../../features/catalog/types";

const range: ReferenceRange = {
  id: "range-001",
  test_id: "test-001",
  sex: "B",
  age_min_days: 0,
  age_max_days: null,
  low: "13.500",
  high: "17.500",
  critical_low: null,
  critical_high: null,
  unit: "g/dL",
  effective_from: "2026-01-01",
  effective_to: null,
  created_at: "2026-01-01T00:00:00Z",
  updated_at: "2026-01-01T00:00:00Z",
};

describe("D7 — per-row critical threshold editing", () => {
  it("saves critical_low/high on the existing range without inventing values", async () => {
    const user = userEvent.setup();
    // PATCH supersedes: the successor has a new id.
    const updated: ReferenceRange = {
      ...range,
      id: "range-002",
      critical_low: "6.500",
      critical_high: null,
    };
    const service = {
      listTestRanges: vi.fn().mockResolvedValue([range]),
      createTestRange: vi.fn(),
      updateTestRange: vi.fn().mockResolvedValue(updated),
    };

    render(
      <ReferenceRangesManager testId="test-001" service={service as never} />,
    );

    await screen.findByRole("button", { name: /edit critical thresholds/i });

    await user.click(
      screen.getByRole("button", { name: /edit critical thresholds/i }),
    );
    const low = screen.getByLabelText("Critical low for range-001");
    await user.clear(low);
    await user.type(low, "6.500");
    await user.click(screen.getByRole("button", { name: "Save" }));

    await waitFor(() => {
      expect(service.updateTestRange).toHaveBeenCalledWith(
        "test-001",
        "range-001",
        { critical_low: "6.500", critical_high: null },
      );
    });
    expect(await screen.findByText(/6\.500/)).toBeInTheDocument();
    // Only the successor remains; the superseded row is not duplicated.
    expect(
      screen.getAllByRole("button", { name: /edit critical thresholds/i }),
    ).toHaveLength(1);
  });
});
