import { useCallback, useEffect, useId, useState } from "react";
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

const REJECTION_REASONS: Array<{ code: RejectionReasonCode; label: string }> = [
  { code: "hemolyzed", label: "Gross hemolysis detected on centrifugation" },
  { code: "clotted", label: "Clotted EDTA / micro-clots detected" },
  { code: "insufficient_volume", label: "Quantity not sufficient (QNS)" },
  { code: "wrong_tube", label: "Incorrect tube type or additive" },
  { code: "mislabelled", label: "Mislabeled / unlabeled tube" },
  { code: "damaged_transport", label: "Container cracked or leaking" },
  { code: "other", label: "Other quality deviation" },
];

function getStatusPill(status: SampleStatus): JSX.Element {
  switch (status) {
    case "collected":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-blue-50 text-blue-700 border border-blue-200">
          <span className="w-2 h-2 rounded-full bg-blue-600" />
          Collected
        </span>
      );
    case "received":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-teal-50 text-teal-800 border border-teal-200">
          <span className="w-2 h-2 rounded-full bg-teal-600" />
          Received
        </span>
      );
    case "in_process":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-orange-50 text-orange-800 border border-orange-200">
          <span className="w-2 h-2 rounded-full bg-orange-500 animate-pulse" />
          In process
        </span>
      );
    case "ready":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-emerald-50 text-emerald-800 border border-emerald-200">
          <span className="w-2 h-2 rounded-full bg-emerald-600" />
          Ready / Reported
        </span>
      );
    case "rejected":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-red-50 text-red-800 border border-red-200">
          <span className="w-2 h-2 rounded-full bg-red-600" />
          Rejected
        </span>
      );
    case "cancelled":
      return (
        <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700 border border-slate-200">
          <span className="w-2 h-2 rounded-full bg-slate-500" />
          Cancelled
        </span>
      );
    default:
      return (
        <span className="inline-flex items-center px-3 py-1 rounded-full text-xs font-semibold bg-slate-100 text-slate-700">
          {status}
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
      const msg =
        err instanceof Error ? err.message : "Failed to load sample details";
      setErrorMessage(msg);
    } finally {
      setIsLoading(false);
    }
  }, [sampleId, service]);

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
    const t = setTimeout(() => setToastMessage(null), 5000);
    return () => clearTimeout(t);
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
        title: "Sample received",
        description: `${sample.accession_id} is now received at ${sample.branch_name}.`,
      });
      await loadDetail();
    } catch (err: unknown) {
      const msg =
        err instanceof Error ? err.message : "Failed to receive sample";
      setErrorMessage(msg);
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
        title: "Sample rejected",
        description: `Accession ${sample.accession_id} marked as rejected. Recollection flagged.`,
      });
      await loadDetail();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Rejection failed";
      setErrorMessage(msg);
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
        title: "Transfer initiated",
        description: `Specimen transit record created for ${sample.accession_id}.`,
      });
      await loadDetail();
    } catch (err: unknown) {
      const msg = err instanceof Error ? err.message : "Transfer failed";
      setErrorMessage(msg);
    } finally {
      setIsTransferring(false);
    }
  };

  if (isLoading) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">Loading sample record...</p>
      </main>
    );
  }

  if (errorMessage || !sample) {
    return (
      <main className="w-full min-h-screen bg-slate-50 flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-xl p-6 max-w-md w-full shadow-sm text-center">
          <Ban className="w-10 h-10 text-red-600 mx-auto mb-3" />
          <h2 className="text-lg font-bold text-slate-900 mb-1">
            Accession Not Found
          </h2>
          <p className="text-sm text-slate-600 mb-4">
            {errorMessage || "Sample record could not be retrieved."}
          </p>
          <button
            type="button"
            onClick={onBack}
            className="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-teal-600 text-white text-sm font-medium hover:bg-teal-700"
          >
            <ArrowLeft className="w-4 h-4" />
            Back to Accessioning
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
          <nav aria-label="Breadcrumb" className="flex items-center gap-1.5">
            <button
              type="button"
              onClick={onBack}
              className="text-slate-600 hover:text-teal-700 transition-colors flex items-center gap-1 font-medium"
            >
              <FlaskConical className="w-4 h-4 text-teal-600" />
              <span>Samples</span>
            </button>
            <span className="text-slate-400">/</span>
            <span className="font-mono text-slate-900 font-semibold tracking-tight">
              {s.accession_id}
            </span>
          </nav>
          <div className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md bg-slate-100 font-medium text-slate-600">
            <Clock className="w-3.5 h-3.5 text-slate-400" />
            <span>20 Oct 2026 · times are PKT</span>
          </div>
        </div>

        {/* Accession Overview Bar */}
        <section className="bg-white rounded-xl p-5 border border-slate-200 shadow-sm flex flex-col lg:flex-row lg:items-center justify-between gap-5">
          <div className="flex flex-col sm:flex-row sm:items-center gap-3 sm:gap-4 flex-wrap">
            {/* Accession ID with Copy */}
            <div className="flex items-center gap-2">
              <span className="text-2xl font-bold text-slate-900 tracking-tight font-mono select-all">
                {s.accession_id}
              </span>
              <button
                type="button"
                onClick={handleCopyAccession}
                className="p-1.5 rounded-md text-slate-400 hover:text-teal-700 hover:bg-slate-100 transition-colors"
                title="Copy Accession ID"
                aria-label="Copy Accession ID"
              >
                {isCopied ? (
                  <Check className="w-4 h-4 text-emerald-600" />
                ) : (
                  <Copy className="w-4 h-4" />
                )}
              </button>
            </div>

            {/* Status Pill */}
            {getStatusPill(s.status)}

            <span className="hidden sm:inline text-slate-300 font-light">
              |
            </span>

            {/* Patient Link */}
            <button
              type="button"
              onClick={() => onViewPatient?.(s.patient_id)}
              className="inline-flex items-center gap-1.5 text-teal-700 hover:text-teal-800 text-sm font-semibold hover:underline transition-colors text-left"
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
              <span>Label</span>
            </button>

            <button
              type="button"
              onClick={() => setShowTransferModal(true)}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-slate-300 text-slate-700 hover:bg-slate-50 text-sm font-medium transition-all shadow-sm"
            >
              <ArrowRightLeft className="w-4 h-4 text-slate-500" />
              <span>Transfer</span>
            </button>

            <button
              type="button"
              onClick={() => setShowRejectModal(true)}
              disabled={s.status === "rejected"}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg bg-white border border-red-200 text-red-600 hover:bg-red-50 text-sm font-medium transition-all shadow-sm disabled:opacity-50"
            >
              <Ban className="w-4 h-4 text-red-500" />
              <span>Reject</span>
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
              <span>{isReceiving ? "Receiving..." : "Receive"}</span>
            </button>
          </div>
        </section>

        {/* Card 1: Sample Information */}
        <section className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 bg-slate-50 border-b border-slate-200">
            <div className="flex items-center gap-2">
              <FlaskConical className="w-5 h-5 text-teal-700" />
              <h2 className="text-base font-semibold text-slate-900">
                Sample information
              </h2>
            </div>
            <span className="inline-flex items-center gap-1 px-2.5 py-1 rounded bg-teal-50 border border-teal-200 text-teal-800 text-xs font-medium">
              <QrCode className="w-3.5 h-3.5 text-teal-600" />
              <span>Accession Verified</span>
            </span>
          </div>

          <div className="p-6 grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-6">
            {/* Patient Info */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Patient
              </span>
              <button
                type="button"
                onClick={() => onViewPatient?.(s.patient_id)}
                className="text-base text-teal-700 hover:text-teal-800 font-semibold text-left hover:underline"
              >
                {s.patient_name}
              </button>
              <span className="text-xs text-slate-500">
                {s.patient_mrn} · {s.patient_sex === "M" ? "Male" : "Female"},{" "}
                {s.patient_age_years}y
              </span>
            </div>

            {/* Tests & Tubes Requested */}
            <div className="flex flex-col gap-1.5">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Tests Requested
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
                  : s.tests.map((t, idx) => (
                      <div
                        key={idx}
                        className="inline-flex flex-col bg-slate-50 border border-slate-200 px-2.5 py-1 rounded-md"
                      >
                        <span className="text-xs font-semibold text-slate-900">
                          {t}
                        </span>
                        <span className="text-[10px] text-slate-500 font-mono">
                          Primary Specimen
                        </span>
                      </div>
                    ))}
              </div>
            </div>

            {/* Originating Branch */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Originating Branch
              </span>
              <span className="text-base text-slate-900 font-semibold">
                {s.branch_name}
              </span>
              <span className="text-xs text-slate-500 font-mono">
                {originBranch
                  ? `${originBranch.code} · ${
                      originBranch.is_collection_centre
                        ? "Collection Centre"
                        : "Testing Facility"
                    }`
                  : "Branch facility"}
              </span>
            </div>

            {/* Collected Timestamp */}
            <div className="flex flex-col gap-1">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Collected
              </span>
              <span className="font-mono text-sm text-slate-800 font-medium">
                {s.collected_at
                  ? new Date(s.collected_at).toLocaleString("en-GB", {
                      day: "2-digit",
                      month: "short",
                      year: "numeric",
                      hour: "2-digit",
                      minute: "2-digit",
                      hour12: false,
                      timeZone: "Asia/Karachi",
                    })
                  : "Pending collection"}
              </span>
              <span className="text-xs text-slate-500 flex items-center gap-1">
                <User className="w-3.5 h-3.5 text-slate-400" />
                {s.collected_by || "Phlebotomy Station #01"}
              </span>
            </div>

            {/* Custody / Location */}
            <div className="flex flex-col gap-1 sm:col-span-2 md:col-span-2">
              <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
                Current Physical Custody
              </span>
              <div className="flex items-center gap-2 flex-wrap pt-0.5">
                <span className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg bg-teal-50 border border-teal-100 text-teal-900 text-xs font-medium">
                  <MapPin className="w-3.5 h-3.5 text-teal-600" />
                  <span>
                    {s.custody_location ||
                      `${s.branch_name} — Specimen Bench A`}
                  </span>
                </span>
                <span className="text-xs text-slate-500">
                  {s.bench_code
                    ? `Station ${s.bench_code}`
                    : "Rack 04 / Slot 12"}
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
                  Event timeline
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Chronological chain of custody and status events (oldest
                  first)
                </p>
              </div>
            </div>
            <span className="text-xs font-semibold text-slate-400 uppercase tracking-wider">
              ISO 15189 Audit Trail
            </span>
          </div>

          <div className="p-6">
            <div className="relative pl-6 sm:pl-8 space-y-8 before:absolute before:left-[11px] sm:before:left-[15px] before:top-3 before:bottom-3 before:w-0.5 before:bg-slate-200">
              {s.events && s.events.length > 0 ? (
                s.events.map((evt, idx) => (
                  <div
                    key={evt.id || idx}
                    className="relative flex flex-col gap-1.5"
                  >
                    {/* Node Dot */}
                    <div className="absolute -left-6 sm:-left-8 top-1 w-6 h-6 rounded-full bg-white flex items-center justify-center">
                      <span className="w-3 h-3 rounded-full bg-teal-600 ring-4 ring-teal-50" />
                    </div>

                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-1">
                      <div className="flex items-center gap-2 flex-wrap">
                        <span className="text-sm font-semibold text-slate-900">
                          {evt.event.replace(/_/g, " ")}
                        </span>
                        <span className="text-xs text-slate-400">by</span>
                        <span className="text-xs text-slate-700 font-medium">
                          {evt.actor || "System Automated"}
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
                        PKT
                      </time>
                    </div>

                    <p className="text-xs text-slate-600 leading-relaxed max-w-3xl">
                      {String(
                        evt.payload?.note ||
                          "Event recorded in specimen custody system.",
                      )}
                    </p>

                    <div className="flex items-center gap-3 text-xs text-slate-400 pt-0.5">
                      <span className="inline-flex items-center gap-1">
                        <Building2 className="w-3 h-3 text-slate-400" />
                        {evt.branch?.name || "Main Lab"}
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
                  No previous custody events logged for this accession.
                </div>
              )}
            </div>
          </div>
        </section>

        {/* Specimen Summary Footnote */}
        <div className="flex flex-col sm:flex-row items-center justify-between gap-3 text-xs text-slate-500 px-2 pt-2">
          <div className="flex items-center gap-2">
            <ShieldCheck className="w-4 h-4 text-emerald-600" />
            <span>
              Chain of custody digitally sealed under ISO 15189 compliance
            </span>
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
                  Reject Specimen
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowRejectModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Rejection permanently stops testing on this specimen and prompts
                a recollection request for patient{" "}
                <span className="font-semibold text-slate-800">
                  {s.patient_name}
                </span>
                .
              </p>

              <div>
                <label
                  htmlFor={rejectCodeSelectId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  Quality Non-Conformance Reason *
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
                      {r.label}
                    </option>
                  ))}
                </select>
              </div>

              <div>
                <label
                  htmlFor={rejectNoteInputId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  Internal Laboratory Note (Optional)
                </label>
                <textarea
                  id={rejectNoteInputId}
                  rows={3}
                  value={rejectReasonNote}
                  onChange={(e) => setRejectReasonNote(e.target.value)}
                  placeholder="Detail visible specimen anomalies for supervisor review..."
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
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmReject}
                disabled={isRejecting}
                className="px-4 py-2 text-xs font-semibold text-white bg-red-600 hover:bg-red-700 rounded-lg shadow-sm disabled:opacity-50"
              >
                {isRejecting ? "Rejecting..." : "Confirm Rejection"}
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
                <ArrowRightLeft className="w-5 h-5" />
                <h3 className="font-bold text-slate-900 text-base">
                  Transfer Specimen
                </h3>
              </div>
              <button
                type="button"
                onClick={() => setShowTransferModal(false)}
                className="text-slate-400 hover:text-slate-600 p-1 rounded-md"
              >
                <X className="w-5 h-5" />
              </button>
            </div>

            <div className="py-4 space-y-4">
              <p className="text-xs text-slate-600 leading-relaxed">
                Dispatch accession{" "}
                <span className="font-mono font-semibold text-slate-800">
                  {s.accession_id}
                </span>{" "}
                to another laboratory facility with cold-chain custody tracking.
              </p>

              <div>
                <label
                  htmlFor={transferBranchSelectId}
                  className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-1"
                >
                  Destination Branch / Lab *
                </label>
                <select
                  id={transferBranchSelectId}
                  value={transferBranchId}
                  onChange={(e) => setTransferBranchId(e.target.value)}
                  className="w-full text-xs rounded-lg border border-slate-300 py-2 px-3 focus:outline-none focus:ring-2 focus:ring-teal-500"
                >
                  {branches.filter((b) => b.id !== s.branch_id).length ===
                    0 && <option value="">No other branch available</option>}
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
                  Courier / Transit Notes (Optional)
                </label>
                <textarea
                  id={transferNoteInputId}
                  rows={3}
                  value={transferNotes}
                  onChange={(e) => setTransferNotes(e.target.value)}
                  placeholder="e.g. Courier Box #04, cold pack temperature verified 4°C"
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
                Cancel
              </button>
              <button
                type="button"
                onClick={handleConfirmTransfer}
                disabled={isTransferring || !transferBranchId}
                className="px-4 py-2 text-xs font-semibold text-white bg-teal-600 hover:bg-teal-700 rounded-lg shadow-sm disabled:opacity-50"
              >
                {isTransferring ? "Dispatching..." : "Initiate Transfer"}
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
          className="fixed bottom-4 right-4 z-50 bg-white rounded-lg shadow-lg border border-slate-200 p-4 max-w-sm w-80 flex items-start gap-3 animate-in fade-in slide-in-from-bottom-2"
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
              Auto-dismiss in 5s
            </span>
          </div>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="text-slate-400 hover:text-slate-600 p-1"
            aria-label="Close notification"
          >
            <X className="w-4 h-4" />
          </button>
        </aside>
      )}
    </main>
  );
}
