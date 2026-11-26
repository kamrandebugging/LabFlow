import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Lock, RotateCcw } from "lucide-react";
import { billingService } from "./billingService";
import { useAuthStore } from "../auth/authStore";
import { settingsService } from "../settings/settingsService";
import type { Branch } from "../settings/types";
import { formatMoney } from "../../lib/format";
import { messageForError } from "../../lib/errors";
import type { DayCloseResponse, DayCloseTotals } from "./types";
import styles from "./DayCloseScreen.module.css";

const METHOD_ORDER = [
  "cash",
  "card",
  "bank_transfer",
  "easypaisa",
  "jazzcash",
  "other",
] as const;

function todayIso(): string {
  const now = new Date();
  const local = new Date(now.getTime() - now.getTimezoneOffset() * 60_000);
  return local.toISOString().slice(0, 10);
}

export function DayCloseScreen(): JSX.Element {
  const { t } = useTranslation();
  const role = useAuthStore((state) => state.user?.role);
  const isOwner = role === "owner";

  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchId, setBranchId] = useState("");
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<DayCloseResponse | null>(null);
  const [countedByMethod, setCountedByMethod] = useState<
    Record<string, string>
  >({});
  const [note, setNote] = useState("");
  const [approverEmail, setApproverEmail] = useState("");
  const [approverPassword, setApproverPassword] = useState("");
  const [approverTotp, setApproverTotp] = useState("");
  const [reopenReason, setReopenReason] = useState("");
  const [isLoading, setIsLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    settingsService
      .getBranches()
      .then((rows) => {
        if (!active) return;
        setBranches(rows);
        setBranchId((current) => current || rows[0]?.id || "");
      })
      .catch((err: unknown) => {
        if (active) setError(messageForError(err, t));
      });
    return () => {
      active = false;
    };
  }, [t]);

  const load = useCallback(
    async (signal?: AbortSignal) => {
      if (!branchId || !date) return;
      setIsLoading(true);
      setError(null);
      try {
        const response = await billingService.getDayClose(
          branchId,
          date,
          signal,
        );
        setData(response);
      } catch (err: unknown) {
        setData(null);
        setError(messageForError(err, t));
      } finally {
        setIsLoading(false);
      }
    },
    [branchId, date, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const totals: DayCloseTotals | null = data?.totals ?? null;
  const methodTotals =
    data?.close?.method_totals ?? totals?.method_totals ?? {};
  const expectedCash = Number(
    data?.close?.expected_cash ?? totals?.expected_cash ?? 0,
  );
  const countedCashRaw = countedByMethod.cash ?? "";
  const counted = countedCashRaw.trim() === "" ? null : Number(countedCashRaw);
  const difference = counted === null ? null : counted - expectedCash;
  const closed = Boolean(data?.closed);
  const isTodayOrFuture = date >= todayIso();

  const methodRows = METHOD_ORDER.filter((method) =>
    Boolean(methodTotals[method]),
  );

  const activeMethods = methodRows.filter((method) => {
    if (method === "cash") return true;
    const bucket = methodTotals[method];
    return (
      Number(bucket?.in ?? 0) !== 0 ||
      Number(bucket?.out ?? 0) !== 0 ||
      Number(bucket?.net ?? 0) !== 0
    );
  });

  const allActiveEntered = activeMethods.every((m) => {
    const raw = (countedByMethod[m] ?? "").trim();
    return raw !== "" && Number.isFinite(Number(raw)) && Number(raw) >= 0;
  });

  const hasAnyDiscrepancy = activeMethods.some((m) => {
    const raw = (countedByMethod[m] ?? "").trim();
    if (raw === "") return false;
    const val = Number(raw);
    const exp = Number(methodTotals[m]?.net ?? 0);
    return Math.abs(val - exp) >= 0.005;
  });

  const noteRequired = hasAnyDiscrepancy;
  const approverRequired = hasAnyDiscrepancy;
  const reopens = data?.reopens ?? [];

  const closeDay = async () => {
    if (!data || !allActiveEntered || isTodayOrFuture) return;
    setBusy(true);
    setError(null);
    try {
      const countedMethodsPayload: Record<string, string> = {};
      for (const m of activeMethods) {
        countedMethodsPayload[m] = (countedByMethod[m] ?? "0").trim();
      }
      const response = await billingService.closeDay({
        branch_id: branchId,
        date,
        counted_cash: countedMethodsPayload.cash,
        counted_methods: countedMethodsPayload,
        difference_note: note.trim() || undefined,
        approver_email: approverRequired
          ? approverEmail.trim() || undefined
          : undefined,
        approver_password: approverRequired
          ? approverPassword || undefined
          : undefined,
        approver_totp: approverRequired
          ? approverTotp.trim() || undefined
          : undefined,
      });
      setData(response);
      setCountedByMethod({});
      setNote("");
      setApproverEmail("");
      setApproverPassword("");
      setApproverTotp("");
    } catch (err: unknown) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  };

  const handleReopen = async () => {
    if (!data || !reopenReason.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const response = await billingService.reopenDay({
        branch_id: branchId,
        date,
        reason: reopenReason.trim(),
      });
      setData(response);
      setReopenReason("");
    } catch (err: unknown) {
      setError(messageForError(err, t));
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className={styles.page}>
      <div className={styles.header}>
        <h1 className={styles.title}>{t("billing:day_close.title")}</h1>
        <p className={styles.subtitle}>{t("billing:day_close.subtitle")}</p>
      </div>

      <div className={styles.controls}>
        <label className={styles.field}>
          <span className={styles.label}>{t("billing:day_close.date")}</span>
          <input
            type="date"
            className={styles.input}
            value={date}
            max={todayIso()}
            onChange={(event) => setDate(event.target.value)}
          />
        </label>
        <label className={styles.field}>
          <span className={styles.label}>{t("billing:day_close.branch")}</span>
          <select
            className={styles.input}
            value={branchId}
            onChange={(event) => setBranchId(event.target.value)}
          >
            {branches.map((branch) => (
              <option key={branch.id} value={branch.id}>
                {branch.name}
              </option>
            ))}
          </select>
        </label>
        {data?.active_business_date ? (
          <span className={styles.lockedBadge}>
            {t("billing:day_close.active_date_label")}:{" "}
            {data.active_business_date}
          </span>
        ) : null}
        {closed ? (
          <span className={styles.lockedBadge}>
            <Lock size={14} aria-hidden="true" />
            {t("billing:day_close.closed_badge")}
          </span>
        ) : null}
        {data?.is_corrected ? (
          <span className={styles.lockedBadge}>
            <RotateCcw size={14} aria-hidden="true" />
            {t("billing:day_close.corrected_badge")}
          </span>
        ) : null}
      </div>

      {error ? (
        <div role="alert" className={styles.alert}>
          <AlertCircle size={16} aria-hidden="true" />
          <span>{error}</span>
        </div>
      ) : null}

      {isLoading && !data ? (
        <p className={styles.muted}>{t("billing:day_close.loading")}</p>
      ) : null}

      {data ? (
        <>
          <section className={styles.card}>
            <div className={styles.cardHead}>
              <h2 className={styles.cardTitle}>
                {t("billing:day_close.methods_title")}
              </h2>
            </div>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th>{t("billing:day_close.method")}</th>
                  <th className={styles.num}>{t("billing:day_close.in")}</th>
                  <th className={styles.num}>{t("billing:day_close.out")}</th>
                  <th className={styles.num}>{t("billing:day_close.net")}</th>
                </tr>
              </thead>
              <tbody>
                {methodRows.length === 0 ? (
                  <tr>
                    <td colSpan={4} className={styles.muted}>
                      {t("billing:day_close.no_payments")}
                    </td>
                  </tr>
                ) : (
                  methodRows.map((method) => (
                    <tr key={method}>
                      <td>{t(`billing:detail.method.${method}`)}</td>
                      <td className={styles.num} dir="ltr">
                        {formatMoney(methodTotals[method]?.in ?? "0.00", "en")}
                      </td>
                      <td className={styles.num} dir="ltr">
                        {formatMoney(methodTotals[method]?.out ?? "0.00", "en")}
                      </td>
                      <td className={styles.num} dir="ltr">
                        {formatMoney(methodTotals[method]?.net ?? "0.00", "en")}
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </section>

          <section className={styles.card}>
            <div className={styles.summary}>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>
                  {t("billing:day_close.total_invoices")}
                </span>
                <span className={styles.summaryValue}>
                  {data.close?.total_invoices ?? totals?.total_invoices ?? 0}
                </span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>
                  {t("billing:day_close.total_discount")}
                </span>
                <span className={styles.summaryValue} dir="ltr">
                  {formatMoney(
                    data.close?.total_discount ??
                      totals?.total_discount ??
                      "0.00",
                    "en",
                  )}
                </span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>
                  {t("billing:day_close.total_credit_notes")}
                </span>
                <span className={styles.summaryValue} dir="ltr">
                  {formatMoney(
                    data.close?.total_credit_notes ??
                      totals?.total_credit_notes ??
                      "0.00",
                    "en",
                  )}
                </span>
              </div>
              <div className={styles.summaryItem}>
                <span className={styles.summaryLabel}>
                  {t("billing:day_close.net_total")}
                </span>
                <span className={styles.summaryValue} dir="ltr">
                  {formatMoney(totals?.net_total ?? "0.00", "en")}
                </span>
              </div>
            </div>
          </section>

          {closed && data.close ? (
            <section className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:day_close.closed_title")}
                </h2>
              </div>
              <div className={styles.summary}>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>
                    {t("billing:day_close.expected_cash")}
                  </span>
                  <span className={styles.summaryValue} dir="ltr">
                    {formatMoney(data.close.expected_cash, "en")}
                  </span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>
                    {t("billing:day_close.counted_cash")}
                  </span>
                  <span className={styles.summaryValue} dir="ltr">
                    {formatMoney(data.close.counted_cash, "en")}
                  </span>
                </div>
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>
                    {t("billing:day_close.difference")}
                  </span>
                  <span className={styles.summaryValue} dir="ltr">
                    {formatMoney(data.close.difference, "en")}
                  </span>
                </div>
              </div>
              {data.close.difference_note ? (
                <p className={styles.muted}>
                  {t("billing:day_close.note")}: {data.close.difference_note}
                </p>
              ) : null}
              {data.close.approved_by_name ? (
                <p className={styles.muted}>
                  {t("billing:day_close.approved_by", {
                    name: data.close.approved_by_name,
                  })}
                </p>
              ) : null}
              <p className={styles.muted}>
                {t("billing:day_close.closed_by", {
                  name:
                    data.close.closed_by_name ||
                    t("billing:day_close.unknown_user"),
                  time: new Date(data.close.closed_at).toLocaleString(),
                })}
              </p>

              {isOwner ? (
                <div style={{ marginTop: 16 }}>
                  <h3 className={styles.cardTitle}>
                    {t("billing:day_close.reopen_title")}
                  </h3>
                  <div className={styles.controls} style={{ marginTop: 8 }}>
                    <label className={styles.field}>
                      <span className={styles.label}>
                        {t("billing:day_close.reopen_reason")}
                      </span>
                      <input
                        type="text"
                        className={styles.input}
                        value={reopenReason}
                        onChange={(event) =>
                          setReopenReason(event.target.value)
                        }
                        placeholder={t("billing:day_close.reopen_reason_hint")}
                      />
                    </label>
                    <button
                      type="button"
                      className={styles.primaryButton}
                      disabled={busy || !reopenReason.trim()}
                      onClick={() => void handleReopen()}
                    >
                      {busy
                        ? t("billing:day_close.reopening")
                        : t("billing:day_close.reopen_button")}
                    </button>
                  </div>
                </div>
              ) : null}
            </section>
          ) : (
            <section className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:day_close.reconcile_title")}
                </h2>
              </div>
              {isTodayOrFuture ? (
                <p className={styles.muted}>
                  {t("billing:day_close.today_blocked_hint")}
                </p>
              ) : null}
              <div className={styles.controls}>
                {activeMethods.map((method) => (
                  <label key={method} className={styles.field}>
                    <span className={styles.label}>
                      {method === "cash"
                        ? t("billing:day_close.counted_cash")
                        : t("billing:day_close.counted_for_method", {
                            method: t(`billing:detail.method.${method}`),
                          })}
                    </span>
                    <input
                      type="number"
                      min="0"
                      step="0.01"
                      inputMode="decimal"
                      className={styles.input}
                      value={countedByMethod[method] ?? ""}
                      onChange={(event) =>
                        setCountedByMethod((prev) => ({
                          ...prev,
                          [method]: event.target.value,
                        }))
                      }
                      placeholder={
                        method === "cash"
                          ? t("billing:day_close.counted_placeholder")
                          : formatMoney(
                              methodTotals[method]?.net ?? "0.00",
                              "en",
                            )
                      }
                    />
                  </label>
                ))}
                <div className={styles.summaryItem}>
                  <span className={styles.summaryLabel}>
                    {t("billing:day_close.expected_cash")}
                  </span>
                  <span className={styles.summaryValue} dir="ltr">
                    {formatMoney(expectedCash.toFixed(2), "en")}
                  </span>
                </div>
              </div>

              <div
                className={`${styles.difference} ${
                  noteRequired ? styles.differenceBad : ""
                }`}
              >
                <span>{t("billing:day_close.difference")}</span>
                <span dir="ltr">
                  {difference === null
                    ? "—"
                    : formatMoney(difference.toFixed(2), "en")}
                </span>
              </div>

              <label className={styles.field} style={{ marginTop: 12 }}>
                <span className={styles.label}>
                  {t("billing:day_close.note")}
                  {noteRequired ? " *" : ""}
                </span>
                <input
                  type="text"
                  className={styles.input}
                  value={note}
                  onChange={(event) => setNote(event.target.value)}
                  placeholder={t("billing:day_close.note_hint")}
                />
              </label>

              {approverRequired ? (
                <div style={{ marginTop: 12 }}>
                  <p className={styles.muted}>
                    {t("billing:day_close.approver_hint")}
                  </p>
                  <div className={styles.controls} style={{ marginTop: 8 }}>
                    <label className={styles.field}>
                      <span className={styles.label}>
                        {t("billing:day_close.approver_email")} *
                      </span>
                      <input
                        type="email"
                        className={styles.input}
                        value={approverEmail}
                        onChange={(event) =>
                          setApproverEmail(event.target.value)
                        }
                      />
                    </label>
                    <label className={styles.field}>
                      <span className={styles.label}>
                        {t("billing:day_close.approver_password")} *
                      </span>
                      <input
                        type="password"
                        className={styles.input}
                        value={approverPassword}
                        onChange={(event) =>
                          setApproverPassword(event.target.value)
                        }
                      />
                    </label>
                    <label className={styles.field}>
                      <span className={styles.label}>
                        {t("billing:day_close.approver_totp")}
                      </span>
                      <input
                        type="text"
                        className={styles.input}
                        value={approverTotp}
                        onChange={(event) =>
                          setApproverTotp(event.target.value)
                        }
                      />
                    </label>
                  </div>
                </div>
              ) : null}

              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={
                    busy ||
                    isTodayOrFuture ||
                    !allActiveEntered ||
                    (noteRequired && !note.trim()) ||
                    (approverRequired &&
                      (!approverEmail.trim() || !approverPassword))
                  }
                  onClick={() => void closeDay()}
                >
                  {busy
                    ? t("billing:day_close.closing")
                    : t("billing:day_close.close_button")}
                </button>
                <span className={styles.muted}>
                  {t("billing:day_close.lock_hint")}
                </span>
              </div>
            </section>
          )}

          {reopens.length > 0 ? (
            <section className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:day_close.reopens_title")}
                </h2>
              </div>
              {reopens.map((entry) => (
                <p key={entry.id} className={styles.muted}>
                  {t("billing:day_close.reopened_by", {
                    name:
                      entry.reopened_by_name ||
                      t("billing:day_close.unknown_user"),
                    time: new Date(entry.reopened_at).toLocaleString(),
                  })}{" "}
                  — {entry.reason}
                </p>
              ))}
            </section>
          ) : null}
        </>
      ) : null}
    </main>
  );
}

export default DayCloseScreen;
