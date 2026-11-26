import { useCallback, useEffect, useMemo, useState } from "react";
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
import { settingsService } from "../settings/settingsService";
import { fetchTenantContext } from "../auth/tenantContext";
import { sampleService } from "./sampleService";
import type { SampleLabelData } from "./types";
import { LabelPrintSheet } from "./components";
import styles from "./SampleLabelScreen.module.css";

export interface SampleLabelScreenProps {
  sampleId?: string;
  sampleIds?: string[];
  onBack?: () => void;
  service?: typeof sampleService;
}

export function SampleLabelScreen({
  sampleId,
  sampleIds,
  onBack,
  service = sampleService,
}: SampleLabelScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const navigate = useNavigate();

  const targetIds = useMemo(() => {
    const raw =
      sampleIds && sampleIds.length > 0
        ? sampleIds
        : sampleId
          ? [sampleId]
          : [];
    return Array.from(new Set(raw.map((id) => id.trim()).filter(Boolean)));
  }, [sampleId, sampleIds]);
  const isBulk = targetIds.length > 1;
  const fallbackBackPath =
    !isBulk && targetIds[0] ? `/samples/${targetIds[0]}` : "/samples";

  const [labels, setLabels] = useState<SampleLabelData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isPrinting, setIsPrinting] = useState(false);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [labName, setLabName] = useState<string>("LabFlow");

  const loadLabel = useCallback(async () => {
    if (targetIds.length === 0) {
      setLabels([]);
      setIsLoading(false);
      return;
    }
    try {
      setIsLoading(true);
      setErrorMessage(null);
      // GET preview: does NOT write an audit row (D8)
      if (targetIds.length === 1 && targetIds[0]) {
        const data = await service.getLabel(targetIds[0]);
        setLabels([data]);
      } else {
        const data = await service.getLabelsBulk(targetIds);
        setLabels(data);
      }
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [targetIds, service, t]);

  useEffect(() => {
    loadLabel();
  }, [loadLabel]);

  // Real organisation name for the sticker header: tenant branding first,
  // then the live tenant context endpoint, then the LabFlow product name.
  // Never a hard-coded laboratory name.
  useEffect(() => {
    let active = true;
    const loadTenantName = async () => {
      try {
        const settings = await settingsService.getSettings();
        const raw = settings.brand_display_name?.value;
        if (active && typeof raw === "string" && raw.trim()) {
          setLabName(raw.trim());
          return;
        }
      } catch {
        // Fall through to the tenant context endpoint.
      }
      try {
        const info = await fetchTenantContext();
        if (active && info?.name?.trim()) setLabName(info.name.trim());
      } catch {
        // Keep LabFlow as the safe product fallback.
      }
    };
    void loadTenantName();
    return () => {
      active = false;
    };
  }, []);

  // Thermal roll geometry belongs to this screen only. The style element is
  // removed on unmount so the A4/A5 invoice print routes keep their own page
  // rules untouched.
  useEffect(() => {
    const style = document.createElement("style");
    style.setAttribute("data-lf-page", "sample-label");
    style.textContent = "@page { size: 50mm 30mm; margin: 0; }";
    document.head.appendChild(style);
    return () => {
      style.remove();
    };
  }, []);

  const handlePrint = async () => {
    if (targetIds.length === 0) return;
    try {
      setIsPrinting(true);
      // POST label/print: explicit audited print action (D8)
      if (targetIds.length === 1 && targetIds[0]) {
        await service.printLabel(targetIds[0]);
      } else {
        await service.printLabelsBulk(targetIds);
      }
      window.print();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsPrinting(false);
    }
  };

  if (isLoading && labels.length === 0) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">
          {t("samples:label_page.generating")}
        </p>
      </main>
    );
  }

  if (errorMessage && labels.length === 0) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-2xl p-6 max-w-md w-full shadow-sm text-center">
          <p className="text-sm text-red-600 mb-4">{errorMessage}</p>
          <button
            type="button"
            onClick={onBack || (() => navigate(fallbackBackPath))}
            className={styles.primaryBlackPill}
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            <span>{t("samples:label_page.back")}</span>
          </button>
        </div>
      </main>
    );
  }

  if (labels.length === 0) return <div />;

  const primaryLabel = labels[0]!;

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header Row */}
      <header className={styles.headerRow}>
        <div className={styles.titleArea}>
          <div className="flex items-center gap-2 mb-1">
            <button
              type="button"
              onClick={onBack || (() => navigate(fallbackBackPath))}
              className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>{t("samples:label_page.back")}</span>
            </button>
          </div>
          <h1 className={styles.pageTitle}>{t("samples:label_page.title")}</h1>
          <p className={styles.pageSubtitle}>
            {isBulk ? (
              <bdi dir="ltr">
                {labels.map((item) => item.accession_id).join(", ")}
              </bdi>
            ) : (
              <>
                <bdi dir="ltr">{primaryLabel.accession_id}</bdi> ·{" "}
                {primaryLabel.patient_name}
              </>
            )}
          </p>
        </div>

        <div className={styles.headerActions}>
          <button
            type="button"
            onClick={onBack || (() => navigate(fallbackBackPath))}
            className={styles.outlinePill}
          >
            <span>{t("samples:label_page.close")}</span>
          </button>
          <button
            type="button"
            disabled={isPrinting}
            onClick={handlePrint}
            className={styles.primaryBlackPill}
          >
            <Printer className="w-4 h-4" />
            <span>
              {isPrinting
                ? t("samples:label_page.printing")
                : t("samples:label_page.print")}
            </span>
          </button>
        </div>
      </header>

      {/* Error alert (never printed) */}
      {errorMessage && (
        <div
          role="alert"
          data-print-hide
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

      {/* Instruction Note (never printed) */}
      <div className={styles.instructionCard} data-print-hide>
        <Info className="w-4 h-4 text-slate-500 shrink-0" />
        <span>{t("samples:label_page.printing_note")}</span>
      </div>

      {/* 2. Printed Sheet Preview */}
      {labels.map((item) => (
        <LabelPrintSheet
          key={item.accession_id}
          labelData={item}
          tenantName={labName}
        />
      ))}
    </div>
  );
}

export default SampleLabelScreen;
