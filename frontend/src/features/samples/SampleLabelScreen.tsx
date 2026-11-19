import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  Info,
  Printer,
  RotateCw,
  X,
  AlertCircle,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { sampleService } from "./sampleService";
import type { SampleLabelData } from "./types";
import { LabelPrintSheet } from "./components";
import styles from "./SampleLabelScreen.module.css";

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
  const navigate = useNavigate();

  const [labelData, setLabelData] = useState<SampleLabelData | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isPrinting, setIsPrinting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const loadLabel = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      // GET preview: does NOT write an audit row (D8)
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

  const handlePrint = async () => {
    try {
      setIsPrinting(true);
      // POST label/print: explicit audited print action (D8)
      await service.printLabel(sampleId);
      window.print();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsPrinting(false);
    }
  };

  if (isLoading && !labelData) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">Generating barcode label...</p>
      </main>
    );
  }

  if (errorMessage && !labelData) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-2xl p-6 max-w-md w-full shadow-sm text-center">
          <p className="text-sm text-red-600 mb-4">{errorMessage}</p>
          <button
            type="button"
            onClick={onBack || (() => navigate(`/samples/${sampleId}`))}
            className={styles.primaryBlackPill}
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            <span>Back to Details</span>
          </button>
        </div>
      </main>
    );
  }

  if (!labelData) return <div />;

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header Row */}
      <header className={styles.headerRow}>
        <div className={styles.titleArea}>
          <div className="flex items-center gap-2 mb-1">
            <button
              type="button"
              onClick={onBack || (() => navigate(`/samples/${sampleId}`))}
              className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>Back to Details</span>
            </button>
          </div>
          <h1 className={styles.pageTitle}>Sample label</h1>
          <p className={styles.pageSubtitle}>
            {labelData.accession_id} · {labelData.patient_name}
          </p>
        </div>

        <div className={styles.headerActions}>
          <button
            type="button"
            onClick={onBack || (() => navigate(`/samples/${sampleId}`))}
            className={styles.outlinePill}
          >
            <span>Close</span>
          </button>
          <button
            type="button"
            disabled={isPrinting}
            onClick={handlePrint}
            className={styles.primaryBlackPill}
          >
            <Printer className="w-4 h-4" />
            <span>{isPrinting ? "Printing..." : "Print"}</span>
          </button>
        </div>
      </header>

      {/* Error alert */}
      {errorMessage && (
        <div
          role="alert"
          className="p-3 bg-red-50 border border-red-200 rounded-xl text-xs text-red-700 flex items-center justify-between"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMessage}</span>
          </div>
          <button
            type="button"
            onClick={() => setErrorMessage(null)}
            className="text-red-500 hover:text-red-700"
          >
            <X className="w-4 h-4" />
          </button>
        </div>
      )}

      {/* Instruction Note */}
      <div className={styles.instructionCard}>
        <Info className="w-4 h-4 text-slate-500 shrink-0" />
        <span>
          Printing Note: Ensure browser print margins are set to &apos;None&apos; and Headers
          &amp; Footers are unchecked for optimal thermal sticker alignment.
        </span>
      </div>

      {/* 2. Printed Sheet Preview */}
      <LabelPrintSheet labelData={labelData} />
    </div>
  );
}

export default SampleLabelScreen;
