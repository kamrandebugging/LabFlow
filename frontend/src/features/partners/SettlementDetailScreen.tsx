import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useParams } from "react-router-dom";
import {
  AlertCircle,
  AlertTriangle,
  ArrowDownToLine,
  ArrowLeft,
  CheckCircle2,
  ChevronRight,
  ExternalLink,
  Send,
  Wallet,
  XCircle,
} from "lucide-react";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { formatMoney, statusLabel } from "../../lib/format";
import { PartnerApiError, partnersService } from "./partnersService";
import type { ReferralPartner, Settlement, SettlementStatus } from "./types";

export const SettlementDetailScreen: React.FC = () => {
  const { t, i18n } = useTranslation(["settlements", "common"]);
  const lang = i18n.resolvedLanguage === "ur" ? "ur" : "en";
  const { id } = useParams<{ id: string }>();
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "owner";
  const isManager = user?.role === "manager";
  const isAuthorized = isOwner || isManager;

  const [settlement, setSettlement] = useState<Settlement | null>(null);
  const [partner, setPartner] = useState<ReferralPartner | null>(null);
  const [isLoading, setIsLoading] = useState<boolean>(true);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [actionSuccess, setActionSuccess] = useState<string | null>(null);
  const [isSubmitting, setIsSubmitting] = useState<boolean>(false);

  // Mark paid modal state
  const [isMarkPaidModalOpen, setIsMarkPaidModalOpen] =
    useState<boolean>(false);
  const [paymentReference, setPaymentReference] = useState<string>("");

  /** Server codes become translated text; a raw `detail` is never rendered. */
  const translateError = useCallback(
    (err: unknown): string =>
      messageForError(err, (key) =>
        key.includes(":") ? t(key) : t(`common:${key}`),
      ),
    [t],
  );

  const fetchData = useCallback(async (): Promise<void> => {
    if (!id || !isAuthorized) return;
    setIsLoading(true);
    setErrorMsg(null);

    try {
      const settData = await partnersService.getSettlement(id);
      setSettlement(settData);

      if (settData.referral_partner_id) {
        try {
          const partnerData = await partnersService.getPartner(
            settData.referral_partner_id,
          );
          setPartner(partnerData);
        } catch {
          // Non-critical if partner lookup fails
        }
      }
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setErrorMsg(translateError(err));
      } else if (err instanceof Error) {
        setErrorMsg(t("settlements:errors.load_detail_failed"));
      } else {
        setErrorMsg(t("settlements:errors.load_detail_failed"));
      }
    } finally {
      setIsLoading(false);
    }
  }, [id, isAuthorized, translateError, t]);

  useEffect(() => {
    fetchData();
  }, [fetchData]);

  // Handle mutations with If-Match version conflict handling
  const executeMutation = async (
    mutationFn: (version: string) => Promise<Settlement>,
    successMessage: string,
  ): Promise<void> => {
    if (!settlement || !isOwner) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    setActionSuccess(null);

    try {
      const updated = await mutationFn(settlement.version);
      setSettlement(updated);
      setActionSuccess(successMessage);
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        if (err.code === "version_conflict") {
          await fetchData();
          setErrorMsg(t("settlements:errors.version_conflict"));
        } else {
          setErrorMsg(translateError(err));
        }
      } else if (err instanceof Error) {
        setErrorMsg(t("settlements:errors.action_failed"));
      } else {
        setErrorMsg(t("settlements:errors.action_failed"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  const handleApprove = () => {
    executeMutation(
      (version) => partnersService.approveSettlement(id!, version),
      t("settlements:toast.approved"),
    );
  };

  const handleCancel = () => {
    if (!confirm(t("settlements:confirm.cancel"))) {
      return;
    }
    executeMutation(
      (version) => partnersService.cancelSettlement(id!, version),
      t("settlements:toast.cancelled"),
    );
  };

  const handleMarkPaidSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!settlement || !isOwner) return;
    setIsMarkPaidModalOpen(false);

    executeMutation(
      (version) =>
        partnersService.markPaidSettlement(
          id!,
          version,
          paymentReference.trim() || undefined,
        ),
      paymentReference
        ? t("settlements:toast.marked_paid_ref", {
            reference: paymentReference,
          })
        : t("settlements:toast.marked_paid"),
    );
  };

  const handleSendStatement = async () => {
    if (!settlement || !isOwner) return;
    setIsSubmitting(true);
    setErrorMsg(null);
    setActionSuccess(null);

    try {
      await partnersService.sendSettlement(id!);
      setActionSuccess(t("settlements:toast.statement_queued"));
      await fetchData();
    } catch (err: unknown) {
      if (err instanceof PartnerApiError) {
        setErrorMsg(translateError(err));
      } else if (err instanceof Error) {
        setErrorMsg(t("settlements:errors.send_statement_failed"));
      } else {
        setErrorMsg(t("settlements:errors.send_statement_failed"));
      }
    } finally {
      setIsSubmitting(false);
    }
  };

  if (!isAuthorized) {
    return (
      <div className="min-h-screen bg-slate-50 flex items-center justify-center p-6 text-xs text-slate-600">
        <div className="bg-white border border-slate-200 rounded-xl p-8 max-w-md text-center shadow-xs">
          <AlertTriangle className="w-8 h-8 text-amber-600 mx-auto mb-3" />
          <h2 className="text-sm font-bold text-slate-900 mb-1">
            {t("settlements:access.title")}
          </h2>
          <p className="text-slate-600 mb-4">
            {t("settlements:access.body_detail")}
          </p>
          <Link
            to="/settlements"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-teal-600 text-white rounded-lg font-semibold hover:bg-teal-700 transition-colors"
          >
            <span>{t("settlements:access.back_to_settlements")}</span>
          </Link>
        </div>
      </div>
    );
  }

  const statusStyles: Record<SettlementStatus, { badge: string; dot: string }> =
    {
      DRAFT: {
        badge: "bg-amber-50 text-amber-700 border-amber-200",
        dot: "bg-amber-600",
      },
      APPROVED: {
        badge: "bg-blue-50 text-blue-700 border-blue-200",
        dot: "bg-blue-600",
      },
      SENT: {
        badge: "bg-purple-50 text-purple-700 border-purple-200",
        dot: "bg-purple-600",
      },
      PAID: {
        badge: "bg-emerald-50 text-emerald-700 border-emerald-200",
        dot: "bg-emerald-600",
      },
      CANCELLED: {
        badge: "bg-slate-100 text-slate-600 border-slate-200",
        dot: "bg-slate-400",
      },
    };

  return (
    <div className="min-h-screen bg-slate-50 text-slate-900 flex flex-col selection:bg-teal-100 selection:text-teal-900">
      <main className="flex-1 p-6 md:p-8 max-w-6xl mx-auto w-full space-y-6">
        {/* BREADCRUMBS */}
        <div className="flex items-center justify-between text-xs text-slate-500">
          <div className="flex items-center gap-x-2">
            <Link
              to="/settlements"
              className="hover:text-slate-800 transition-colors flex items-center gap-1 font-medium"
            >
              <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
              <span>{t("common:nav.settlements")}</span>
            </Link>
            <ChevronRight className="w-3.5 h-3.5 text-slate-300 rtl:rotate-180" />
            <span className="font-mono text-slate-700">
              <bdi dir="ltr">
                {settlement ? settlement.id.slice(0, 8) : "..."}
              </bdi>
            </span>
          </div>
          <div className="text-slate-400 text-[11px] font-mono">
            {settlement ? (
              <>
                {t("settlements:detail.version")}{" "}
                <bdi dir="ltr">{settlement.version}</bdi>
              </>
            ) : (
              ""
            )}
          </div>
        </div>

        {/* FEEDBACK BANNERS */}
        {errorMsg && (
          <div className="p-4 bg-red-50 border border-red-200 text-red-800 rounded-xl text-xs flex items-center gap-3">
            <AlertCircle className="w-4 h-4 text-red-600 shrink-0" />
            <span>{errorMsg}</span>
          </div>
        )}

        {actionSuccess && (
          <div className="p-4 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-xl text-xs flex items-center gap-3">
            <CheckCircle2 className="w-4 h-4 text-emerald-600 shrink-0" />
            <span>{actionSuccess}</span>
          </div>
        )}

        {isLoading ? (
          <div className="p-12 text-center text-xs text-slate-500 bg-white rounded-xl border border-slate-200">
            {t("settlements:states.loading_detail")}
          </div>
        ) : settlement ? (
          <>
            {/* HEADER METADATA CARD */}
            <div className="bg-white rounded-xl border border-slate-200 p-6 shadow-xs">
              <div className="flex flex-col md:flex-row md:items-start md:justify-between gap-4">
                <div>
                  <div className="flex flex-wrap items-center gap-3 mb-2">
                    <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                      {t("settlements:detail.heading")}
                      {" — "}
                      <bdi dir="ltr">
                        {partner?.name || settlement.referral_partner_id}
                      </bdi>{" "}
                      — <bdi dir="ltr">{settlement.period}</bdi>
                    </h1>
                    <span className="font-mono px-2.5 py-0.5 rounded bg-slate-100 border border-slate-300 text-slate-700 text-xs font-semibold">
                      <bdi dir="ltr">{settlement.id.slice(0, 13)}</bdi>
                    </span>
                    <span
                      className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-xs font-semibold border ${
                        statusStyles[settlement.status]?.badge ||
                        statusStyles.DRAFT.badge
                      }`}
                    >
                      <span
                        className={`w-1.5 h-1.5 rounded-full me-1.5 ${
                          statusStyles[settlement.status]?.dot ||
                          statusStyles.DRAFT.dot
                        }`}
                      ></span>
                      {/* Raw status code: shared with the ledger badge. */}
                      <bdi>
                        {statusLabel(
                          "settlement",
                          settlement.status.toLowerCase(),
                          (key) => t(`common:${key}`),
                        )}
                      </bdi>
                    </span>
                  </div>

                  {/* Metadata grid */}
                  <div className="mt-3 grid grid-cols-1 md:grid-cols-2 gap-y-1.5 gap-x-6 text-slate-600 text-xs">
                    <div>
                      <span className="font-semibold text-slate-700">
                        {t("settlements:detail.period")}
                      </span>{" "}
                      <bdi className="font-mono" dir="ltr">
                        {settlement.period}
                      </bdi>
                    </div>
                    <div>
                      <span className="font-semibold text-slate-700">
                        {t("settlements:detail.partner")}
                      </span>{" "}
                      <Link
                        to={`/partners/${settlement.referral_partner_id}`}
                        className="text-teal-700 hover:text-teal-900 font-medium"
                      >
                        <bdi dir="ltr">
                          {partner?.name || settlement.referral_partner_id}
                        </bdi>
                      </Link>
                    </div>
                    {partner?.phone && (
                      <div>
                        <span className="font-semibold text-slate-700">
                          {t("settlements:detail.contact")}
                        </span>{" "}
                        <bdi className="font-mono" dir="ltr">
                          {partner.phone}
                        </bdi>
                      </div>
                    )}
                    {partner?.email && (
                      <div>
                        <span className="font-semibold text-slate-700">
                          {t("common:labels.email")}:
                        </span>{" "}
                        <bdi dir="ltr">{partner.email}</bdi>
                      </div>
                    )}
                  </div>
                </div>

                {/* PDF Download */}
                <div className="shrink-0 pt-1">
                  <a
                    href={partnersService.getStatementPdfUrl(settlement.id)}
                    download
                    className="inline-flex items-center gap-1.5 px-3.5 py-2 rounded-lg border border-slate-300 bg-white hover:bg-slate-50 text-slate-800 text-xs font-semibold shadow-xs transition-colors"
                  >
                    <ArrowDownToLine className="w-4 h-4 text-slate-600" />
                    <span>{t("settlements:actions.download_statement")}</span>
                  </a>
                </div>
              </div>
            </div>

            {/* FINANCIAL SUMMARY KPIS */}
            <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
                <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
                  {t("settlements:kpi.total_amount")}
                </span>
                <div className="mt-2 text-2xl font-bold font-mono text-slate-900">
                  {formatMoney(settlement.total, lang)}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {t("settlements:kpi.total_hint")}
                </div>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
                <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
                  {t("settlements:kpi.line_items")}
                </span>
                <div className="mt-2 text-2xl font-bold font-mono text-slate-900">
                  {settlement.lines ? settlement.lines.length : 0}
                </div>
                <div className="mt-1 text-xs text-slate-500">
                  {t("settlements:kpi.line_items_hint")}
                </div>
              </div>

              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs">
                <span className="text-xs uppercase tracking-wider text-slate-500 font-semibold">
                  {t("settlements:kpi.sign_off")}
                </span>
                <div className="mt-2 text-2xl font-bold text-slate-900">
                  {/* Raw status code, matching the header badge. */}
                  <bdi>
                    {statusLabel(
                      "settlement",
                      settlement.status.toLowerCase(),
                      (key) => t(`common:${key}`),
                    )}
                  </bdi>
                </div>
                <div className="mt-1 text-xs text-slate-500 font-mono text-[11px]">
                  {settlement.approved_at ? (
                    <>
                      {t("settlements:kpi.approved_on")}{" "}
                      <bdi dir="ltr">{settlement.approved_at.slice(0, 10)}</bdi>
                    </>
                  ) : (
                    t("settlements:kpi.awaiting_owner")
                  )}
                </div>
              </div>
            </div>

            {/* OWNER ACTION CONTROLS */}
            {isOwner && settlement.status !== "CANCELLED" && (
              <div className="bg-white rounded-xl border border-slate-200 p-5 shadow-xs space-y-3">
                <h3 className="text-xs font-bold uppercase tracking-wider text-slate-600">
                  {t("settlements:workflow.title")}
                </h3>
                <div className="flex flex-wrap items-center gap-3">
                  {/* Approve Action */}
                  {settlement.status === "DRAFT" && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={handleApprove}
                      className="px-4 py-2 bg-teal-600 hover:bg-teal-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                    >
                      {isSubmitting
                        ? t("settlements:actions.approving")
                        : t("settlements:actions.approve")}
                    </button>
                  )}

                  {/* Send Action */}
                  {(settlement.status === "APPROVED" ||
                    settlement.status === "SENT") && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={handleSendStatement}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-purple-600 hover:bg-purple-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                    >
                      <Send className="w-3.5 h-3.5" />
                      <span>
                        {isSubmitting
                          ? t("settlements:actions.sending")
                          : t("settlements:actions.send_statement")}
                      </span>
                    </button>
                  )}

                  {/* Mark Paid Action */}
                  {(settlement.status === "APPROVED" ||
                    settlement.status === "SENT") && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={() => {
                        setPaymentReference("");
                        setIsMarkPaidModalOpen(true);
                      }}
                      className="inline-flex items-center gap-1.5 px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                    >
                      <Wallet className="w-3.5 h-3.5" />
                      <span>{t("settlements:actions.mark_paid")}</span>
                    </button>
                  )}

                  {/* Cancel Action */}
                  {settlement.status !== "PAID" && (
                    <button
                      type="button"
                      disabled={isSubmitting}
                      onClick={handleCancel}
                      className="inline-flex items-center gap-1.5 px-3.5 py-2 border border-red-200 text-red-700 hover:bg-red-50 text-xs font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                    >
                      <XCircle className="w-3.5 h-3.5" />
                      <span>{t("settlements:actions.cancel_settlement")}</span>
                    </button>
                  )}
                </div>
              </div>
            )}

            {/* LINE ITEMS TABLE */}
            <div className="bg-white rounded-xl border border-slate-200 shadow-xs overflow-hidden">
              <div className="p-4 border-b border-slate-200 flex items-center justify-between">
                <div>
                  <h2 className="text-sm font-bold text-slate-900">
                    {t("settlements:lines.title")}
                  </h2>
                  <p className="text-xs text-slate-500 mt-0.5">
                    {t("settlements:lines.subtitle")}
                  </p>
                </div>
                <Link
                  to={`/partners/ledger?partner_id=${settlement.referral_partner_id}`}
                  className="text-xs font-medium text-teal-700 hover:text-teal-800 flex items-center gap-1"
                >
                  <span>{t("settlements:lines.open_ledger")}</span>
                  <ExternalLink className="w-3.5 h-3.5" />
                </Link>
              </div>

              {!settlement.lines || settlement.lines.length === 0 ? (
                <div className="p-8 text-center text-xs text-slate-500">
                  {t("settlements:lines.empty")}
                </div>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-start border-collapse text-xs">
                    <thead>
                      <tr className="bg-slate-50/80 border-b border-slate-200 text-[11px] font-semibold text-slate-600 uppercase tracking-wider">
                        <th className="py-3 px-4 w-44 font-mono">
                          {t("settlements:lines.id")}
                        </th>
                        <th className="py-3 px-4 w-48 font-mono">
                          {t("settlements:lines.ledger_entry")}
                        </th>
                        <th className="py-3 px-4 w-32 font-mono">
                          {t("settlements:lines.entry_period")}
                        </th>
                        <th className="py-3 px-4 text-end font-mono w-40">
                          {t("common:labels.amount")}
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100 text-slate-700">
                      {settlement.lines.map((line) => (
                        <tr
                          key={line.id}
                          className="hover:bg-slate-50/70 transition-colors"
                          data-testid={`line-row-${line.id}`}
                        >
                          <td className="py-3.5 px-4 font-mono text-slate-900">
                            <bdi dir="ltr">{line.id.slice(0, 13)}...</bdi>
                          </td>
                          <td className="py-3.5 px-4 font-mono text-teal-700">
                            <Link
                              to={`/partners/ledger?partner_id=${settlement.referral_partner_id}`}
                              className="hover:underline"
                            >
                              <bdi dir="ltr">
                                {line.share_ledger_entry_id.slice(0, 13)}...
                              </bdi>
                            </Link>
                          </td>
                          <td className="py-3.5 px-4 font-mono text-slate-800">
                            <bdi dir="ltr">{line.entry_period}</bdi>
                          </td>
                          <td className="py-3.5 px-4 text-end font-mono font-semibold text-slate-900">
                            {formatMoney(line.amount, lang)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                    <tfoot>
                      <tr className="bg-slate-50/90 border-t-2 border-slate-300 font-semibold text-slate-900">
                        <td className="py-3.5 px-4" colSpan={3}>
                          {t("settlements:lines.total", {
                            items: settlement.lines.length,
                          })}
                        </td>
                        <td className="py-3.5 px-4 text-end font-mono text-sm font-bold text-slate-900">
                          {formatMoney(settlement.total, lang)}
                        </td>
                      </tr>
                    </tfoot>
                  </table>
                </div>
              )}
            </div>
          </>
        ) : null}
      </main>

      {/* MARK PAID MODAL */}
      {isMarkPaidModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 w-full max-w-md overflow-hidden">
            <div className="p-5 border-b border-slate-200 flex items-center justify-between">
              <h3 className="text-base font-bold text-slate-900">
                {t("settlements:modal.title")}
              </h3>
              <button
                type="button"
                onClick={() => setIsMarkPaidModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-lg p-1"
                aria-label={t("common:actions.close")}
              >
                ✕
              </button>
            </div>

            <form
              onSubmit={handleMarkPaidSubmit}
              className="p-5 space-y-4 text-xs"
            >
              <p className="text-slate-600">
                {t("settlements:modal.body_prefix")}{" "}
                <strong className="font-mono text-slate-900" dir="ltr">
                  {formatMoney(settlement?.total, lang)}
                </strong>
                {t("settlements:modal.body_suffix")}
              </p>

              <div>
                <label className="block font-semibold text-slate-700 mb-1">
                  {t("settlements:modal.payment_reference")}
                </label>
                <input
                  type="text"
                  placeholder={t(
                    "settlements:modal.payment_reference_placeholder",
                  )}
                  value={paymentReference}
                  onChange={(e) => setPaymentReference(e.target.value)}
                  className="w-full bg-slate-50 border border-slate-200 rounded-lg px-3 py-2 text-slate-900 focus:bg-white focus:ring-1 focus:ring-teal-600 focus:border-teal-600"
                />
              </div>

              <div className="pt-2 flex items-center justify-end gap-2.5">
                <button
                  type="button"
                  onClick={() => setIsMarkPaidModalOpen(false)}
                  className="px-4 py-2 border border-slate-200 text-slate-700 rounded-lg hover:bg-slate-50 transition-colors"
                >
                  {t("common:actions.cancel")}
                </button>
                <button
                  type="submit"
                  disabled={isSubmitting}
                  className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white font-semibold rounded-lg shadow-xs transition-colors disabled:opacity-50"
                >
                  {isSubmitting
                    ? t("settlements:actions.confirming")
                    : t("settlements:actions.confirm_payment")}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
};
