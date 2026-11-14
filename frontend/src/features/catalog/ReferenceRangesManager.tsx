import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Plus, RefreshCw, AlertCircle, X, Archive, Pencil } from "lucide-react";
import { messageForError } from "../../lib/errors";
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

const SEX_SLUGS: Record<RangeSex, string> = {
  M: "male",
  F: "female",
  B: "both",
};

function formatBand(range: ReferenceRange, daysLabel: string): string {
  const max = range.age_max_days === null ? "∞" : String(range.age_max_days);
  return `${range.age_min_days}–${max} ${daysLabel}`;
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
  const { t } = useTranslation(["settings", "common"]);
  const [ranges, setRanges] = useState<ReferenceRange[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [isFormOpen, setIsFormOpen] = useState(false);
  const [form, setForm] = useState<ReferenceRangeCreateInput>(emptyForm());
  const [isSaving, setIsSaving] = useState(false);
  const [retiringId, setRetiringId] = useState<string | null>(null);
  // D7: per-row critical threshold editing, using only the critical_low /
  // critical_high values already stored on the range.
  const [editingCriticalId, setEditingCriticalId] = useState<string | null>(
    null,
  );
  const [criticalDraft, setCriticalDraft] = useState<{
    low: string;
    high: string;
  }>({ low: "", high: "" });
  const [savingCriticalId, setSavingCriticalId] = useState<string | null>(null);

  const load = useCallback(async () => {
    setIsLoading(true);
    setError(null);
    try {
      const data = await service.listTestRanges(testId);
      setRanges(data);
    } catch (err) {
      setError(
        err && typeof err === "object" && "code" in err
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:ranges.load_failed"),
      );
    } finally {
      setIsLoading(false);
    }
  }, [service, testId, t]);

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
          ? t("settings:ranges.overlap_create")
          : coded.code
            ? messageForError(coded, (key, options) =>
                t(`common:${key}`, options),
              )
            : t("settings:ranges.create_failed"),
      );
    } finally {
      setIsSaving(false);
    }
  }

  function startCriticalEdit(range: ReferenceRange): void {
    setEditingCriticalId(range.id);
    setCriticalDraft({
      low: range.critical_low ?? "",
      high: range.critical_high ?? "",
    });
  }

  async function handleSaveCritical(rangeId: string): Promise<void> {
    setSavingCriticalId(rangeId);
    setError(null);
    try {
      const updated = await service.updateTestRange(testId, rangeId, {
        critical_low: criticalDraft.low.trim()
          ? criticalDraft.low.trim()
          : null,
        critical_high: criticalDraft.high.trim()
          ? criticalDraft.high.trim()
          : null,
      });
      // PATCH supersedes the row: the backend closes the old range and returns
      // its successor with a NEW id, so replace rather than map by old id.
      setRanges((prev) => [updated, ...prev.filter((r) => r.id !== rangeId)]);
      setEditingCriticalId(null);
    } catch (err) {
      const coded = err as Error & { code?: string };
      setError(
        coded.code === "overlapping_range"
          ? t("settings:ranges.overlap_update")
          : coded.code
            ? messageForError(coded, (key, options) =>
                t(`common:${key}`, options),
              )
            : t("settings:ranges.critical_update_failed"),
      );
    } finally {
      setSavingCriticalId(null);
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
      setError(
        err && typeof err === "object" && "code" in err
          ? messageForError(err, (key, options) => t(`common:${key}`, options))
          : t("settings:ranges.retire_failed"),
      );
    } finally {
      setRetiringId(null);
    }
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h3 className="text-sm font-semibold text-slate-900">
          {testCode
            ? t("settings:ranges.title_with_code", { code: testCode })
            : t("settings:ranges.title")}
        </h3>
        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={() => void load()}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            aria-label={t("settings:ranges.reload_aria")}
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
            {isFormOpen ? t("common:actions.cancel") : t("settings:ranges.add")}
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
            {t("common:labels.sex")}
            <select
              value={form.sex}
              onChange={(e) => setField("sex", e.target.value as RangeSex)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            >
              {(Object.keys(SEX_SLUGS) as RangeSex[]).map((s) => (
                <option key={s} value={s}>
                  {t(`settings:ranges.sex_${SEX_SLUGS[s]}`)}
                </option>
              ))}
            </select>
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.age_min")}
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
            {t("settings:ranges.age_max")}
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
            {t("settings:ranges.unit")}
            <input
              type="text"
              value={form.unit}
              onChange={(e) => setField("unit", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
              required
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.low")}
            <input
              type="text"
              inputMode="decimal"
              value={form.low ?? ""}
              onChange={(e) => setField("low", e.target.value)}
              placeholder={t("settings:ranges.low_placeholder")}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.high")}
            <input
              type="text"
              inputMode="decimal"
              value={form.high ?? ""}
              onChange={(e) => setField("high", e.target.value)}
              placeholder={t("settings:ranges.high_placeholder")}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.critical_low")}
            <input
              type="text"
              inputMode="decimal"
              value={form.critical_low ?? ""}
              onChange={(e) => setField("critical_low", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.critical_high")}
            <input
              type="text"
              inputMode="decimal"
              value={form.critical_high ?? ""}
              onChange={(e) => setField("critical_high", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.effective_from")}
            <input
              type="date"
              value={form.effective_from}
              onChange={(e) => setField("effective_from", e.target.value)}
              className="mt-1 w-full px-2 py-1.5 bg-white text-slate-900 text-sm rounded-lg border border-slate-200"
              required
            />
          </label>
          <label className="text-xs font-medium text-slate-600">
            {t("settings:ranges.effective_to")}
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
              {isSaving
                ? t("settings:ranges.saving")
                : t("settings:ranges.save_range")}
            </button>
          </div>
        </form>
      )}

      {isLoading ? (
        <div className="h-24 rounded-lg bg-slate-100 border border-slate-200" />
      ) : ranges.length === 0 ? (
        <p className="text-sm text-slate-500 py-6 text-center border border-dashed border-slate-200 rounded-lg">
          {t("settings:ranges.empty")}
        </p>
      ) : (
        <div className="overflow-x-auto rounded-lg border border-slate-200">
          <table className="w-full text-sm">
            <thead>
              <tr className="bg-slate-50 text-start text-xs font-medium text-slate-500">
                <th className="px-3 py-2">{t("settings:ranges.col_sex")}</th>
                <th className="px-3 py-2">
                  {t("settings:ranges.col_age_band")}
                </th>
                <th className="px-3 py-2">{t("settings:ranges.col_range")}</th>
                <th className="px-3 py-2">
                  {t("settings:ranges.col_critical")}
                </th>
                <th className="px-3 py-2">
                  {t("settings:ranges.col_effective")}
                </th>
                <th className="px-3 py-2 text-end">
                  {t("settings:ranges.col_actions")}
                </th>
              </tr>
            </thead>
            <tbody>
              {ranges.map((range) => (
                <tr
                  key={range.id}
                  className="border-t border-slate-100 text-slate-800"
                >
                  <td className="px-3 py-2 font-medium">
                    {t(`settings:ranges.sex_${SEX_SLUGS[range.sex]}`)}
                  </td>
                  <td className="px-3 py-2">
                    {formatBand(range, t("settings:ranges.days"))}
                  </td>
                  <td className="px-3 py-2" dir="ltr">
                    {formatBounds(range)}
                  </td>
                  <td className="px-3 py-2 text-slate-500">
                    {editingCriticalId === range.id ? (
                      <div className="flex items-center gap-1">
                        <input
                          aria-label={t("settings:ranges.critical_low_aria", {
                            id: range.id,
                          })}
                          inputMode="decimal"
                          value={criticalDraft.low}
                          onChange={(e) =>
                            setCriticalDraft((prev) => ({
                              ...prev,
                              low: e.target.value,
                            }))
                          }
                          placeholder={t("settings:ranges.placeholder_low")}
                          className="w-16 px-1.5 py-1 bg-white text-slate-900 text-xs rounded border border-slate-300"
                        />
                        <span>–</span>
                        <input
                          aria-label={t("settings:ranges.critical_high_aria", {
                            id: range.id,
                          })}
                          inputMode="decimal"
                          value={criticalDraft.high}
                          onChange={(e) =>
                            setCriticalDraft((prev) => ({
                              ...prev,
                              high: e.target.value,
                            }))
                          }
                          placeholder={t("settings:ranges.placeholder_high")}
                          className="w-16 px-1.5 py-1 bg-white text-slate-900 text-xs rounded border border-slate-300"
                        />
                      </div>
                    ) : (
                      <span dir="ltr">
                        {range.critical_low ?? "–"} –{" "}
                        {range.critical_high ?? "–"}
                      </span>
                    )}
                  </td>
                  <td className="px-3 py-2 text-slate-500">
                    <span dir="ltr">
                      {range.effective_from} → {range.effective_to ?? "∞"}
                    </span>
                  </td>
                  <td className="px-3 py-2 text-end">
                    <div className="inline-flex items-center gap-1">
                      {editingCriticalId === range.id ? (
                        <>
                          <button
                            type="button"
                            onClick={() => void handleSaveCritical(range.id)}
                            disabled={savingCriticalId === range.id}
                            className="px-2 py-1 text-xs font-semibold text-white bg-[#005c55] hover:bg-[#0f766e] rounded disabled:opacity-50"
                          >
                            {savingCriticalId === range.id
                              ? t("settings:ranges.saving")
                              : t("common:actions.save")}
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditingCriticalId(null)}
                            className="px-2 py-1 text-xs font-semibold text-slate-600 border border-slate-200 rounded"
                          >
                            {t("common:actions.cancel")}
                          </button>
                        </>
                      ) : (
                        <button
                          type="button"
                          onClick={() => startCriticalEdit(range)}
                          title={t("settings:ranges.edit_critical_title")}
                          aria-label={t("settings:ranges.edit_critical_title")}
                          className="p-1.5 text-slate-400 hover:text-[#005c55] hover:bg-teal-50 rounded-md transition-colors"
                        >
                          <Pencil className="w-4 h-4" />
                        </button>
                      )}
                      {!range.effective_to && (
                        <button
                          type="button"
                          onClick={() => void handleRetire(range.id)}
                          disabled={retiringId === range.id}
                          title={t("settings:ranges.retire_title")}
                          className="p-1.5 text-slate-400 hover:text-red-600 hover:bg-red-50 rounded-md transition-colors disabled:opacity-50"
                        >
                          <Archive className="w-4 h-4" />
                        </button>
                      )}
                    </div>
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
