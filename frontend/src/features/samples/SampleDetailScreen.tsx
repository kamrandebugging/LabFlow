import { useCallback, useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router-dom";
import { useTranslation } from "react-i18next";
import {
  ArrowLeft,
  ArrowRightLeft,
  Ban,
  CheckCircle2,
  ExternalLink,
  Printer,
  RotateCw,
  Truck,
  X,
  AlertCircle,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { useDialogFocus } from "../../lib/dialogFocus";
import { sampleService } from "./sampleService";
import { useAuthStore } from "../auth/authStore";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import type {
  RejectionReasonCode,
  SampleDetail,
} from "./types";
import { SampleStatusPill, SampleTimeline } from "./components";
import styles from "./SampleDetailScreen.module.css";

export interface SampleDetailScreenProps {
  sampleId: string;
  onBack?: () => void;
  onPrintLabel?: (sampleId: string) => void;
  onViewPatient?: (patientId: string) => void;
  service?: typeof sampleService;
}

const REJECTION_REASONS: Array<{ code: RejectionReasonCode; label: string }> = [
  { code: "unlabelled", label: "Unlabelled" },
  { code: "mislabelled", label: "Mislabelled" },
  { code: "hemolyzed", label: "Hemolyzed" },
  { code: "insufficient_volume", label: "Insufficient Volume" },
  { code: "wrong_tube", label: "Wrong Tube Type" },
  { code: "clotted", label: "Clotted" },
  { code: "lipemic", label: "Lipemic" },
  { code: "damaged_transport", label: "Damaged in Transport" },
  { code: "barcode_issue", label: "Barcode Unreadable" },
  { code: "other", label: "Other (Clinical Justification Required)" },
];

export function SampleDetailScreen({
  sampleId,
  onBack,
  onPrintLabel,
  onViewPatient,
  service = sampleService,
}: SampleDetailScreenProps): JSX.Element {
  const { t } = useTranslation(["samples", "common"]);
  let navigate = (to: string, _opts?: any) => {
    window.location.href = to;
  };
  try {
    navigate = useNavigate();
  } catch {
    // Outside router context
  }

  let toastFromLocation: string | null = null;
  try {
    const loc = useLocation();
    toastFromLocation = (loc?.state as { toast?: string })?.toast || null;
  } catch {
    // Outside router context
  }

  const user = useAuthStore((s) => s.user);
  const userRole = (user?.role || "").toLowerCase();

  // Role permissions
  const isOwner = userRole === "owner";
  const isManager = userRole === "manager";
  const isTechnician = userRole === "technician";
  const isReception = userRole === "reception";
  const isPathologist = userRole === "pathologist";

  // Data States
  const [sample, setSample] = useState<SampleDetail | null>(null);
  const [branches, setBranches] = useState<Branch[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [errorMessage, setErrorMessage] = useState<string | null>(null);
  const [actionLoading, setActionLoading] = useState(false);

  // Toast Notification
  const [toastMessage, setToastMessage] = useState<string | null>(
    toastFromLocation,
  );

  // Modals Open State
  const [rejectModalOpen, setRejectModalOpen] = useState(false);
  const [rejectionCode, setRejectionCode] = useState<RejectionReasonCode | "">("");
  const [rejectionNote, setRejectionNote] = useState("");

  const [transferModalOpen, setTransferModalOpen] = useState(false);
  const [transferBranchId, setTransferBranchId] = useState("");
  const [transferNotes, setTransferNotes] = useState("");

  const [cancelModalOpen, setCancelModalOpen] = useState(false);
  const [cancelReason, setCancelReason] = useState("");

  const [recollectModalOpen, setRecollectModalOpen] = useState(false);
  const [markLostModalOpen, setMarkLostModalOpen] = useState(false);
  const [markLostNote, setMarkLostNote] = useState("");

  // WCAG Focus Traps for Modals
  const rejectPanelRef = useDialogFocus(rejectModalOpen, () =>
    setRejectModalOpen(false),
  );
  const transferPanelRef = useDialogFocus(transferModalOpen, () =>
    setTransferModalOpen(false),
  );
  const cancelPanelRef = useDialogFocus(cancelModalOpen, () =>
    setCancelModalOpen(false),
  );
  const recollectPanelRef = useDialogFocus(recollectModalOpen, () =>
    setRecollectModalOpen(false),
  );
  const markLostPanelRef = useDialogFocus(markLostModalOpen, () =>
    setMarkLostModalOpen(false),
  );

  // Load sample detail
  const loadDetail = useCallback(async () => {
    try {
      setIsLoading(true);
      setErrorMessage(null);
      const data = await service.getSample(sampleId);
      setSample(data);
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setIsLoading(false);
    }
  }, [sampleId, service, t]);

  useEffect(() => {
    loadDetail();
  }, [loadDetail]);

  // Load branches
  useEffect(() => {
    let active = true;
    void settingsService
      .getBranches(false)
      .then((list) => {
        if (active && Array.isArray(list)) setBranches(list);
      })
      .catch(() => {});
    return () => {
      active = false;
    };
  }, []);

  // Toast auto-dismiss
  useEffect(() => {
    if (!toastMessage) return;
    const timer = setTimeout(() => setToastMessage(null), 5000);
    return () => clearTimeout(timer);
  }, [toastMessage]);

  if (isLoading && !sample) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8 text-slate-600">
        <RotateCw className="w-8 h-8 animate-spin text-teal-600 mb-3" />
        <p className="text-sm font-medium">Loading sample details...</p>
      </main>
    );
  }

  if (errorMessage && !sample) {
    return (
      <main className="w-full min-h-[60vh] flex flex-col items-center justify-center p-8">
        <div className="bg-white border border-red-200 rounded-2xl p-6 max-w-md w-full shadow-sm text-center">
          <p className="text-sm text-red-600 mb-4">{errorMessage}</p>
          <button
            type="button"
            onClick={onBack || (() => navigate("/samples"))}
            className={styles.primaryBlackPill}
          >
            <ArrowLeft className="w-4 h-4 rtl:rotate-180" />
            <span>Back to Samples</span>
          </button>
        </div>
      </main>
    );
  }

  if (!sample) return <div />;

  const hasOpenTransfer = Boolean(sample.open_transfer);
  const status = sample.status;

  // Role Gating
  const canReceive =
    (isOwner || isManager || isTechnician) &&
    status === "collected" &&
    !hasOpenTransfer;

  const canReject =
    !hasOpenTransfer &&
    ((status === "collected" &&
      (isOwner || isManager || isReception || isTechnician)) ||
      ((status === "received" || status === "in_process") &&
        (isOwner || isManager || isTechnician)));

  const canRecollect =
    (isOwner || isManager || isReception || isTechnician) &&
    status === "rejected";

  const canCancelSample =
    (isOwner || isManager) &&
    (status === "collected" || status === "received") &&
    !hasOpenTransfer;

  const canCreateTransfer =
    (isOwner || isManager || isReception || isTechnician) &&
    (status === "collected" || status === "received") &&
    !hasOpenTransfer &&
    branches.length > 1;

  const canPrintLabel =
    (isOwner || isManager || isReception || isTechnician) && !isPathologist;

  // Actions execution
  const handleReceiveSample = async () => {
    try {
      setActionLoading(true);
      await service.receiveSample(sample.id);
      setToastMessage("✓ Sample received into accessioning");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRejectSubmit = async () => {
    if (!rejectionCode) return;
    if (rejectionCode === "other" && !rejectionNote.trim()) {
      setErrorMessage("Note is mandatory when rejection reason is 'Other'.");
      return;
    }
    try {
      setActionLoading(true);
      await service.rejectSample(sample.id, {
        reason_code: rejectionCode,
        note: rejectionNote.trim() || undefined,
      });
      setRejectModalOpen(false);
      setToastMessage("✓ Specimen rejected for non-conformance");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleRecollectConfirm = async () => {
    try {
      setActionLoading(true);
      const res = await service.recollectSample(sample.id);
      setRecollectModalOpen(false);
      navigate(`/samples/${res.id}`, {
        state: {
          toast: `✓ Recollection accession ${res.accession_id} created`,
        },
      });
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelSampleSubmit = async () => {
    if (!cancelReason.trim()) return;
    try {
      setActionLoading(true);
      await service.cancelSample(sample.id, { reason: cancelReason.trim() });
      setCancelModalOpen(false);
      setToastMessage("✓ Sample accession cancelled");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleTransferSubmit = async () => {
    if (!transferBranchId) return;
    try {
      setActionLoading(true);
      await service.transferSample(sample.id, {
        to_branch_id: transferBranchId,
        notes: transferNotes.trim() || undefined,
      });
      setTransferModalOpen(false);
      setToastMessage("✓ Inter-branch transfer dispatched");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  // Open Transfer Actions
  const handleReceiveTransferAction = async () => {
    if (!sample.open_transfer) return;
    try {
      setActionLoading(true);
      await service.receiveTransfer(sample.open_transfer.id);
      setToastMessage("✓ Transferred specimen received at destination");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleCancelTransferAction = async () => {
    if (!sample.open_transfer) return;
    if (
      !window.confirm(
        "Are you sure you want to cancel this transfer? Specimen remains at sending branch.",
      )
    ) {
      return;
    }
    try {
      setActionLoading(true);
      await service.cancelTransfer(sample.open_transfer.id);
      setToastMessage("✓ Inter-branch transfer cancelled");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  const handleMarkLostAction = async () => {
    if (!sample.open_transfer || !markLostNote.trim()) return;
    try {
      setActionLoading(true);
      await service.markLostTransfer(
        sample.open_transfer.id,
        markLostNote.trim(),
      );
      setMarkLostModalOpen(false);
      setMarkLostNote("");
      setToastMessage("✓ Specimen marked lost in transit");
      await loadDetail();
    } catch (err) {
      setErrorMessage(messageForError(err, t));
    } finally {
      setActionLoading(false);
    }
  };

  return (
    <div className={styles.pageContainer}>
      {/* 1. Header Row */}
      <header className={styles.headerRow}>
        <div className={styles.titleArea}>
          <div className="flex items-center gap-2 mb-1">
            <button
              type="button"
              onClick={onBack || (() => navigate("/samples"))}
              className="text-xs text-slate-500 hover:text-slate-800 flex items-center gap-1 transition-colors"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>Back to Samples</span>
            </button>
          </div>
          <h1 className={styles.accessionTitle}>{sample.accession_id}</h1>
          <div className={styles.subtitle}>
            <span className="font-semibold text-slate-900">
              {sample.patient_name}
            </span>
            <span>·</span>
            <span className="font-mono">{sample.patient_mrn}</span>
            <span>·</span>
            <span>{sample.branch_name}</span>
            {sample.collected_at && (
              <>
                <span>·</span>
                <span>Collected {sample.age_display || "recently"}</span>
              </>
            )}
          </div>
        </div>

        <div className={styles.headerActions}>
          {canPrintLabel && (
            <button
              type="button"
              onClick={() => {
                if (onPrintLabel) onPrintLabel(sample.id);
                else navigate(`/samples/${sample.id}/label`);
              }}
              className={styles.outlinePill}
            >
              <Printer className="w-4 h-4" />
              <span>Print label</span>
            </button>
          )}
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

      {/* 2. Main Content Grid (2/3 Main, 1/3 Right Rail) */}
      <div className={styles.contentGrid}>
        {/* Main Column */}
        <div className={styles.mainColumn}>
          {/* Status & Custody Card */}
          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Specimen Status & Custody</h2>
              <SampleStatusPill status={sample.status} />
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-slate-400 block font-medium">
                  Collected At
                </span>
                <span className="font-mono text-slate-800 font-semibold mt-0.5 block">
                  {sample.collected_at
                    ? new Date(sample.collected_at).toLocaleString("en-GB", {
                        day: "2-digit",
                        month: "short",
                        year: "numeric",
                        hour: "2-digit",
                        minute: "2-digit",
                        timeZone: "Asia/Karachi",
                      })
                    : "—"}
                </span>
              </div>
              {sample.collected_by && (
                <div>
                  <span className="text-slate-400 block font-medium">
                    Collected By
                  </span>
                  <span className="text-slate-800 font-semibold mt-0.5 block">
                    {sample.collected_by}
                  </span>
                </div>
              )}
              {sample.custody_location && (
                <div>
                  <span className="text-slate-400 block font-medium">
                    Custody Location
                  </span>
                  <span className="text-slate-800 font-semibold mt-0.5 block">
                    {sample.custody_location}
                  </span>
                </div>
              )}
              {sample.bench_code && (
                <div>
                  <span className="text-slate-400 block font-medium">
                    Bench Code
                  </span>
                  <span className="font-mono text-slate-800 font-semibold mt-0.5 block">
                    {sample.bench_code}
                  </span>
                </div>
              )}
            </div>
            {sample.collection_notes && (
              <div className="p-3 bg-slate-50 border border-slate-200 rounded-xl text-xs text-slate-700">
                <span className="font-bold text-slate-900 block mb-0.5">
                  Collection Notes:
                </span>
                <span>{sample.collection_notes}</span>
              </div>
            )}
          </section>

          {/* Patient Demographics Card */}
          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Patient Identity</h2>
              {onViewPatient && (
                <button
                  type="button"
                  onClick={() => onViewPatient(sample.patient_id)}
                  className="text-xs font-semibold text-teal-700 hover:text-teal-900 flex items-center gap-1"
                >
                  <span>View record</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
            <div className="grid grid-cols-2 md:grid-cols-4 gap-4 text-xs">
              <div>
                <span className="text-slate-400 block font-medium">
                  Full Name
                </span>
                <span className="font-semibold text-slate-900 mt-0.5 block">
                  {sample.patient_name}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">MRN</span>
                <span className="font-mono font-semibold text-slate-900 mt-0.5 block">
                  {sample.patient_mrn}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">
                  Age / Gender
                </span>
                <span className="text-slate-800 font-medium mt-0.5 block">
                  {sample.patient_age_years ? `${sample.patient_age_years}y` : "—"}{" "}
                  {sample.patient_sex ? `· ${sample.patient_sex}` : ""}
                </span>
              </div>
              <div>
                <span className="text-slate-400 block font-medium">
                  Linked Invoice
                </span>
                <span className="font-mono text-slate-800 font-medium mt-0.5 block">
                  {sample.invoice_id}
                </span>
              </div>
            </div>
          </section>

          {/* Test Parameters Card */}
          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Diagnostic Tests & Panels</h2>
              <span className="text-xs text-slate-500">
                {(sample.sample_tests || []).length} assigned
              </span>
            </div>
            <div className="space-y-3">
              {(sample.sample_tests || []).map((tItem) => (
                <div
                  key={tItem.id}
                  className="p-3.5 bg-slate-50 border border-slate-200 rounded-xl flex flex-col md:flex-row md:items-center justify-between gap-2 text-xs"
                >
                  <div>
                    <div className="font-bold text-slate-900 text-sm">
                      {tItem.test_name}{" "}
                      <span className="text-slate-400 font-mono text-xs font-normal">
                        ({tItem.test_code})
                      </span>
                    </div>
                    <div className="text-slate-500 mt-0.5 flex items-center gap-2">
                      {tItem.category && <span>Category: {tItem.category}</span>}
                      {tItem.tube_type && (
                        <span>· Tube: {tItem.tube_type}</span>
                      )}
                      {tItem.required_volume_ml && (
                        <span>· Vol: {tItem.required_volume_ml} mL</span>
                      )}
                    </div>
                  </div>
                  <div className="text-slate-600 font-mono">
                    {tItem.reference_range ? (
                      <span>
                        Ref: {tItem.reference_range.low ?? "—"} –{" "}
                        {tItem.reference_range.high ?? "—"}{" "}
                        {tItem.reference_range.unit || ""}
                      </span>
                    ) : (
                      <span className="text-slate-400 italic">
                        Not configured
                      </span>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </section>

          {/* Chain of Custody Audit Timeline (Phase 2.7) */}
          <section className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Chain of Custody Timeline</h2>
              <span className="text-xs text-slate-400">
                ISO 15189 Immutable Log
              </span>
            </div>
            <SampleTimeline events={sample.events} />
          </section>
        </div>

        {/* Right Rail */}
        <aside className={styles.rightRail}>
          {/* Open Transfer Banner & Actions */}
          {hasOpenTransfer && sample.open_transfer && (
            <div className={styles.openTransferBanner}>
              <div className={styles.transferBannerHeader}>
                <span className="text-xs font-bold text-teal-800 uppercase tracking-wider flex items-center gap-1.5">
                  <Truck className="w-4 h-4 text-teal-600" />
                  <span>Transfer in transit</span>
                </span>
                <SampleStatusPill status={sample.open_transfer.status} />
              </div>
              <div className={styles.transferRouteText}>
                {sample.open_transfer.from_branch.name} →{" "}
                {sample.open_transfer.to_branch.name}
              </div>
              <div className={styles.transferMetaText}>
                Dispatched:{" "}
                {new Date(sample.open_transfer.dispatched_at).toLocaleString(
                  "en-GB",
                  { hour: "2-digit", minute: "2-digit" },
                )}
              </div>
              <div className="pt-2 flex flex-col gap-2">
                {/* Destination Branch Receive */}
                {(isOwner || isManager || isTechnician) && (
                  <button
                    type="button"
                    disabled={actionLoading}
                    onClick={handleReceiveTransferAction}
                    className={styles.primaryBlackPill}
                  >
                    Receive at Destination
                  </button>
                )}
                {/* Sender Branch Actions */}
                {(isOwner || isManager) && (
                  <div className="flex items-center gap-2">
                    <button
                      type="button"
                      disabled={actionLoading}
                      onClick={handleCancelTransferAction}
                      className={styles.outlinePill}
                    >
                      Cancel Transfer
                    </button>
                    <button
                      type="button"
                      disabled={actionLoading}
                      onClick={() => setMarkLostModalOpen(true)}
                      className={styles.outlinePill}
                    >
                      Mark Lost
                    </button>
                  </div>
                )}
              </div>
            </div>
          )}

          {/* Recollection Lineage Card */}
          {sample.recollected_from_accession && (
            <div className={styles.card}>
              <h2 className={styles.cardTitle}>Specimen Lineage</h2>
              <div className="p-3 bg-amber-50 border border-amber-200 rounded-xl text-xs text-amber-900 space-y-1">
                <span className="font-semibold block">
                  Recollected Replacement:
                </span>
                <p>
                  This sample was recollected from previous accession{" "}
                  {sample.recollected_from_id ? (
                    <button
                      type="button"
                      onClick={() =>
                        navigate(`/samples/${sample.recollected_from_id}`)
                      }
                      className="font-mono font-bold underline"
                    >
                      {sample.recollected_from_accession}
                    </button>
                  ) : (
                    <span className="font-mono font-bold">
                      {sample.recollected_from_accession}
                    </span>
                  )}
                  .
                </p>
              </div>
            </div>
          )}

          {/* Quick Actions Card */}
          <div className={styles.card}>
            <div className={styles.cardHeader}>
              <h2 className={styles.cardTitle}>Sample Actions</h2>
            </div>
            <div className={styles.actionButtonGroup}>
              {canReceive && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={handleReceiveSample}
                  className={styles.primaryBlackPill}
                >
                  Receive Sample
                </button>
              )}

              {canRecollect && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => setRecollectModalOpen(true)}
                  className={styles.primaryBlackPill}
                >
                  Recollect Specimen
                </button>
              )}

              {canCreateTransfer && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => setTransferModalOpen(true)}
                  className={styles.outlinePill}
                >
                  <ArrowRightLeft className="w-4 h-4" />
                  <span>Transfer to Branch</span>
                </button>
              )}

              {canReject && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => setRejectModalOpen(true)}
                  className={styles.dangerOutlinePill}
                >
                  <Ban className="w-4 h-4" />
                  <span>Reject Sample</span>
                </button>
              )}

              {canCancelSample && (
                <button
                  type="button"
                  disabled={actionLoading}
                  onClick={() => setCancelModalOpen(true)}
                  className={styles.dangerOutlinePill}
                >
                  <span>Cancel Accession</span>
                </button>
              )}
            </div>
          </div>
        </aside>
      </div>

      {/* Floating Toast */}
      {toastMessage && (
        <aside
          role="status"
          aria-live="polite"
          className={styles.floatingToast}
        >
          <CheckCircle2 className="w-4 h-4 text-emerald-400" />
          <span>{toastMessage}</span>
          <button
            type="button"
            onClick={() => setToastMessage(null)}
            className="ms-2 text-white/70 hover:text-white"
          >
            <X className="w-3.5 h-3.5" />
          </button>
        </aside>
      )}

      {/* MODAL 1: Reject Sample Modal */}
      {rejectModalOpen && (
        <div className={styles.modalBackdrop}>
          <div
            ref={rejectPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="reject-modal-title"
            className={styles.modalPanel}
          >
            <h2 id="reject-modal-title" className={styles.modalTitle}>
              Reject Specimen
            </h2>
            <p className={styles.modalBody}>
              Document quality non-conformance. This action is irreversible and
              audited.
            </p>

            <div>
              <label
                htmlFor="reject-reason-code"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Rejection Reason Code
              </label>
              <select
                id="reject-reason-code"
                value={rejectionCode}
                onChange={(e) =>
                  setRejectionCode(e.target.value as RejectionReasonCode)
                }
                className={styles.modalInput}
              >
                <option value="">Select non-conformance reason...</option>
                {REJECTION_REASONS.map((r) => (
                  <option key={r.code} value={r.code}>
                    {r.label}
                  </option>
                ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="reject-note"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Clinical Justification{" "}
                {rejectionCode === "other" && (
                  <span className="text-red-600">*</span>
                )}
              </label>
              <textarea
                id="reject-note"
                rows={3}
                value={rejectionNote}
                onChange={(e) => setRejectionNote(e.target.value)}
                placeholder={
                  rejectionCode === "other"
                    ? "Mandatory note for 'Other'..."
                    : "Optional explanatory notes..."
                }
                className={styles.modalInput}
              />
            </div>

            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setRejectModalOpen(false)}
                className={styles.outlinePill}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={
                  !rejectionCode ||
                  (rejectionCode === "other" && !rejectionNote.trim()) ||
                  actionLoading
                }
                onClick={handleRejectSubmit}
                className={styles.primaryBlackPill}
              >
                Confirm Rejection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 2: Transfer Sample Modal */}
      {transferModalOpen && (
        <div className={styles.modalBackdrop}>
          <div
            ref={transferPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="transfer-modal-title"
            className={styles.modalPanel}
          >
            <h2 id="transfer-modal-title" className={styles.modalTitle}>
              Transfer Specimen to Branch
            </h2>
            <p className={styles.modalBody}>
              Dispatch this specimen to another branch facility.
            </p>

            <div>
              <label
                htmlFor="transfer-to-branch"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Destination Branch
              </label>
              <select
                id="transfer-to-branch"
                value={transferBranchId}
                onChange={(e) => setTransferBranchId(e.target.value)}
                className={styles.modalInput}
              >
                <option value="">Select destination branch...</option>
                {branches
                  .filter((b) => b.id !== sample.branch_id)
                  .map((b) => (
                    <option key={b.id} value={b.id}>
                      {b.name}
                    </option>
                  ))}
              </select>
            </div>

            <div>
              <label
                htmlFor="transfer-note"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Courier / Transport Notes (Optional)
              </label>
              <textarea
                id="transfer-note"
                rows={2}
                value={transferNotes}
                onChange={(e) => setTransferNotes(e.target.value)}
                placeholder="e.g. Courier rider Tariq, ice pack included"
                className={styles.modalInput}
              />
            </div>

            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setTransferModalOpen(false)}
                className={styles.outlinePill}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!transferBranchId || actionLoading}
                onClick={handleTransferSubmit}
                className={styles.primaryBlackPill}
              >
                Confirm Transfer
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 3: Cancel Sample Modal */}
      {cancelModalOpen && (
        <div className={styles.modalBackdrop}>
          <div
            ref={cancelPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="cancel-modal-title"
            className={styles.modalPanel}
          >
            <h2 id="cancel-modal-title" className={styles.modalTitle}>
              Cancel Sample Accession
            </h2>
            <p className="text-xs text-red-700 bg-red-50 p-2.5 rounded-xl border border-red-200">
              <strong>Warning:</strong> This cannot be undone. This accession
              will be permanently marked as cancelled.
            </p>

            <div>
              <label
                htmlFor="cancel-reason"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Cancellation Reason <span className="text-red-600">*</span>
              </label>
              <textarea
                id="cancel-reason"
                rows={3}
                value={cancelReason}
                onChange={(e) => setCancelReason(e.target.value)}
                placeholder="Mandatory cancellation reason..."
                className={styles.modalInput}
              />
            </div>

            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setCancelModalOpen(false)}
                className={styles.outlinePill}
              >
                Keep Sample
              </button>
              <button
                type="button"
                disabled={!cancelReason.trim() || actionLoading}
                onClick={handleCancelSampleSubmit}
                className={styles.primaryBlackPill}
              >
                Confirm Cancel
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 4: Recollect Confirmation Dialog */}
      {recollectModalOpen && (
        <div className={styles.modalBackdrop}>
          <div
            ref={recollectPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="recollect-dialog-title"
            className={styles.modalPanel}
          >
            <h2 id="recollect-dialog-title" className={styles.modalTitle}>
              Recollect Sample Specimen
            </h2>
            <p className={styles.modalBody}>
              Creates a new accession for remaining untested items on this
              invoice without re-billing.
            </p>
            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setRecollectModalOpen(false)}
                className={styles.outlinePill}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={actionLoading}
                onClick={handleRecollectConfirm}
                className={styles.primaryBlackPill}
              >
                Confirm Recollection
              </button>
            </div>
          </div>
        </div>
      )}

      {/* MODAL 5: Mark Lost Modal */}
      {markLostModalOpen && (
        <div className={styles.modalBackdrop}>
          <div
            ref={markLostPanelRef}
            role="dialog"
            aria-modal="true"
            aria-labelledby="marklost-modal-title"
            className={styles.modalPanel}
          >
            <h2 id="marklost-modal-title" className={styles.modalTitle}>
              Mark Transferred Specimen as Lost
            </h2>
            <p className={styles.modalBody}>
              Document loss in transit. A clinical non-conformance incident will
              be registered.
            </p>

            <div>
              <label
                htmlFor="lost-note"
                className="block text-xs font-bold text-slate-700 mb-1"
              >
                Mandatory Incident Note <span className="text-red-600">*</span>
              </label>
              <textarea
                id="lost-note"
                rows={3}
                value={markLostNote}
                onChange={(e) => setMarkLostNote(e.target.value)}
                placeholder="Explain the circumstance of loss..."
                className={styles.modalInput}
              />
            </div>

            <div className={styles.modalActions}>
              <button
                type="button"
                onClick={() => setMarkLostModalOpen(false)}
                className={styles.outlinePill}
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={!markLostNote.trim() || actionLoading}
                onClick={handleMarkLostAction}
                className={styles.primaryBlackPill}
              >
                Confirm Lost
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}

export default SampleDetailScreen;
