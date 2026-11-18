import { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { AlertCircle, Lock } from "lucide-react";
import { billingService } from "./billingService";
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
  const [branches, setBranches] = useState<Branch[]>([]);
  const [branchId, setBranchId] = useState("");
  const [date, setDate] = useState(todayIso());
  const [data, setData] = useState<DayCloseResponse | null>(null);
  const [countedCash, setCountedCash] = useState("");
  const [note, setNote] = useState("");
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
  const counted = countedCash.trim() === "" ? null : Number(countedCash);
  const difference = counted === null ? null : counted - expectedCash;
  const closed = Boolean(data?.closed);
  const noteRequired = difference !== null && Math.abs(difference) >= 0.005;

  const methodRows = METHOD_ORDER.filter((method) =>
    Boolean(methodTotals[method]),
  );

  const closeDay = async () => {
    if (!data || counted === null) return;
    setBusy(true);
    setError(null);
    try {
      const response = await billingService.closeDay({
        branch_id: branchId,
        date,
        counted_cash: countedCash.trim(),
        difference_note: note.trim() || undefined,
      });
      setData(response);
      setCountedCash("");
      setNote("");
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
        {closed ? (
          <span className={styles.lockedBadge}>
            <Lock size={14} aria-hidden="true" />
            {t("billing:day_close.closed_badge")}
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
              <p className={styles.muted}>
                {t("billing:day_close.closed_by", {
                  name:
                    data.close.closed_by_name ||
                    t("billing:day_close.unknown_user"),
                  time: new Date(data.close.closed_at).toLocaleString(),
                })}
              </p>
            </section>
          ) : (
            <section className={styles.card}>
              <div className={styles.cardHead}>
                <h2 className={styles.cardTitle}>
                  {t("billing:day_close.reconcile_title")}
                </h2>
              </div>
              <div className={styles.controls}>
                <label className={styles.field}>
                  <span className={styles.label}>
                    {t("billing:day_close.counted_cash")}
                  </span>
                  <input
                    type="number"
                    min="0"
                    step="0.01"
                    inputMode="decimal"
                    className={styles.input}
                    value={countedCash}
                    onChange={(event) => setCountedCash(event.target.value)}
                    placeholder={t("billing:day_close.counted_placeholder")}
                  />
                </label>
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

              <div className={styles.actions}>
                <button
                  type="button"
                  className={styles.primaryButton}
                  disabled={
                    busy ||
                    counted === null ||
                    !Number.isFinite(counted) ||
                    (noteRequired && !note.trim())
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
        </>
      ) : null}
    </main>
  );
}

export default DayCloseScreen;
