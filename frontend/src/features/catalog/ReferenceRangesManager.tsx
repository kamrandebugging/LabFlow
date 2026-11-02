import React, { useCallback, useEffect, useState } from "react";
import { Plus, RefreshCw, AlertCircle, X, Archive } from "lucide-react";
import { catalogService } from "./catalogService";
import type {
  RangeSex,
  ReferenceRange,
  ReferenceRangeCreateInput,
} from "./types";

interface ReferenceRangesManagerProps {
  testId: string;
  testCode?: string;
  service?: typeof catalogService;
}

const SEX_LABELS: Record<RangeSex, string> = {
  M: "Male",
  F: "Female",
  B: "Both",
};

function formatBand(range: ReferenceRange): string {
  const max = range.age_max_days === null ? "∞" : String(range.age_max_days);
  return `${range.age_min_days}–${max} days`;
}

function formatBounds(range: ReferenceRange): string {
  const low = range.low ?? "–";
  const high = range.high ?? "–";
  return `${low} – ${high} ${range.unit}`;
}

function emptyForm(): ReferenceRangeCreateInput {
  return {
    sex: "B",
    age_min_days: 0,
    age_max_days: null,
    low: "",
    high: "",
    critical_low: "",
    critical_high: "",
    unit: "",
    effective_from: new Date().toISOString().slice(0, 10),
    effective_to: null,
  };
}

export function ReferenceRangesManager({
  testId,
  testCode,
  service = catalogService,
}: ReferenceRangesManagerProps): JSX.Element {
  const [ranges, setRanges] = useState<ReferenceRange[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [form, setForm] = useState<ReferenceRangeCreateInput>(emptyForm());
  const [isSaving, setIsSaving] = useState(false);
  const [retiringId, setRetiringId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listTestRanges(testId);
      setRanges(data);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load ranges.");
    } finally {
      setIsLoading(false);
    }
  }, [service, testId]);

  useEffect(() => {
    void load();
  }, [load]);

  function setField<K extends keyof ReferenceRangeCreateInput>(
    key: K,
    value: ReferenceRangeCreateInput[K],
  ): void {
    setForm((prev) => ({ ...prev, [key]: value }));
  }

  async function handleCreate(e: React.FormEvent): Promise<void> {
    e.preventDefault();
    setIsSaving(true);
    setError(null);
    try {
      const created = await service.createTestRange(testId, {
        ...form,
        low: form.low?.trim() ? form.low : null,
        high: form.high?.trim() ? form.high : null,
        critical_low: form.critical_low?.trim() ? form.critical_low : null,
        critical_high: form.critical_high?.trim() ? form.critical_high : null,
        effective_to:
          form.effective_to && form.effective_to.trim()
            ? form.effective_to
            : null,
      });
      setRanges((prev) => [created, ...prev]);
      setForm(emptyForm());
      setIsFormOpen(false);
    } catch (err) {
      const coded = err as Error & { code?: string };
      setError(
        coded.code === "overlapping_range"
          ? "This range overlaps an existing range for the same sex, age band and effective dates."
          : err instanceof Error
            ? err.message
            : "Failed to create range.",
      );
    } finally {
      setIsSaving(false);
    }
  }

  async function handleRetire(rangeId: string): Promise<void> {
    setRetiringId(rangeId);
    setError(null);
    try {
      const updated = await service.updateTestRange(testId, rangeId, {
        effective_to: new Date().toISOString().slice(0, 10),
      });
      setRanges((prev) => prev.map((r) => (r.id === rangeId ? updated : r)));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to retire range.");
    } finally {
      setRetiringId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          Reference Ranges{testCode ? ` — ${testCode}` : ""}
        </h3>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            aria-label="Reload ranges"
          >
            <RefreshCw className="w-4 h-4" />
          </button>
          <button
            type="button"
            onClick={() => setIsFormOpen((v) => !v)}
            className="inline-flex items-center gap-1.5 px-3 py-2 bg-[#005c55] hover:bg-[#0f766e] text-white text-sm font-medium rounded-lg shadow-sm transition-colors cursor-pointer"
          >
            {isFormOpen ? (
              <X className="w-4 h-4" />
            ) : (
              <Plus className="w-4 h-4" />
            )}
            {isFormOpen ? "Cancel" : "Add Range"}
          </button>
        </div>
      </div>

      {error && (
        <div className="flex items-center gap-2 p-3 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm">
          <AlertCircle className="w-4 h-4 shrink-0" />
          <span>{error}</span>
        </div>
      )}

      {isFormOpen && (
        <form
          onSubmit={(e) => void handleCreate(e)}
          className="grid grid-cols-2 md:grid-cols-4 gap-3 p-4 rounded-lg bg-slate-50 border border-slate-200"
        >
          <label className="text-xs font-medium text-slate-600">
            Sex
            <select
              value={form.sex}
              onChange={(e) => setField("sex", e.target.value as RangeSex)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            >
              {(Object.keys(SEX_LABELS) as RangeSex[]).map((s) => (
                <option key={s} value={s}>
                  {SEX_LABELS[s]}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            Age min (days)
            <input
              type="number"
              min={0}
              value={form.age_min_days}
              onChange={(e) => setField("age_min_days", Number(e.target.value))}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
              required
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Age max (days, blank = ∞)
            <input
              type="number"
              min={0}
              value={form.age_max_days ?? ""}
              onChange={(e) =>
                setField(
                  "age_max_days",
                  e.target.value === "" ? null : Number(e.target.value),
                )
              }
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Unit
            <input
              type="text"
              value={form.unit}
              onChange={(e) => setField("unit", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
              required
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Low
            <input
              type="text"
              inputMode="decimal"
              value={form.low ?? ""}
              onChange={(e) => setField("low", e.target.value)}
              placeholder="e.g. 13.500"
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            High
            <input
              type="text"
              inputMode="decimal"
              value={form.high ?? ""}
              onChange={(e) => setField("high", e.target.value)}
              placeholder="e.g. 17.500"
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Critical low
            <input
              type="text"
              inputMode="decimal"
              value={form.critical_low ?? ""}
              onChange={(e) => setField("critical_low", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Critical high
            <input
              type="text"
              inputMode="decimal"
              value={form.critical_high ?? ""}
              onChange={(e) => setField("critical_high", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Effective from
            <input
              type="date"
              value={form.effective_from}
              onChange={(e) => setField("effective_from", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
              required
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            Effective to (blank = open)
            <input
              type="date"
              value={form.effective_to ?? ""}
              onChange={(e) =>
                setField(
                  "effective_to",
                  e.target.value === "" ? null : e.target.value,
                )
              }
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <div className="col-span-2 md:col-span-4 flex justify-end">
            <button
              type="submit"
              disabled={isSaving}
              className="inline-flex items-center gap-1.5 px-4 py-2 bg-[#005c55] hover:bg-[#0f766e] disabled:opacity-50 text-white text-sm font-medium rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              {isSaving ? "Saving…" : "Save Range"}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="h-24 rounded-lg bg-slate-100 border border-slate-200" />
      ) : ranges.length === 0 ? (
        <p className="text-sm text-slate-500 py-6 text-center border border-dashed border-slate-200 rounded-lg">
          No reference ranges defined for this test yet.
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-left text-xs font-medium text-slate-500">
                <th className="px-3 py-2">Sex</th>
                <th className="px-3 py-2">Age band</th>
                <th className="px-3 py-2">Range</th>
                <th className="px-3 py-2">Critical</th>
                <th className="px-3 py-2">Effective</th>
                <th className="px-3 py-2 text-right">Actions</th>
              </tr>
            </thead>
            <tbody>
              {ranges.map((range) => (
                <tr
                  key={range.id}
                  className="border-t border-slate-100 text-slate-800"
                >
                  <td className="px-3 py-2 font-medium">
                    {SEX_LABELS[range.sex]}
                  </td>
                  <td className="px-3 py-2">{formatBand(range)}</td>
                  <td className="px-3 py-2">{formatBounds(range)}</td>
                  <td className="px-3 py-2 text-slate-500">
                    {range.critical_low ?? "–"} – {range.critical_high ?? "–"}
                  </td>
                  <td className="px-3 py-2 text-slate-500">
                    {range.effective_from} → {range.effective_to ?? "∞"}
                  </td>
                  <td className="px-3 py-2 text-right">
                    {!range.effective_to && (
                      <button
                        type="button"
                        onClick={() => void handleRetire(range.id)}
                        disabled={retiringId === range.id}
                        title="Retire this range"
                        className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors disabled:opacity-50"
                      >
                        <Archive className="w-4 h-4" />
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}
