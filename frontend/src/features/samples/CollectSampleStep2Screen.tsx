import { useEffect, useState } from "react";
import {
  ArrowLeft,
  ArrowRight,
  Check,
  CheckCircle2,
  Clock,
  Printer,
  Receipt,
  ScanLine,
  X,
} from "lucide-react";
import { sampleService } from "./sampleService";
import type { SampleCollectionDraft, SampleCreatedResponse } from "./types";

export interface CollectSampleStep2ScreenProps {
  draft: SampleCollectionDraft;
  onBack?: () => void;
  onConfirmed?: (sample: SampleCreatedResponse) => void;
  service?: typeof sampleService;
}

export function CollectSampleStep2Screen({
  draft,
  onBack,
  onConfirmed,
  service = sampleService,
}: CollectSampleStep2ScreenProps): JSX.Element {
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [createdSample, setCreatedSample] =
    useState<SampleCreatedResponse | null>(null);
  const [secondsLeft, setSecondsLeft] = useState<number>(5);

  // Auto-dismiss countdown when sample is collected
  useEffect(() => {
    if (!createdSample) return;
    if (secondsLeft <= 0) {
      onConfirmed?.(createdSample);
      return;
    }

    const timer = setTimeout(() => {
      setSecondsLeft((prev) => prev - 1);
    }, 1000);

    return () => clearTimeout(timer);
  }, [createdSample, secondsLeft, onConfirmed]);

  const handleCommitCollection = async () => {
    try {
      setIsSubmitting(true);
      setErrorMessage(null);

      const res = await service.collectSample({
        invoice_id: draft.invoice_id,
        invoice_item_ids: draft.selected_item_ids,
        notes: draft.notes,
      });

      setCreatedSample(res);
    } catch (err) {
      setErrorMessage(
        err instanceof Error
          ? err.message
          : "Failed to record specimen collection.",
      );
      setIsSubmitting(false);
    }
  };

  return (
    <div className="w-full max-w-[760px] mx-auto px-4 py-8 space-y-6">
      {/* Breadcrumb & Header */}
      <div>
        <nav
          aria-label="Breadcrumb"
          className="flex items-center gap-2 text-xs text-slate-500 mb-1.5"
        >
          <button
            type="button"
            onClick={onBack}
            className="hover:text-slate-800 transition-colors cursor-pointer"
          >
            Samples
          </button>
          <span className="text-slate-300">/</span>
          <span className="text-slate-900 font-medium">New</span>
          <span className="text-slate-300 ml-1">·</span>
          <span className="text-slate-500 font-normal">
            Step 2: Tube Preparation
          </span>
        </nav>
        <div className="flex items-center justify-between">
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            Collect sample
          </h1>
          <div className="flex items-center gap-2 bg-white px-3 py-1.5 rounded-lg border border-slate-200 text-xs text-slate-600">
            <span className="inline-block w-2 h-2 rounded-full bg-teal-600 animate-pulse" />
            <span>
              Station: <strong>Phlebotomy Counter 02</strong>
            </span>
          </div>
        </div>
      </div>

      {/* Error alert */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-lg text-xs text-red-700 flex items-center justify-between"
        >
          <span>{errorMessage}</span>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            aria-label="Dismiss error"
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Stepper Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm p-6 md:p-8 space-y-8">
        {/* Progress Navigation */}
        <nav aria-label="Progress" className="w-full">
          <ol className="flex items-center justify-between w-full">
            {/* Step 1: Invoice (Completed) */}
            <li className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-teal-600 flex items-center justify-center text-white">
                <Check className="w-4 h-4" />
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] text-teal-600 uppercase font-bold tracking-wider">
                  Step 1
                </span>
                <span className="text-xs text-teal-700 font-semibold">
                  Invoice
                </span>
              </div>
            </li>
            <li aria-hidden="true" className="flex-1 mx-4 h-0.5 bg-teal-600" />

            {/* Step 2: Tests & Collection (Active) */}
            <li className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full border-2 border-teal-600 bg-teal-50 text-teal-700 flex items-center justify-center text-xs font-bold">
                2
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] text-slate-500 uppercase tracking-wider font-medium">
                  Step 2
                </span>
                <span className="text-xs text-slate-900 font-semibold">
                  Tests & collection
                </span>
              </div>
            </li>
            <li aria-hidden="true" className="flex-1 mx-4 h-0.5 bg-slate-200" />

            {/* Step 3: Printing (Upcoming) */}
            <li className="flex items-center gap-3">
              <div className="w-8 h-8 rounded-full bg-slate-100 text-slate-400 flex items-center justify-center text-xs font-medium">
                3
              </div>
              <div className="flex flex-col">
                <span className="text-[11px] text-slate-400 uppercase tracking-wider font-medium">
                  Step 3
                </span>
                <span className="text-xs text-slate-400">Label print</span>
              </div>
            </li>
          </ol>
        </nav>

        {/* 1. Summary Strip */}
        <div className="bg-slate-50 border border-slate-200 rounded-lg px-4 py-3 flex flex-wrap items-center justify-between gap-3 text-xs">
          <div className="flex items-center gap-2.5 min-w-0">
            <Receipt className="w-4 h-4 text-slate-400 shrink-0" />
            <div className="truncate">
              <span className="font-semibold text-slate-900">
                Invoice{" "}
                <span className="font-mono text-xs font-medium">
                  {draft.invoice_id.substring(0, 13)}
                </span>
              </span>
              <span className="text-slate-300 mx-1">·</span>
              <span className="text-slate-700">{draft.patient_name}</span>
              <span className="text-slate-300 mx-1">·</span>
              <span className="font-mono bg-white px-2 py-0.5 rounded border border-slate-200 text-slate-800 font-semibold">
                {draft.patient_mrn}
              </span>
            </div>
          </div>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full bg-teal-50 text-teal-700 border border-teal-200 font-semibold tracking-wide">
            <span className="inline-block w-1.5 h-1.5 rounded-full bg-teal-600" />
            Verified
          </div>
        </div>

        {/* 2. Tests to Collect */}
        <div className="space-y-3.5">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h2 className="text-sm font-semibold text-slate-900">
                Tests to collect
              </h2>
              <span className="text-[11px] px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 font-medium">
                ({draft.selected_item_ids.length} items selected)
              </span>
            </div>
            <span className="text-xs text-slate-400">
              All specimens ready for draw
            </span>
          </div>

          <div className="space-y-2.5">
            {(draft.test_labels || []).map((label, idx) => {
              const isEdta = label.toLowerCase().includes("cbc");
              return (
                <div
                  key={idx}
                  className="flex items-center justify-between p-3.5 rounded-lg border border-slate-200 bg-white"
                >
                  <div className="flex items-center gap-3">
                    <span className="w-2.5 h-2.5 rounded-full bg-teal-600" />
                    <div>
                      <span className="text-sm font-semibold text-slate-900">
                        {label}
                      </span>
                      <div className="flex items-center gap-2 mt-0.5 text-xs text-slate-500">
                        <span>
                          {isEdta
                            ? "EDTA tube (Purple top) · 3.0 mL"
                            : "Fluoride Plasma / EDTA (Grey/Purple top) · 2.0 mL"}
                        </span>
                      </div>
                    </div>
                  </div>
                  <span className="text-xs px-2 py-0.5 rounded bg-slate-50 text-slate-600 border border-slate-200 font-medium">
                    {isEdta ? "Whole Blood" : "Plasma / Blood"}
                  </span>
                </div>
              );
            })}
          </div>
        </div>

        {/* 3. Collection Timestamps & Operator */}
        <div className="pt-2 border-t border-slate-100 flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-1.5">
            <Clock className="w-3.5 h-3.5" />
            <span>
              Timestamp: <strong>{draft.collected_at}</strong>
            </span>
          </div>
          <div>
            Operator: <strong>{draft.collected_by}</strong>
          </div>
        </div>

        {/* 4. Footer Actions */}
        <div className="flex items-center justify-between pt-5 border-t border-slate-100">
          <button
            type="button"
            onClick={onBack}
            className="px-5 py-2.5 rounded-lg border border-slate-200 text-slate-700 hover:bg-slate-50 text-xs font-semibold transition-colors flex items-center gap-1.5"
          >
            <ArrowLeft className="w-3.5 h-3.5" />
            <span>Back</span>
          </button>
          <button
            type="button"
            onClick={handleCommitCollection}
            disabled={isSubmitting || createdSample !== null}
            className="px-6 py-2.5 rounded-lg bg-teal-600 hover:bg-teal-700 disabled:opacity-50 text-white text-xs font-semibold shadow-sm transition-colors flex items-center gap-2 cursor-pointer"
          >
            <span>{isSubmitting ? "Accessioning..." : "Collect sample"}</span>
            <ArrowRight className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Thermal Printer Readiness Card */}
      <div className="bg-slate-50 rounded-xl p-4 border border-slate-200 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="w-10 h-10 rounded-lg bg-white border border-slate-200 flex items-center justify-center shrink-0">
            <ScanLine className="w-5 h-5 text-teal-600" />
          </div>
          <div>
            <div className="text-sm font-semibold text-slate-900">
              Primary Barcode Labels Queued
            </div>
            <div className="text-xs text-slate-500">
              Zebra ZD410 Thermal Printer · Ready on Tray 1
            </div>
          </div>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1 text-xs font-mono text-slate-600 bg-white px-2.5 py-1 rounded border border-slate-200">
            <Printer className="w-3.5 h-3.5 text-teal-600" />
            Auto-print enabled
          </span>
        </div>
      </div>

      {/* Success Toast Banner */}
      {createdSample && (
        <aside
          role="status"
          aria-live="polite"
          className="fixed bottom-6 right-6 z-50 bg-white border border-slate-200 shadow-xl rounded-xl p-4 max-w-sm w-full flex items-start gap-3 animate-in slide-in-from-bottom"
        >
          <div className="w-6 h-6 rounded-full bg-emerald-50 text-emerald-600 flex items-center justify-center shrink-0 mt-0.5">
            <CheckCircle2 className="w-4 h-4" />
          </div>
          <div className="flex-1 min-w-0">
            <div className="text-sm font-semibold text-slate-900">
              Sample collected
            </div>
            <p className="text-xs text-slate-600 mt-0.5 leading-relaxed">
              Accession{" "}
              <span className="font-mono font-medium text-slate-900">
                {createdSample.accession_id}
              </span>{" "}
              created — opening label print.
            </p>
            <div className="flex items-center gap-2 mt-2">
              <span className="text-[11px] text-slate-400">
                Auto-opening in {secondsLeft}s
              </span>
              <button
                type="button"
                onClick={() => onConfirmed?.(createdSample)}
                className="text-xs font-semibold text-teal-600 hover:text-teal-800 underline ml-auto"
              >
                Open now →
              </button>
            </div>
          </div>
          <button
            type="button"
            onClick={() => onConfirmed?.(createdSample)}
            aria-label="Close notification"
            className="text-slate-400 hover:text-slate-600"
          >
            <X className="w-4 h-4" />
          </button>
        </aside>
      )}
    </div>
  );
}
