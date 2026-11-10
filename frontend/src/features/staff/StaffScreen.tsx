import type { ReactElement, ReactNode } from "react";
import { useCallback, useEffect, useMemo, useState } from "react";

import type {
  CreateStaffInput,
  StaffDetail,
  StaffListResponse,
  StaffRole,
  StaffRow,
  StaffTempPasswordResponse,
} from "./types";
import { staffService } from "./staffService";

const ROLE_HELP: Record<StaffRole, string> = {
  manager: "Branch operations, patients, billing, samples and reports.",
  reception: "Registration, invoicing, cash collection and sample intake.",
  technician: "Worklist, result entry and sample receiving.",
  pathologist: "Clinical review and report approval.",
};

type BusyAction = "create" | "edit" | "deactivate" | "reactivate" | "reset";

function Modal({
  title,
  subtitle,
  onClose,
  children,
}: {
  title: string;
  subtitle?: string;
  onClose: () => void;
  children: ReactNode;
}): ReactElement {
  return (
    <div className="fixed inset-0 z-[90] flex items-center justify-center bg-slate-900/50 p-4">
      <div
        role="dialog"
        aria-modal="true"
        aria-label={title}
        className="w-full max-w-2xl max-h-[90vh] overflow-y-auto rounded-2xl bg-white shadow-2xl"
      >
        <div className="flex items-start justify-between border-b border-slate-200 px-6 py-4">
          <div>
            <h2 className="text-lg font-bold text-slate-900 tracking-tight">
              {title}
            </h2>
            {subtitle && (
              <p className="text-xs text-slate-500 mt-1">{subtitle}</p>
            )}
          </div>
          <button
            type="button"
            onClick={onClose}
            className="rounded p-1 text-slate-400 hover:bg-slate-100 hover:text-slate-700"
            aria-label="Close"
          >
            <span className="material-symbols-outlined text-[20px]">close</span>
          </button>
        </div>
        <div className="px-6 py-5">{children}</div>
      </div>
    </div>
  );
}

function TempPasswordPanel({
  result,
  onDone,
}: {
  result: StaffTempPasswordResponse;
  onDone: () => void;
}): ReactElement {
  const [copied, setCopied] = useState(false);
  const copy = (): void => {
    void navigator.clipboard.writeText(result.temp_password);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="space-y-4" data-testid="temp-password-panel">
      <div className="rounded-lg border border-amber-200 bg-amber-50 p-4">
        <p className="text-sm font-semibold text-amber-900">
          Temporary password — shown once
        </p>
        <p className="text-xs text-amber-800 mt-1">
          Give this to {result.staff.display_name} in person. It is never shown
          again, never emailed as the only delivery, and must be changed at
          first login.
        </p>
        <div className="mt-3 flex items-center gap-3">
          <code className="flex-1 rounded-lg border border-amber-300 bg-white px-3 py-2 font-mono text-sm text-slate-900 select-all">
            {result.temp_password}
          </code>
          <button
            type="button"
            onClick={copy}
            className="inline-flex items-center gap-1.5 rounded-lg border border-amber-300 bg-white px-3 py-2 text-xs font-semibold text-amber-950 hover:bg-amber-100"
          >
            <span className="material-symbols-outlined text-[16px]">
              {copied ? "check" : "content_copy"}
            </span>
            {copied ? "Copied" : "Copy"}
          </button>
        </div>
      </div>
      <button
        type="button"
        onClick={onDone}
        className="w-full rounded-lg bg-[#005c55] px-4 py-2.5 text-sm font-semibold text-white hover:bg-[#0f766e]"
      >
        I have saved this password — done
      </button>
    </div>
  );
}

function CreateStaffForm({
  data,
  onCreated,
  onCancel,
}: {
  data: StaffListResponse;
  onCreated: (result: StaffTempPasswordResponse) => void;
  onCancel: () => void;
}): ReactElement {
  const [displayName, setDisplayName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<StaffRole | "">(
    data.enabled_roles[0]?.role ?? "",
  );
  const [branchId, setBranchId] = useState<string>(data.branches[0]?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const tenantWide = role === "pathologist";

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    if (!role) {
      setError("Select a role that is enabled for this lab.");
      return;
    }
    if (!tenantWide && !branchId) {
      setError("Select the staff member's branch.");
      return;
    }
    setBusy(true);
    try {
      const payload: CreateStaffInput = {
        display_name: displayName.trim(),
        email: email.trim(),
        role,
        branch_id: tenantWide ? null : branchId,
      };
      onCreated(await staffService.create(payload));
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not create staff.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form
      onSubmit={submit}
      className="space-y-4"
      data-testid="create-staff-form"
    >
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
          Display name
        </label>
        <input
          required
          aria-label="Display name"
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          placeholder="e.g. Usman Tariq"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
        />
      </div>

      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
          Work email
        </label>
        <input
          required
          type="email"
          aria-label="Work email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="name@lab.pk"
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
        />
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Role
          </label>
          <select
            aria-label="Role"
            value={role}
            onChange={(e) => setRole(e.target.value as StaffRole)}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
          >
            {data.enabled_roles.length === 0 && (
              <option value="">No roles enabled by the platform</option>
            )}
            {data.enabled_roles.map((item) => (
              <option key={item.role} value={item.role}>
                {item.label}
              </option>
            ))}
          </select>
          {role && (
            <p className="mt-1 text-[11px] text-slate-500">{ROLE_HELP[role]}</p>
          )}
        </div>

        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Branch
          </label>
          <select
            aria-label="Branch"
            value={tenantWide ? "" : branchId}
            onChange={(e) => setBranchId(e.target.value)}
            disabled={tenantWide}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100 disabled:text-slate-500 focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
          >
            {tenantWide ? (
              <option value="">All branches (tenant-wide role)</option>
            ) : (
              data.branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.code} — {branch.name}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {error}
        </p>
      )}

      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy}
          className="inline-flex items-center gap-2 rounded-lg bg-[#005c55] px-5 py-2 text-sm font-semibold text-white hover:bg-[#0f766e] disabled:opacity-60"
        >
          <span className="material-symbols-outlined text-[18px]">
            person_add
          </span>
          {busy ? "Creating..." : "Create staff account"}
        </button>
      </div>
    </form>
  );
}

function EditStaffForm({
  staff,
  data,
  onSaved,
  onCancel,
}: {
  staff: StaffRow;
  data: StaffListResponse;
  onSaved: (row: StaffRow) => void;
  onCancel: () => void;
}): ReactElement {
  const [displayName, setDisplayName] = useState(staff.display_name);
  const [role, setRole] = useState<StaffRole | "owner">(staff.role);
  const [branchId, setBranchId] = useState(staff.branch?.id ?? "");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const tenantWide = role === "pathologist";

  const submit = async (event: React.FormEvent): Promise<void> => {
    event.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const updated = await staffService.update(staff.id, {
        display_name: displayName.trim(),
        role: role === "owner" ? undefined : role,
        branch_id: tenantWide ? null : branchId || null,
      });
      onSaved(updated);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not save changes.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <form onSubmit={submit} className="space-y-4" data-testid="edit-staff-form">
      <div>
        <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
          Display name
        </label>
        <input
          required
          value={displayName}
          onChange={(e) => setDisplayName(e.target.value)}
          className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
        />
      </div>
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Role
          </label>
          <select
            value={role}
            onChange={(e) => setRole(e.target.value as StaffRole | "owner")}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
          >
            {data.enabled_roles.map((item) => (
              <option key={item.role} value={item.role}>
                {item.label}
              </option>
            ))}
          </select>
          <p className="mt-1 text-[11px] text-slate-500">
            Only roles the Platform enabled for this lab can be chosen.
          </p>
        </div>
        <div>
          <label className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
            Branch
          </label>
          <select
            aria-label="Branch"
            value={tenantWide ? "" : branchId}
            onChange={(e) => setBranchId(e.target.value)}
            disabled={tenantWide}
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm disabled:bg-slate-100 disabled:text-slate-500 focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
          >
            {tenantWide ? (
              <option value="">All branches (tenant-wide role)</option>
            ) : (
              data.branches.map((branch) => (
                <option key={branch.id} value={branch.id}>
                  {branch.code} — {branch.name}
                </option>
              ))
            )}
          </select>
        </div>
      </div>

      {error && (
        <p
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700"
        >
          {error}
        </p>
      )}

      <div className="flex items-center justify-end gap-3 pt-2">
        <button
          type="button"
          onClick={onCancel}
          className="rounded-lg border border-slate-300 px-4 py-2 text-sm font-medium text-slate-700 hover:bg-slate-50"
        >
          Cancel
        </button>
        <button
          type="submit"
          disabled={busy}
          className="rounded-lg bg-[#005c55] px-5 py-2 text-sm font-semibold text-white hover:bg-[#0f766e] disabled:opacity-60"
        >
          {busy ? "Saving..." : "Save changes"}
        </button>
      </div>
    </form>
  );
}

function DetailPanel({ detail }: { detail: StaffDetail }): ReactElement {
  return (
    <div className="space-y-5" data-testid="staff-detail">
      <div className="grid grid-cols-2 gap-4 text-sm">
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Name
          </p>
          <p className="font-semibold text-slate-900">{detail.display_name}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Email
          </p>
          <p className="font-mono text-slate-800 break-all">{detail.email}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Role
          </p>
          <p className="text-slate-800">{detail.role_label}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Branch
          </p>
          <p className="text-slate-800">
            {detail.branch
              ? `${detail.branch.code} — ${detail.branch.name}`
              : "All branches"}
          </p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Status
          </p>
          <p className="text-slate-800 capitalize">{detail.status}</p>
        </div>
        <div>
          <p className="text-[11px] uppercase tracking-wide text-slate-500">
            Two-factor
          </p>
          <p className="text-slate-800 capitalize">{detail.totp_status}</p>
        </div>
      </div>

      <div>
        <h3 className="text-xs font-semibold uppercase tracking-wide text-slate-600 mb-2">
          Account audit history
        </h3>
        {detail.audit_history.length === 0 ? (
          <p className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-xs text-slate-500">
            No audit entries recorded for this account yet.
          </p>
        ) : (
          <ul className="divide-y divide-slate-100 rounded-lg border border-slate-200">
            {detail.audit_history.map((row) => (
              <li key={row.id} className="px-3 py-2 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span className="font-semibold text-slate-800">
                    {row.action}
                  </span>
                  <span className="text-slate-500">
                    {row.at ? new Date(row.at).toLocaleString() : ""}
                  </span>
                </div>
                <pre className="mt-1 overflow-x-auto whitespace-pre-wrap break-all text-[11px] text-slate-500">
                  {JSON.stringify({ before: row.before, after: row.after })}
                </pre>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}

export function StaffScreen(): ReactElement {
  const [data, setData] = useState<StaffListResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [query, setQuery] = useState("");
  const [statusFilter, setStatusFilter] = useState<
    "" | "active" | "deactivated"
  >("");

  const [createOpen, setCreateOpen] = useState(false);
  const [editTarget, setEditTarget] = useState<StaffRow | null>(null);
  const [detail, setDetail] = useState<StaffDetail | null>(null);
  const [detailLoading, setDetailLoading] = useState(false);
  const [tempResult, setTempResult] =
    useState<StaffTempPasswordResponse | null>(null);
  const [busyRow, setBusyRow] = useState<string | null>(null);
  const [busyAction, setBusyAction] = useState<BusyAction | null>(null);
  const [nextCursor, setNextCursor] = useState<string | null>(null);
  const [loadingMore, setLoadingMore] = useState(false);

  const load = useCallback(async (): Promise<void> => {
    setLoading(true);
    setError(null);
    try {
      const result = await staffService.list({
        q: query.trim() || undefined,
        status: statusFilter,
        limit: 50,
      });
      setData(result);
      setNextCursor(result.next_cursor);
    } catch (err: unknown) {
      setError(err instanceof Error ? err.message : "Could not load staff.");
    } finally {
      setLoading(false);
    }
  }, [query, statusFilter]);

  const loadMore = async (): Promise<void> => {
    if (!nextCursor || loadingMore) return;
    setLoadingMore(true);
    setError(null);
    try {
      const result = await staffService.list({
        q: query.trim() || undefined,
        status: statusFilter,
        cursor: nextCursor,
        limit: 50,
      });
      setData((prev) =>
        prev
          ? {
              ...prev,
              results: [...prev.results, ...result.results],
              staff_count: result.staff_count,
            }
          : result,
      );
      setNextCursor(result.next_cursor);
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not load more staff.",
      );
    } finally {
      setLoadingMore(false);
    }
  };

  useEffect(() => {
    void load();
  }, [load]);

  const replaceRow = (row: StaffRow): void => {
    setData((prev) =>
      prev
        ? {
            ...prev,
            results: prev.results.map((item) =>
              item.id === row.id ? row : item,
            ),
          }
        : prev,
    );
  };

  const handleCreated = (result: StaffTempPasswordResponse): void => {
    setCreateOpen(false);
    setTempResult(result);
    setNotice(null);
    void load();
  };

  const handleReset = async (row: StaffRow): Promise<void> => {
    if (
      !window.confirm(
        `Issue a new temporary password for ${row.display_name}? Their current password stops working immediately and all sessions are revoked.`,
      )
    ) {
      return;
    }
    setBusyRow(row.id);
    setBusyAction("reset");
    setError(null);
    try {
      setTempResult(await staffService.resetPassword(row.id));
      void load();
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not reset the password.",
      );
    } finally {
      setBusyRow(null);
      setBusyAction(null);
    }
  };

  const handleToggleActive = async (row: StaffRow): Promise<void> => {
    const action = row.is_active ? "deactivate" : "reactivate";
    if (
      !window.confirm(
        row.is_active
          ? `Deactivate ${row.display_name}? They are signed out immediately and cannot log in until reactivated. Their history and approvals are kept.`
          : `Reactivate ${row.display_name}? They can log in again with their existing two-factor state.`,
      )
    ) {
      return;
    }
    setBusyRow(row.id);
    setBusyAction(action);
    setError(null);
    try {
      const updated = row.is_active
        ? await staffService.deactivate(row.id)
        : await staffService.reactivate(row.id);
      replaceRow(updated);
      setNotice(
        `${updated.display_name} was ${updated.is_active ? "reactivated" : "deactivated"}.`,
      );
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not update the account.",
      );
    } finally {
      setBusyRow(null);
      setBusyAction(null);
    }
  };

  const openDetail = async (row: StaffRow): Promise<void> => {
    setDetailLoading(true);
    setDetail(null);
    try {
      setDetail(await staffService.get(row.id));
    } catch (err: unknown) {
      setError(
        err instanceof Error ? err.message : "Could not load the profile.",
      );
    } finally {
      setDetailLoading(false);
    }
  };

  const seatText = useMemo(() => {
    if (!data) return "";
    if (data.plan_staff_limit === null) {
      return `${data.staff_count} accounts — unlimited on this plan`;
    }
    return `${data.staff_count} of ${data.plan_staff_limit} plan seats used (Owner counts as a seat)`;
  }, [data]);

  return (
    <div className="mx-auto max-w-6xl space-y-6 px-4 py-6 sm:px-8">
      <div className="flex flex-col gap-4 border-b border-slate-200 pb-4 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-1 flex items-center gap-2 text-xs text-slate-500">
            <span>Settings</span>
            <span className="material-symbols-outlined text-[14px]">
              chevron_right
            </span>
            <span className="font-medium text-teal-700">Staff</span>
          </div>
          <h1 className="text-2xl font-bold tracking-tight text-slate-900">
            Staff accounts
          </h1>
          <p className="mt-0.5 text-sm text-slate-600">
            Create and manage the people who work in your lab.
          </p>
        </div>
        <button
          type="button"
          onClick={() => {
            setCreateOpen(true);
            setError(null);
          }}
          disabled={!data || data.enabled_roles.length === 0}
          className="inline-flex items-center gap-2 rounded-lg bg-[#005c55] px-4 py-2.5 text-sm font-semibold text-white shadow-sm hover:bg-[#0f766e] disabled:opacity-60"
        >
          <span className="material-symbols-outlined text-[18px]">
            person_add
          </span>
          Add staff
        </button>
      </div>

      {data && (
        <div className="flex flex-wrap items-center gap-3 rounded-lg border border-slate-200 bg-white px-4 py-3 text-xs text-slate-600 shadow-sm">
          <span className="inline-flex items-center gap-1.5">
            <span className="material-symbols-outlined text-[16px] text-teal-700">
              badge
            </span>
            {seatText}
          </span>
          <span className="text-slate-300">|</span>
          <span>
            Enabled roles:{" "}
            <strong className="text-slate-800">
              {data.enabled_roles.map((role) => role.label).join(", ") ||
                "None — ask the Platform"}
            </strong>
          </span>
        </div>
      )}

      {notice && (
        <div className="flex items-center justify-between rounded-lg border border-emerald-200 bg-emerald-50 px-4 py-3 text-sm text-emerald-800">
          <span>{notice}</span>
          <button type="button" onClick={() => setNotice(null)}>
            <span className="material-symbols-outlined text-[18px]">close</span>
          </button>
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-lg border border-red-200 bg-red-50 px-4 py-3 text-sm text-red-700"
        >
          {error}
        </div>
      )}

      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div className="relative w-full sm:max-w-xs">
          <span className="material-symbols-outlined absolute left-3 top-1/2 -translate-y-1/2 text-[18px] text-slate-400">
            search
          </span>
          <input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Search name or email"
            className="w-full rounded-lg border border-slate-300 bg-white py-2 pl-9 pr-3 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
          />
        </div>
        <select
          value={statusFilter}
          onChange={(e) =>
            setStatusFilter(e.target.value as "" | "active" | "deactivated")
          }
          className="rounded-lg border border-slate-300 bg-white px-3 py-2 text-sm focus:border-teal-600 focus:outline-none focus:ring-1 focus:ring-teal-600"
        >
          <option value="">All statuses</option>
          <option value="active">Active</option>
          <option value="deactivated">Deactivated</option>
        </select>
      </div>

      {loading ? (
        <div className="space-y-2">
          {[0, 1, 2].map((index) => (
            <div key={index} className="h-16 rounded-lg bg-slate-100" />
          ))}
        </div>
      ) : (
        <div className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
          {data?.owner && (
            <div className="flex flex-col gap-2 border-b border-slate-100 bg-slate-50/60 px-4 py-3 sm:flex-row sm:items-center sm:justify-between">
              <div className="flex items-center gap-3">
                <span className="flex h-9 w-9 items-center justify-center rounded-full bg-[#86f2e4] text-xs font-bold text-[#006f66]">
                  {data.owner.display_name.slice(0, 2).toUpperCase()}
                </span>
                <div>
                  <p className="text-sm font-semibold text-slate-900">
                    {data.owner.display_name}{" "}
                    <span className="ml-1 rounded bg-[#005c55] px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-white">
                      Owner
                    </span>
                  </p>
                  <p className="text-xs text-slate-500">{data.owner.email}</p>
                </div>
              </div>
              <span className="text-[11px] text-slate-500">
                Full access — cannot be edited or deactivated
              </span>
            </div>
          )}

          {data && data.results.length === 0 ? (
            <div className="px-6 py-12 text-center">
              <span className="material-symbols-outlined text-[36px] text-slate-300">
                group_off
              </span>
              <p className="mt-2 text-sm font-semibold text-slate-800">
                No staff accounts yet
              </p>
              <p className="mx-auto mt-1 max-w-md text-xs text-slate-500">
                You are running the lab alone. Add a receptionist or technician
                when you are ready — the Owner account never depends on them.
              </p>
            </div>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-left text-sm">
                <thead className="bg-slate-50 text-[11px] uppercase tracking-wider text-slate-500">
                  <tr>
                    <th className="px-4 py-3 font-semibold">Name</th>
                    <th className="px-4 py-3 font-semibold">Role</th>
                    <th className="px-4 py-3 font-semibold">Branch</th>
                    <th className="px-4 py-3 font-semibold">Status</th>
                    <th className="px-4 py-3 font-semibold">2FA</th>
                    <th className="px-4 py-3 text-right font-semibold">
                      Actions
                    </th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-100">
                  {(data?.results ?? []).map((row) => (
                    <tr key={row.id} className="hover:bg-slate-50/70">
                      <td className="px-4 py-3">
                        <p className="font-semibold text-slate-900">
                          {row.display_name}
                        </p>
                        <p className="text-xs text-slate-500 break-all">
                          {row.email}
                        </p>
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {row.role_label}
                      </td>
                      <td className="px-4 py-3 text-slate-700">
                        {row.branch
                          ? `${row.branch.code} — ${row.branch.name}`
                          : "All branches"}
                      </td>
                      <td className="px-4 py-3">
                        <span
                          className={`inline-flex rounded-full px-2 py-0.5 text-[11px] font-semibold ${
                            row.is_active
                              ? "bg-emerald-50 text-emerald-700"
                              : "bg-slate-100 text-slate-600"
                          }`}
                        >
                          {row.is_active ? "Active" : "Deactivated"}
                        </span>
                      </td>
                      <td className="px-4 py-3 text-xs text-slate-600 capitalize">
                        {row.totp_status}
                      </td>
                      <td className="px-4 py-3">
                        <div className="flex flex-wrap items-center justify-end gap-1">
                          <button
                            type="button"
                            onClick={() => void openDetail(row)}
                            className="rounded px-2 py-1 text-xs font-semibold text-teal-700 hover:bg-teal-50"
                          >
                            View
                          </button>
                          <button
                            type="button"
                            onClick={() => setEditTarget(row)}
                            className="rounded px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100"
                          >
                            Edit
                          </button>
                          <button
                            type="button"
                            disabled={busyRow === row.id}
                            onClick={() => void handleReset(row)}
                            className="rounded px-2 py-1 text-xs font-semibold text-slate-700 hover:bg-slate-100 disabled:opacity-50"
                          >
                            {busyRow === row.id && busyAction === "reset"
                              ? "Resetting…"
                              : "Reset password"}
                          </button>
                          <button
                            type="button"
                            disabled={busyRow === row.id}
                            onClick={() => void handleToggleActive(row)}
                            className={`rounded px-2 py-1 text-xs font-semibold disabled:opacity-50 ${
                              row.is_active
                                ? "text-red-700 hover:bg-red-50"
                                : "text-emerald-700 hover:bg-emerald-50"
                            }`}
                          >
                            {busyRow === row.id &&
                            (busyAction === "deactivate" ||
                              busyAction === "reactivate")
                              ? "Saving…"
                              : row.is_active
                                ? "Deactivate"
                                : "Reactivate"}
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
      )}

      {nextCursor && (
        <div className="flex justify-center">
          <button
            type="button"
            onClick={() => void loadMore()}
            disabled={loadingMore}
            className="rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
          >
            {loadingMore ? "Loading…" : "Load more staff"}
          </button>
        </div>
      )}

      {createOpen && data && (
        <Modal
          title="Add a staff account"
          subtitle="Only roles the Platform enabled for this lab are offered."
          onClose={() => setCreateOpen(false)}
        >
          <CreateStaffForm
            data={data}
            onCreated={handleCreated}
            onCancel={() => setCreateOpen(false)}
          />
        </Modal>
      )}

      {editTarget && data && (
        <Modal
          title={`Edit ${editTarget.display_name}`}
          subtitle="Role and branch changes are audited."
          onClose={() => setEditTarget(null)}
        >
          <EditStaffForm
            staff={editTarget}
            data={data}
            onSaved={(row) => {
              setEditTarget(null);
              replaceRow(row);
              setNotice(`${row.display_name} was updated.`);
              void load();
            }}
            onCancel={() => setEditTarget(null)}
          />
        </Modal>
      )}

      {(detailLoading || detail) && (
        <Modal
          title={detail ? detail.display_name : "Staff profile"}
          subtitle={detail ? detail.email : "Loading profile…"}
          onClose={() => setDetail(null)}
        >
          {detailLoading ? (
            <div className="h-40 rounded-lg bg-slate-100 animate-pulse" />
          ) : detail ? (
            <DetailPanel detail={detail} />
          ) : null}
        </Modal>
      )}

      {tempResult && (
        <Modal
          title="Temporary password issued"
          subtitle="Copy it now — the server will not show it again."
          onClose={() => setTempResult(null)}
        >
          <TempPasswordPanel
            result={tempResult}
            onDone={() => {
              setTempResult(null);
              setNotice("Temporary password issued.");
            }}
          />
        </Modal>
      )}
    </div>
  );
}
