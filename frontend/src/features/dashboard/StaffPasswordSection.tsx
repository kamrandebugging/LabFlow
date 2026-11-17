import type { ReactElement } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";
import { useTranslation } from "react-i18next";

import { ApiError } from "../../lib/apiClient";
import { messageForError } from "../../lib/errors";
import { staffService } from "../staff/staffService";
import type { StaffRow } from "../staff/types";
import styles from "./StaffPasswordSection.module.css";

interface TempCredential {
  staffName: string;
  password: string;
  expiresAt: string | null;
}

interface ResetRequest {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
}

/**
 * Dashboard "Staff passwords" section (Owner and Manager).
 *
 * The server decides scope: the Owner sees every non-owner account, a Manager
 * only Receptionist/Technician rows. The reset endpoints re-check that scope
 * on every call, so hiding a button is never the enforcement.
 *
 * A temporary password is shown ONCE with its 24-hour expiry. The Owner
 * account is never listed: owner recovery is the Flow 1 support/platform path.
 */
export function StaffPasswordSection(): ReactElement {
  const { t } = useTranslation("common");
  const [rows, setRows] = useState<StaffRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [credential, setCredential] = useState<TempCredential | null>(null);
  const [requests, setRequests] = useState<ResetRequest[]>([]);

  const translateError = useCallback(
    (err: unknown, fallback: string): string =>
      err instanceof ApiError
        ? messageForError(err, (key, options) => t(`common:${key}`, options))
        : fallback,
    [t],
  );

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      const [response, requestResponse] = await Promise.all([
        staffService.list({ limit: 50 }),
        staffService
          .listPasswordRequests()
          .catch(() => ({ requests: [] as ResetRequest[] })),
      ]);
      setRows(response.results.filter((row) => !row.is_owner));
      setRequests(requestResponse.requests);
      setError(null);
    } catch (err: unknown) {
      setError(translateError(err, "Could not load staff accounts."));
    } finally {
      setLoading(false);
    }
  }, [translateError]);

  useEffect(() => {
    void load();
  }, [load]);

  // Only requests that match a row this actor can actually reset are shown.
  // A Manager must never see an Owner/Manager/Pathologist request as actionable.
  const visibleRequests = useMemo(() => {
    const emails = new Set(rows.map((row) => row.email.toLowerCase()));
    return requests.filter((request) =>
      emails.has(request.email.toLowerCase()),
    );
  }, [requests, rows]);

  const issueTempPassword = async (row: StaffRow): Promise<void> => {
    if (
      !window.confirm(
        `Issue a temporary password for ${row.display_name}? Their current password and sessions stop working immediately.`,
      )
    ) {
      return;
    }
    setBusyId(row.id);
    setError(null);
    setNotice(null);
    try {
      const result = await staffService.resetPassword(row.id);
      setCredential({
        staffName: row.display_name,
        password: result.temp_password,
        expiresAt: result.expires_at ?? null,
      });
      void load();
    } catch (err: unknown) {
      setError(translateError(err, "Could not issue a temporary password."));
    } finally {
      setBusyId(null);
    }
  };

  const resetTotp = async (row: StaffRow): Promise<void> => {
    if (
      !window.confirm(
        `Reset two-factor authentication for ${row.display_name}? They will be asked to enrol again (optional).`,
      )
    ) {
      return;
    }
    setBusyId(row.id);
    setError(null);
    setNotice(null);
    try {
      await staffService.resetTotp(row.id);
      setNotice(`Two-factor authentication reset for ${row.display_name}.`);
      void load();
    } catch (err: unknown) {
      setError(
        translateError(err, "Could not reset two-factor authentication."),
      );
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className={styles.section} aria-labelledby="staff-passwords-title">
      <div className={styles.header}>
        <div>
          <h2 id="staff-passwords-title" className={styles.title}>
            Staff passwords
          </h2>
          <p className={styles.subtitle}>
            Issue a one-time temporary password (24 hours, shown once) or reset
            a lost 2FA. Staff change their own password in Settings.
          </p>
        </div>
      </div>

      {error && (
        <div className={styles.body}>
          <p role="alert" className={styles.alertError}>
            {error}
          </p>
        </div>
      )}

      {visibleRequests.length > 0 && (
        <div className={styles.body}>
          <div role="status" className={styles.requests}>
            <p className={styles.requestsTitle}>
              Staff password requests ({visibleRequests.length})
            </p>
            <ul className={styles.requestList}>
              {visibleRequests.map((request) => (
                <li key={request.id} className={styles.requestRow}>
                  <div>
                    <p className={styles.requestName}>
                      {request.display_name || "Staff member"}
                    </p>
                    <p className={styles.requestMeta} dir="ltr">
                      {request.email} ·{" "}
                      {new Date(request.created_at).toLocaleString()}
                    </p>
                  </div>
                  <div className={styles.requestActions}>
                    <button
                      type="button"
                      disabled={busyId !== null}
                      onClick={() => {
                        const row = rows.find(
                          (candidate) =>
                            candidate.email.toLowerCase() ===
                            request.email.toLowerCase(),
                        );
                        if (!row) {
                          setError(
                            `No resettable staff account matches ${request.email}.`,
                          );
                          return;
                        }
                        void issueTempPassword(row);
                      }}
                      className={styles.primary}
                    >
                      Issue temp password
                    </button>
                    <button
                      type="button"
                      disabled={busyId !== null}
                      onClick={async () => {
                        setBusyId(request.id);
                        setError(null);
                        try {
                          await staffService.resolvePasswordRequest(request.id);
                          void load();
                        } catch (err: unknown) {
                          setError(
                            translateError(
                              err,
                              "Could not dismiss the request.",
                            ),
                          );
                        } finally {
                          setBusyId(null);
                        }
                      }}
                      className={styles.ghost}
                    >
                      Dismiss
                    </button>
                  </div>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}

      {notice && (
        <div className={styles.body}>
          <p role="status" className={styles.alertSuccess}>
            {notice}
          </p>
        </div>
      )}

      {credential && (
        <div className={styles.body}>
          <div className={styles.credential}>
            <p className={styles.credentialLabel}>
              Temporary password for {credential.staffName} — shown once, never
              retrievable again.
            </p>
            <code className={styles.credentialCode}>{credential.password}</code>
            <div className={styles.credentialRow}>
              <button
                type="button"
                onClick={() => {
                  void navigator.clipboard?.writeText(credential.password);
                }}
                className={styles.secondary}
              >
                Copy
              </button>
              <span className={styles.credentialMeta}>
                Expires{" "}
                {credential.expiresAt
                  ? new Date(credential.expiresAt).toLocaleString()
                  : "in 24 hours"}
              </span>
              <button
                type="button"
                onClick={() => setCredential(null)}
                className={styles.ghost}
              >
                Done
              </button>
            </div>
          </div>
        </div>
      )}

      <div className={styles.body}>
        {loading ? (
          <div className={styles.skeleton} />
        ) : rows.length === 0 ? (
          <p className={styles.empty}>
            No staff accounts available for password resets.
          </p>
        ) : (
          <div className={styles.tableWrap}>
            <table className={styles.table}>
              <thead>
                <tr>
                  <th className={styles.th}>Staff member</th>
                  <th className={styles.th}>Role</th>
                  <th className={styles.th}>2FA</th>
                  <th className={`${styles.th} ${styles.thActions}`}>
                    Actions
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row) => (
                  <tr key={row.id} className={styles.row}>
                    <td className={styles.td}>
                      <p className={styles.name}>{row.display_name}</p>
                      <p className={styles.email} dir="ltr">
                        {row.email}
                      </p>
                    </td>
                    <td className={styles.td}>
                      <span className={styles.badge}>{row.role}</span>
                    </td>
                    <td className={styles.td}>
                      {row.totp_status === "enabled" ? "Enabled" : "Off"}
                    </td>
                    <td className={styles.tdActions}>
                      <div className={styles.actions}>
                        <button
                          type="button"
                          disabled={busyId !== null}
                          onClick={() => void issueTempPassword(row)}
                          className={styles.primary}
                        >
                          {busyId === row.id
                            ? "Working…"
                            : "Issue temp password"}
                        </button>
                        <button
                          type="button"
                          disabled={busyId !== null}
                          onClick={() => void resetTotp(row)}
                          className={styles.secondary}
                        >
                          Reset 2FA
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </section>
  );
}
