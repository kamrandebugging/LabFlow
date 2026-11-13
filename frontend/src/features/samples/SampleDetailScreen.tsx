import { useCallback, useEffect, useId, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRightLeft,
  Ban,
  Building2,
  Check,
  CheckCircle2,
  Clock,
  Copy,
  FlaskConical,
  History,
  Inbox,
  MapPin,
  Printer,
  QrCode,
  RotateCw,
  ShieldCheck,
  User,
  X,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate, formatDateTime } from "../../lib/format";
import { sampleService } from "./sampleService";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import type { RejectionReasonCode, SampleDetail, SampleStatus } from "./types";

export interface SampleDetailScreenProps {
  sampleId: string;
  onBack?: () => void;
  onPrintLabel?: (sampleId: string) => void;
  onViewPatient?: (patientId: string) => void;
  service?: typeof sampleService;
}

type Translator = (key: string) => string;

const REJECTION_REASONS: Array<{ code: RejectionReasonCode; key: string }> = [
  { code: "hemolyzed", key: "samples:reject_reasons.hemolyzed" },
  { code: "clotted", key: "samples:reject_reasons.clotted" },
  {
    code: "insufficient_volume",
    key: "samples:reject_reasons.insufficient_volume",
  },
  { code: "wrong_tube", key: "samples:reject_reasons.wrong_tube" },
  { code: "mislabelled", key: "samples:reject_reasons.mislabelled" },
  {
    code: "damaged_transport",
    key: "samples:reject_reasons.damaged_transport",
  },
  { code: "other", key: "samples:reject_reasons.other" },
];

function getStatusPill(status: SampleStatus, t: Translator): JSX.Element {
  switch (status) {
    case "collected":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <span className="w-2 h-2 rounded-full bg-blue-600" />
          {t("common:status.sample.collected")}
        </span>
      );
    case "received":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
          <span className="w-2 h-2 rounded-full bg-teal-600" />
          {t("common:status.sample.received")}
        </span>
      );
    case "in_process":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-orange-50 text-orange-800 border border-orange-200">
          <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
          {t("common:status.sample.in_process")}
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
          <span className="w-2 h-2 rounded-full bg-emerald-600" />
          {t("samples:status.ready_reported")}
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-800 border border-red-200">
          <span className="w-2 h-2 rounded-full bg-red-600" />
          {t("common:status.sample.rejected")}
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
          <span className="w-2 h-2 rounded-full bg-slate-500" />
          {t("common:status.sample.cancelled")}
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
          {t("common:labels.unknown")}
        </span>
      );
  }
}

export function SampleDetailScreen({
  sampleId,
  onBack,
  onPrintLabel,
  onViewPatient,
  service = sampleService,
}: SampleDetailScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  const [sample, setSample] = useState<SampleDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [isCopied, setIsCopied] = useState(false);

  // Modals & Action States
  const [isReceiving, setIsReceiving] = useState(false);
  const [showRejectModal, setShowRejectModal] = useState(false);
  const [rejectReasonCode, setRejectReasonCode] = useState<RejectionReasonCode>(
    REJECTION_REASONS[0]?.code ?? "hemolyzed",
  );
  const [rejectReasonNote, setRejectReasonNote] = useState("");
  const [isRejecting, setIsRejecting] = useState(false);

  const [branches, setBranches] = useState<Branch[]>([]);
  const [showTransferModal, setShowTransferModal] = useState(false);
  const [transferBranchId, setTransferBranchId] = useState("");
  const [transferNotes, setTransferNotes] = useState("");
  const [isTransferring, setIsTransferring] = useState(false);

  // Toast
  const [toastMessage, setToastMessage] = useState<{
    title: string;
    description: string;
  } | null>(null);

  const rejectCodeSelectId = useId();
  const rejectNoteInputId = useId();
  const transferBranchSelectId = useId();
  const transferNoteInputId = useId();

  const loadDetail = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const data = await service.getSample(sampleId);
      setSample(data);
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [sampleId, service, t]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  useEffect(() => {
    let active = true;
    void settingsService
      .getBranches(false)
      .then((list) => {
        if (active && Array.isArray(list)) {
          setBranches(list);
        }
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Default the transfer destination to the first real branch other than the
  // one the specimen currently sits at.
  useEffect(() => {
    if (transferBranchId) return;
    const candidate = branches.find((b) => b.id !== sample?.branch_id);
    if (candidate) {
      setTransferBranchId(candidate.id);
    }
  }, [branches, sample?.branch_id, transferBranchId]);

  // Toast Auto-Dismiss
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  const handleCopyAccession = async () => {
    if (!sample) return;
    try {
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(sample.accession_id);
      }
      setIsCopied(true);
      setTimeout(() => setIsCopied(false), 2000);
    } catch {
      // ignore
    }
  };

  const handleReceive = async () => {
    if (!sample) return;
    try {
      setIsReceiving(true);
      await service.receiveSample(sample.id);
      setToastMessage({
        title: t("samples:toast.received_title"),
        description: t("samples:toast.received_desc", {
          accession: sample.accession_id,
          branch: sample.branch_name,
        }),
      });
      await loadDetail();
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsReceiving(false);
    }
  };

  const handleConfirmReject = async () => {
    if (!sample) return;
    try {
      setIsRejecting(true);
      await service.rejectSample(sample.id, {
        reason_code: rejectReasonCode,
        note: rejectReasonNote.trim() || undefined,
      });
      setShowRejectModal(false);
      setToastMessage({
        title: t("samples:toast.rejected_title"),
        description: t("samples:toast.rejected_desc", {
          accession: sample.accession_id,
        }),
      });
      await loadDetail();
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsRejecting(false);
    }
  };

  const handleConfirmTransfer = async () => {
    if (!sample) return;
    try {
      setIsTransferring(true);
      await service.transferSample(sample.id, {
        to_branch_id: transferBranchId,
        notes: transferNotes.trim() || undefined,
      });
      setShowTransferModal(false);
      setToastMessage({
        title: t("samples:toast.transfer_title"),
        description: t("samples:toast.transfer_desc", {
          accession: sample.accession_id,
        }),
      });
      await loadDetail();
    } catch (err: unknown) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsTransferring(false);
    }
  };

  if (isLoading) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">{t("samples:detail.loading")}</p>
      </main>
    );
  }

  if (errorMessage || !sample) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-xl p-6 max-w-md w-full shadow-sm text-center">
          <Ban className="w-10 h-10 text-red-600 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-slate-900 mb-1">
            {t("samples:detail.not_found_title")}
          </h2>
          <p className="text-sm text-slate-600 mb-4">
            {errorMessage || t("samples:detail.not_found_body")}
          </p>
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700"
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            {t("samples:detail.back_to_accessioning")}
          </button>
        </div>
      </main>
    );
  }

  const s = sample!;
  const originBranch = branches.find((b) => b.id === s.branch_id);

  return (
    <main className="w-full min-h-screen bg-slate-50 relative pb-16">
      <div className="max-w-5xl mx-auto px-4 sm:px-6 py-6 flex flex-col gap-6">
        {/* Breadcrumb & Metadata */}
        <div className="flex flex-wrap items-center justify-between gap-y-2 text-xs text-slate-500">
          <nav
            aria-label={t("samples:breadcrumbs.aria")}
            className="flex items-center gap-1.5"
          >
            <button
              type="button"
              onClick={onBack}
              className="text-slate-600 hover:text-teal-700 transition-colors flex items-center gap-1 font-medium"
            >
              <FlaskConical className="w-4 h-4 text-teal-600" />
              <span>{t("common:nav.samples")}</span>
            </button>
            <span className="text-slate-400">/</span>
            <span className="font-mono text-slate-900 font-semibold tracking-tight">
              {s.accession_id}
            </span>
          </nav>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 font-medium text-slate-600">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>
              {formatDate(s.collected_at)} · {t("common:time.pkt")}
            </span>
          </div>
        </div>

        {/* Accession Overview Bar */}
        <section className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 flex-wrap">
            {/* Accession ID with Copy */}
            <div className="flex items-center gap-2">
              <span className="font-mono text-2xl font-bold text-slate-900 tracking-tight select-all">
                {s.accession_id}
              </span>
              <button
                type="button"
                onClick={handleCopyAccession}
                className="p-1.5 rounded-md text-slate-400 hover:text-teal-700 hover:bg-slate-100 transition-colors"
                title={t("samples:detail.copy_accession")}
                aria-label={t("samples:detail.copy_accession")}
              >
                {isCopied ? (
                  <Check className="w-4 h-4 text-emerald-600" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>

            {/* Status Pill */}
            {getStatusPill(s.status, t)}

            <span className="hidden sm:inline text-slate-300 font-light">
              |
            </span>

            {/* Patient Link */}
            <button
              type="button"
              onClick={() => onViewPatient?.(s.patient_id)}
              className="inline-flex items-center gap-1.5 text-teal-700 hover:text-teal-800 text-sm font-semibold hover:underline transition-colors text-start"
            >
              <User className="w-4 h-4 text-slate-400" />
              <span>{s.patient_name}</span>
              <span className="text-slate-500 font-normal text-xs">
                · {s.patient_mrn}
              </span>
            </button>
          </div>

          {/* Action Buttons */}
          <div className="flex items-center gap-2.5 self-start lg:self-auto flex-wrap">
            <button
              type="button"
              onClick={() => onPrintLabel?.(s.id)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm font-medium transition-all shadow-sm"
            >
              <Printer className="w-4 h-4 text-slate-500" />
              <span>{t("samples:label.breadcrumb_label")}</span>
            </button>

            <button
              type="button"
              onClick={() => setShowTransferModal(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm font-medium transition-all shadow-sm"
            >
              <ArrowRightLeft className="w-4 h-4 text-slate-500 rtl:-scale-x-100" />
              <span>{t("samples:detail.transfer_button")}</span>
            </button>

            <button
              type="button"
              onClick={() => setShowRejectModal(true)}
              disabled={s.status === "rejected"}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-red-200 text-red-600 hover:bg-red-50 text-sm font-medium transition-all shadow-sm disabled:opacity-50"
            >
              <Ban className="w-4 h-4 text-red-500" />
              <span>{t("samples:detail.reject_button")}</span>
            </button>

            <button
              type="button"
              onClick={handleReceive}
              disabled={
                isReceiving || s.status === "received" || s.status === "ready"
              }
              className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-600 hover:bg-teal-700 text-white text-sm font-medium shadow-sm transition-all active:scale-[0.98] disabled:opacity-50"
            >
              <Inbox className="w-4 h-4" />
              <span>
                {isReceiving
                  ? t("samples:detail.receiving")
                  : t("samples:detail.receive")}
              </span>
            </button>
          </div>
        </section>

        {/* Card 1: Sample Information */}
        <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 bg-slate-50 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <FlaskConical className="w-5 h-5 text-teal-700" />
              <h2 className="text-base font-semibold text-slate-900">
                {t("samples:detail.sample_information")}
              </h2>
            </div>
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-teal-50 border border-teal-200 text-teal-800 text-xs font-medium">
              <QrCode className="w-3.5 h-3.5 text-teal-600" />
              <span>{t("samples:detail.accession_verified")}</span>
            </span>
          </div>

          <div className="p-6 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {/* Patient Info */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {t("samples:detail.patient")}
              </span>
              <button
                type="button"
                onClick={() => onViewPatient?.(s.patient_id)}
                className="text-base text-teal-700 hover:text-teal-800 font-semibold text-start hover:underline"
              >
                {s.patient_name}
              </button>
              <span className="text-xs text-slate-500">
                {s.patient_mrn} ·{" "}
                {s.patient_sex === "M"
                  ? t("samples:detail.sex_male")
                  : t("samples:detail.sex_female")}
                ,{" "}
                {t("samples:detail.age_years_short", {
                  n: s.patient_age_years,
                })}
              </span>
            </div>

            {/* Tests & Tubes Requested */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {t("samples:detail.tests_requested")}
              </span>
              <div className="flex flex-wrap gap-2 pt-0.5">
                {s.sample_tests && s.sample_tests.length > 0
                  ? s.sample_tests.map((st) => (
                      <div
                        key={st.id}
                        className="inline-flex flex-col bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-md"
                      >
                        <span className="text-xs font-semibold text-slate-900">
                          {st.test_name}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {st.tube_type} · {st.specimen_type}
                        </span>
                      </div>
                    ))
                  : s.tests.map((testName, idx) => (
                      <div
                        key={idx}
                        className="inline-flex flex-col bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-md"
                      >
                        <span className="text-xs font-semibold text-slate-900">
                          {testName}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          {t("samples:detail.primary_specimen")}
                        </span>
                      </div>
                    ))}
              </div>
            </div>

            {/* Originating Branch */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {t("samples:detail.originating_branch")}
              </span>
              <span className="text-base text-slate-900 font-semibold">
                {s.branch_name}
              </span>
              <span className="text-xs text-slate-500 font-mono">
                {originBranch
                  ? `${originBranch.code} · ${
                      originBranch.is_collection_centre
                        ? t("samples:detail.collection_centre")
                        : t("samples:detail.testing_facility")
                    }`
                  : t("samples:detail.branch_facility")}
              </span>
            </div>

            {/* Collected Timestamp */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {t("samples:detail.collected")}
              </span>
              <span className="font-mono text-sm text-slate-800 font-medium">
                {s.collected_at
                  ? formatDateTime(s.collected_at)
                  : t("samples:detail.pending_collection")}
              </span>
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <User className="w-3.5 h-3.5 text-slate-400" />
                {s.collected_by ||
                  t("samples:detail.phlebotomy_station_default")}
              </span>
            </div>

            {/* Custody / Location */}
            <div className="flex flex-col gap-1 sm:col-span-2 md:col-span-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                {t("samples:detail.current_custody")}
              </span>
              <div className="flex items-center gap-2 flex-wrap pt-0.5">
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-50 border border-teal-100 text-teal-900 text-xs font-medium">
                  <MapPin className="w-3.5 h-3.5 text-teal-600" />
                  <span>
                    {s.custody_location ||
                      t("samples:detail.custody_fallback", {
                        branch: s.branch_name,
                      })}
                  </span>
                </span>
                <span className="text-xs text-slate-500">
                  {s.bench_code
                    ? t("samples:detail.station_code", { code: s.bench_code })
                    : t("samples:detail.rack_slot_fallback")}
                </span>
              </div>
            </div>
          </div>
        </section>

        {/* Card 2: Event Timeline (Oldest First) */}
        <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="px-6 py-4 bg-slate-50 border-b border-slate-200 flex items-center justify-between">
            <div className="flex items-center gap-2">
              <History className="w-5 h-5 text-teal-700" />
              <div>
                <h2 className="text-base font-semibold text-slate-900">
                  {t("samples:detail.event_timeline")}
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  {t("samples:detail.event_timeline_desc")}
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              {t("samples:detail.audit_trail")}
            </span>
          </div>

          <div className="p-6">
            <div className="relative ps-6 sm:ps-8 space-y-8 before:absolute before:start-[11px] sm:before:start-[15px] before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200">
              {s.events && s.events.length > 0 ? (
                s.events.map((evt, idx) => (
                  <div
                    key={evt.id || idx}
                    className="relative flex flex-col gap-1.5"
                  >
                    {/* Node Dot */}
                    <div className="absolute -start-6 sm:-start-8 top-1 w-6 h-6 rounded-full bg-white flex items-center justify-center">
                      <span className="w-3 h-3 rounded-full bg-teal-600 ring-4 ring-teal-50" />
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-slate-900">
                          {evt.event.replace(/_/g, " ")}
                        </span>
                        <span className="text-xs text-slate-400">
                          {t("samples:detail.event_by")}
                        </span>
                        <span className="text-xs text-slate-700 font-medium">
                          {evt.actor || t("samples:detail.system_automated")}
                        </span>
                        <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-slate-100 text-slate-700">
                          {evt.branch?.name || s.branch_name}
                        </span>
                      </div>
                      <time className="font-mono text-xs text-slate-500">
                        {new Date(evt.timestamp).toLocaleTimeString("en-GB", {
                          hour: "2-digit",
                          minute: "2-digit",
                          hour12: false,
                          timeZone: "Asia/Karachi",
                        })}{" "}
                        {t("samples:time.pkt_abbr")}
                      </time>
                    </div>

                    <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
                      {String(
                        evt.payload?.note ||
                          t("samples:detail.event_note_default"),
                      )}
                    </p>

                    <div className="flex items-center gap-3 text-xs text-slate-400 pt-0.5">
                      <span className="inline-flex items-center gap-1">
                        <Building2 className="w-3 h-3 text-slate-400" />
                        {evt.branch?.name || t("samples:detail.main_lab")}
                      </span>
                      <span>•</span>
                      <span className="font-mono text-[10px]">
                        REF-{evt.id.substring(0, 8)}
                      </span>
                    </div>
                  </div>
                ))
              ) : (
                <div className="text-xs text-slate-500 py-4">
                  {t("samples:detail.no_events")}
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Specimen Summary Footnote */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 px-2 pt-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>{t("samples:detail.custody_sealed")}</span>
          </div>
          <div className="font-mono text-[11px] text-slate-400">
            SHA-256: 7f83b165...041e
          </div>
        </div>
      </div>

      {/* Reject Sample Modal */}
      {showRejectModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2 text-red-600">
                <Ban className="w-5 h-5" />
                <h3 className="font-bold text-slate-900 text-base">
                  {t("samples:detail.reject_title")}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                aria-label={t("samples:detail.close_modal")}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                {t("samples:detail.reject_desc_pre")}{" "}
                <span className="font-semibold text-slate-800">
                  {s.patient_name}
                </span>
                {t("samples:detail.reject_desc_post")}
              </p>

              <div>
                <label
                  htmlFor={rejectCodeSelectId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  {t("samples:detail.reject_reason_label")}
                </label>
                <select
                  id={rejectCodeSelectId}
                  value={rejectReasonCode}
                  onChange={(e) =>
                    setRejectReasonCode(e.target.value as RejectionReasonCode)
                  }
                  className="w-full text-xs rounded-lg border border-slate-300 py-2 px-3 focus:outline-none focus:ring-2 focus:ring-red-500"
                >
                  {REJECTION_REASONS.map((r) => (
                    <option key={r.code} value={r.code}>
                      {t(r.key)}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor={rejectNoteInputId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  {t("samples:detail.reject_note_label")}
                </label>
                <textarea
                  id={rejectNoteInputId}
                  rows={3}
                  value={rejectReasonNote}
                  onChange={(e) => setRejectReasonNote(e.target.value)}
                  placeholder={t("samples:detail.reject_note_placeholder")}
                  className="w-full text-xs rounded-lg border border-slate-300 py-2 px-3 focus:outline-none focus:ring-2 focus:ring-red-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-lg"
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="button"
                onClick={handleConfirmReject}
                disabled={isRejecting}
                className="px-4 py-2 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg shadow-sm disabled:opacity-50"
              >
                {isRejecting
                  ? t("samples:detail.rejecting")
                  : t("samples:detail.confirm_rejection")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Transfer Sample Modal */}
      {showTransferModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-slate-900/40 backdrop-blur-sm">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full p-6 animate-in fade-in zoom-in-95">
            <div className="flex items-center justify-between pb-3 border-b border-slate-100">
              <div className="flex items-center gap-2 text-teal-700">
                <ArrowRightLeft className="w-5 h-5 rtl:-scale-x-100" />
                <h3 className="font-bold text-slate-900 text-base">
                  {t("samples:detail.transfer_title")}
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowTransferModal(false)}
                aria-label={t("samples:detail.close_modal")}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                {t("samples:detail.transfer_desc_pre")}{" "}
                <span className="font-mono font-semibold text-slate-800">
                  <bdi dir="ltr">{s.accession_id}</bdi>
                </span>{" "}
                {t("samples:detail.transfer_desc_post")}
              </p>

              <div>
                <label
                  htmlFor={transferBranchSelectId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  {t("samples:detail.transfer_branch_label")}
                </label>
                <select
                  id={transferBranchSelectId}
                  value={transferBranchId}
                  onChange={(e) => setTransferBranchId(e.target.value)}
                  className="w-full text-xs rounded-lg border border-slate-300 py-2 px-3 focus:outline-none focus:ring-2 focus:ring-teal-500"
                >
                  {branches.filter((b) => b.id !== s.branch_id).length ===
                    0 && (
                    <option value="">
                      {t("samples:detail.transfer_no_branch")}
                    </option>
                  )}
                  {branches
                    .filter((b) => b.id !== s.branch_id)
                    .map((b) => (
                      <option key={b.id} value={b.id}>
                        {b.name}
                      </option>
                    ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor={transferNoteInputId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  {t("samples:detail.transfer_notes_label")}
                </label>
                <textarea
                  id={transferNoteInputId}
                  rows={3}
                  value={transferNotes}
                  onChange={(e) => setTransferNotes(e.target.value)}
                  placeholder={t("samples:detail.transfer_notes_placeholder")}
                  className="w-full text-xs rounded-lg border border-slate-300 py-2 px-3 focus:outline-none focus:ring-2 focus:ring-teal-500"
                />
              </div>
            </div>

            <div className="flex items-center justify-end gap-3 pt-4 border-t border-slate-100">
              <button
                type="button"
                onClick={() => setShowTransferModal(false)}
                className="px-4 py-2 text-xs font-medium text-slate-600 hover:text-slate-800 rounded-lg"
              >
                {t("common:actions.cancel")}
              </button>
              <button
                type="button"
                onClick={handleConfirmTransfer}
                disabled={isTransferring || !transferBranchId}
                className="px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg shadow-sm disabled:opacity-50"
              >
                {isTransferring
                  ? t("samples:detail.dispatching")
                  : t("samples:detail.initiate_transfer")}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Floating Toast Notification */}
      {toastMessage && (
        <aside
          role="status"
          aria-live="polite"
          className="fixed bottom-4 end-4 z-50 bg-white rounded-lg shadow-lg border border-slate-200 p-4 max-w-sm w-80 flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2"
        >
          <CheckCircle2 className="w-5 h-5 text-emerald-600 shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h4 className="text-xs font-semibold text-slate-900">
              {toastMessage.title}
            </h4>
            <p className="text-xs text-slate-600 mt-0.5 leading-snug">
              {toastMessage.description}
            </p>
            <span className="block text-[10px] text-slate-400 mt-1 font-mono">
              {t("samples:detail.auto_dismiss")}
            </span>
          </div>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-slate-600 p-1"
            aria-label={t("samples:detail.close_notification")}
          >
            <X className="w-4 h-4" />
          </button>
        </aside>
      )}
    </main>
  );
}
