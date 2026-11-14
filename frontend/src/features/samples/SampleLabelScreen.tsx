import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  CheckCircle2,
  Clock,
  FlaskConical,
  Printer,
  RotateCcw,
  RotateCw,
  ShieldCheck,
  X,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { Code128Barcode } from "./components/Code128Barcode";
import { sampleService } from "./sampleService";
import type { SampleLabelData } from "./types";

export interface SampleLabelScreenProps {
  sampleId: string;
  onBack?: () => void;
  service?: typeof sampleService;
}

export function SampleLabelScreen({
  sampleId,
  onBack,
  service = sampleService,
}: SampleLabelScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const [labelData, setLabelData] = useState<SampleLabelData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [printCount, setPrintCount] = useState<number>(1);
  const [toastMessage, setToastMessage] = useState<string | null>(null);

  const loadLabel = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const data = await service.getLabel(sampleId);
      setLabelData(data);
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [sampleId, service, t]);

  useEffect(() => {
    loadLabel();
  }, [loadLabel]);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 4000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const handlePrint = () => {
    setPrintCount((c) => c + 1);
    setToastMessage(
      t("samples:label.print_dispatched_desc", {
        accession: labelData?.accession_id,
      }),
    );
    window.print();
  };

  const handleReprint = () => {
    setPrintCount((c) => c + 1);
    setToastMessage(t("samples:label.reprint_logged", { n: printCount }));
    window.print();
  };

  if (isLoading) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">{t("samples:label.generating")}</p>
      </main>
    );
  }

  if (errorMessage || !labelData) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-xl p-6 max-w-md w-full shadow-sm text-center">
          <p className="text-sm text-red-600 mb-4">
            {errorMessage || t("samples:label.unavailable")}
          </p>
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700"
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            {t("samples:label.back_to_details")}
          </button>
        </div>
      </main>
    );
  }

  const d = labelData;
  const testsSummary = d.tests && d.tests.length > 0 ? d.tests.join(", ") : "—";

  return (
    <main className="w-full min-h-screen bg-slate-50 flex flex-col justify-between p-6 sm:p-8">
      {/* Thermal Print Styles injected for pure label direct output */}
      <style>{`
        @media print {
          body {
            margin: 0 !important;
            padding: 0 !important;
            background: #ffffff !important;
          }
          header, aside, nav, button, footer, .no-print {
            display: none !important;
          }
          .printable-label {
            width: 50mm !important;
            height: 25mm !important;
            border: none !important;
            box-shadow: none !important;
            padding: 1mm !important;
            margin: 0 auto !important;
            page-break-inside: avoid !important;
          }
        }
      `}</style>

      <div className="max-w-4xl mx-auto w-full">
        {/* Header & Breadcrumb */}
        <div className="mb-6 sm:mb-8 no-print">
          <div className="flex items-center justify-between mb-1">
            <nav
              aria-label={t("samples:breadcrumbs.aria")}
              className="flex items-center gap-1.5 text-xs text-slate-500"
            >
              <button
                type="button"
                onClick={onBack}
                className="hover:text-teal-700 transition-colors flex items-center gap-1"
              >
                <FlaskConical className="w-3.5 h-3.5 text-teal-600" />
                <span>{t("common:nav.samples")}</span>
              </button>
              <span>/</span>
              <span className="font-mono text-slate-700" dir="ltr">
                {d.accession_id}
              </span>
              <span>/</span>
              <span className="text-slate-800 font-semibold">
                {t("samples:label.breadcrumb_label")}
              </span>
            </nav>
            <div className="text-xs text-slate-500 flex items-center gap-1.5">
              <Clock className="w-3.5 h-3.5 text-slate-400" />
              <span>
                {d.collected_at
                  ? `${formatDate(d.collected_at)} · ${t("common:time.pkt")}`
                  : t("samples:label.times_are_pkt")}
              </span>
            </div>
          </div>

          <div className="flex items-center justify-between pt-1">
            <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
              {t("samples:label.title")}
            </h1>
            <button
              type="button"
              onClick={onBack}
              className="inline-flex items-center gap-1 text-xs text-slate-500 hover:text-slate-800 transition-colors font-medium"
            >
              <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
              <span>{t("samples:label.back_to_sample_details")}</span>
            </button>
          </div>
        </div>

        {/* Central Card Area */}
        <div className="bg-white border border-slate-200 rounded-xl shadow-sm p-6 sm:p-8 flex flex-col items-center">
          {/* Tube Label Header Info / Context Banner */}
          <div className="w-full max-w-md mb-6 flex items-center justify-between text-xs text-slate-500 pb-3 border-b border-slate-100 no-print">
            <div className="flex items-center gap-1.5">
              <Printer className="w-4 h-4 text-slate-400" />
              <span>{t("samples:label.thermal_size")}</span>
            </div>
            <span className="font-mono text-slate-400">
              {t("samples:label.print_mode")}
            </span>
          </div>

          {/* THE PRINT PREVIEW (Real Proportions, thin dashed cut border) */}
          <div className="printable-label bg-white border-2 border-dashed border-slate-300 rounded-md p-4 sm:p-5 w-full max-w-[380px] shadow-sm relative transition-all hover:border-slate-400">
            {/* Cut line corner marker */}
            <div className="absolute -top-2.5 start-4 bg-white px-1.5 text-[10px] font-mono uppercase tracking-wider text-slate-400 border border-slate-200 rounded no-print">
              {t("samples:label.cut_line")}
            </div>

            <div className="bg-white flex flex-col items-center text-center select-none pt-1 pb-1">
              {/* Code128 Barcode Graphic */}
              <div className="w-full flex justify-center mb-1.5 px-1">
                <Code128Barcode
                  value={d.accession_id}
                  height={52}
                  barWidth={2}
                  className="w-full max-w-[320px]"
                />
              </div>

              {/* Monospace Accession ID */}
              <div className="font-mono font-bold text-lg text-slate-900 tracking-wider mb-1 select-all">
                {d.accession_id}
              </div>

              {/* Patient Name */}
              <div className="font-bold text-base text-slate-900 leading-tight mb-1">
                {d.patient_name}
              </div>

              {/* Tests */}
              <div className="text-sm font-semibold text-slate-800 tracking-tight mb-1">
                {testsSummary}
              </div>

              {/* Collection Details & Branch */}
              <div className="text-[11px] text-slate-600 font-medium">
                Collected{" "}
                {d.collected_at
                  ? new Date(d.collected_at).toLocaleString("en-GB", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                      timeZone: "Asia/Karachi",
                    })
                  : "—"}{" "}
                · {d.branch_name || "—"}
              </div>
            </div>
          </div>

          {/* Label Metadata Breakdown Details */}
          <div className="mt-6 pt-6 border-t border-slate-100 w-full max-w-md grid grid-cols-2 gap-y-2 gap-x-4 text-xs no-print">
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("samples:label.patient_mrn")}
              </span>
              <span className="font-mono font-medium text-slate-800">
                {d.mrn}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("samples:label.primary_specimen")}
              </span>
              <span className="font-medium text-slate-800">
                {d.tests?.length ? d.tests.join(", ") : "—"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("samples:label.collected_by")}
              </span>
              <span className="font-medium text-slate-800">
                {d.collected_by || "—"}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("samples:label.accessioning_branch")}
              </span>
              <span className="font-medium text-slate-800">
                {d.branch_name || "—"}
              </span>
            </div>
          </div>

          {/* Controls Section */}
          <div className="mt-8 flex flex-col items-center gap-3 w-full max-w-xs no-print">
            <div className="flex items-center gap-3 w-full">
              {/* Print Button */}
              <button
                type="button"
                onClick={handlePrint}
                className="flex-1 bg-teal-600 hover:bg-teal-700 text-white font-medium py-2.5 px-4 rounded-lg shadow-sm flex items-center justify-center gap-2 transition-colors cursor-pointer text-sm"
              >
                <Printer className="w-4 h-4" />
                <span>{t("common:actions.print")}</span>
              </button>

              {/* Reprint Button */}
              <button
                type="button"
                onClick={handleReprint}
                className="flex-1 bg-white hover:bg-slate-50 text-slate-700 font-medium py-2.5 px-4 rounded-lg border border-slate-300 shadow-sm flex items-center justify-center gap-2 transition-colors cursor-pointer text-sm"
              >
                <RotateCcw className="w-4 h-4" />
                <span>{t("samples:actions.reprint")}</span>
              </button>
            </div>

            {/* Audit Note */}
            <p className="text-xs text-slate-500 flex items-center gap-1 text-center">
              <ShieldCheck className="w-4 h-4 text-slate-400" />
              <span>{t("samples:label.audit_note")}</span>
            </p>
          </div>
        </div>
      </div>

      {/* System Protocol Footer */}
      <footer className="mt-8 text-center text-xs text-slate-400 py-2 border-t border-slate-200 no-print">
        {t("samples:label.footer")}
      </footer>

      {/* Floating Toast Notification */}
      {toastMessage && (
        <aside
          role="status"
          aria-live="polite"
          className="fixed bottom-4 end-4 z-50 bg-white rounded-lg shadow-lg border border-slate-200 p-4 max-w-sm w-80 flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2 no-print"
        >
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h4 className="text-xs font-semibold text-slate-900">
              {t("samples:label.print_dispatched")}
            </h4>
            <p className="text-xs text-slate-600 mt-0.5 leading-snug">
              {toastMessage}
            </p>
          </div>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-slate-600 p-1"
            aria-label={t("samples:label.close_notification")}
          >
            <X className="w-4 h-4" />
          </button>
        </aside>
      )}
    </main>
  );
}
