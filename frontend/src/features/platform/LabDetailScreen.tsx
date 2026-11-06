import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { ArrowLeft, RefreshCw, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { platformService } from "./platformService";
import type { TenantDetail } from "./types";

const STUCK_AFTER_MS = 15 * 60 * 1000;

function formatBytes(bytes: number | null): string {
  if (bytes === null) return "unavailable";
  if (bytes < 1024) return `${bytes} B`;
  const units = ["KB", "MB", "GB"];
  let value = bytes / 1024;
  let index = 0;
  while (value >= 1024 && index < units.length - 1) {
    value /= 1024;
    index += 1;
  }
  return `${value.toFixed(1)} ${units[index] ?? "GB"}`;
}

export function LabDetailScreen(): ReactElement {
  const { id = "" } = useParams<{ id: string }>();
  const queryClient = useQueryClient();
  const [reason, setReason] = useState("");
  const [confirmAction, setConfirmAction] = useState<
    "suspend" | "offboard" | null
  >(null);
  const [typedName, setTypedName] = useState("");
  const [actionError, setActionError] = useState<string | null>(null);

  const detailQuery = useQuery({
    queryKey: ["platform", "tenant", id],
    queryFn: () => platformService.getTenant(id),
    enabled: Boolean(id),
  });

  const auditQuery = useQuery({
    queryKey: ["platform", "tenant", id, "audit"],
    queryFn: () => platformService.getTenantAudit(id),
    enabled: Boolean(id),
  });

  const detail = detailQuery.data;

  // Poll while provisioning so the step/failure surfaces without a refresh.
  useEffect(() => {
    if (detail?.status !== "provisioning") return;
    const timer = window.setInterval(() => {
      void detailQuery.refetch();
    }, 5000);
    return () => window.clearInterval(timer);
  }, [detail?.status, detailQuery]);

  const invalidate = async () => {
    await queryClient.invalidateQueries({ queryKey: ["platform", "tenant", id] });
  };

  const suspend = useMutation({
    mutationFn: () => platformService.suspendTenant(id, reason.trim()),
    onSuccess: async () => {
      setConfirmAction(null);
      setReason("");
      await invalidate();
    },
    onError: (error: Error) => setActionError(error.message),
  });

  const offboard = useMutation({
    mutationFn: () => platformService.offboardTenant(id),
    onSuccess: async () => {
      setConfirmAction(null);
      setTypedName("");
      await invalidate();
    },
    onError: (error: Error) => setActionError(error.message),
  });

  const reactivate = useMutation({
    mutationFn: () => platformService.reactivateTenant(id),
    onSuccess: invalidate,
    onError: (error: Error) => setActionError(error.message),
  });

  const retry = useMutation({
    mutationFn: () => platformService.retryProvisioning(id),
    onSuccess: invalidate,
    onError: (error: Error) => setActionError(error.message),
  });

  if (detailQuery.isLoading) {
    return <p className="p-6 text-sm text-slate-500">Loading lab…</p>;
  }

  if (detailQuery.isError || !detail) {
    return (
      <div className="p-6">
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {detailQuery.error instanceof Error
            ? detailQuery.error.message
            : "Lab not found."}
        </div>
        <Link
          to="/platform/tenants"
          className="mt-4 inline-flex items-center gap-2 text-sm font-semibold text-[#0E6B3A]"
        >
          <ArrowLeft className="h-4 w-4" /> Back to labs
        </Link>
      </div>
    );
  }

  const stuck =
    detail.status === "provisioning" &&
    detail.provisioning.last_action_at !== null &&
    Date.now() - new Date(detail.provisioning.last_action_at).getTime() >
      STUCK_AFTER_MS;

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
        <div>
          <Link
            to="/platform/tenants"
            className="inline-flex items-center gap-1.5 text-xs font-semibold text-slate-500 hover:text-slate-800"
          >
            <ArrowLeft className="h-3.5 w-3.5" /> Labs
          </Link>
          <h1
            className="mt-2 text-2xl font-bold tracking-tight text-slate-900"
            style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
          >
            {detail.name}
          </h1>
          <p className="font-mono text-xs text-slate-500">
            {detail.slug} · {detail.schema_name}
          </p>
        </div>

        <div className="flex flex-wrap gap-2">
          {detail.status === "active" ? (
            <button
              type="button"
              onClick={() => {
                setActionError(null);
                setConfirmAction("suspend");
              }}
              className="rounded-lg border border-amber-300 bg-amber-50 px-3 py-1.5 text-xs font-semibold text-amber-900 hover:bg-amber-100"
            >
              Suspend
            </button>
          ) : null}
          {detail.status === "suspended" ? (
            <button
              type="button"
              onClick={() => reactivate.mutate()}
              disabled={reactivate.isPending}
              className="rounded-lg border border-emerald-300 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-900 hover:bg-emerald-100 disabled:opacity-60"
            >
              Reactivate
            </button>
          ) : null}
          {detail.status === "provisioning" ? (
            <button
              type="button"
              onClick={() => retry.mutate()}
              disabled={retry.isPending}
              className="flex items-center gap-1.5 rounded-lg border border-sky-300 bg-sky-50 px-3 py-1.5 text-xs font-semibold text-sky-900 hover:bg-sky-100 disabled:opacity-60"
            >
              <RefreshCw className="h-3.5 w-3.5" /> Retry provisioning
            </button>
          ) : null}
          <button
            type="button"
            onClick={() => {
              setActionError(null);
              setConfirmAction("offboard");
            }}
            className="rounded-lg border border-rose-300 bg-rose-50 px-3 py-1.5 text-xs font-semibold text-rose-900 hover:bg-rose-100"
          >
            Start offboarding
          </button>
        </div>
      </header>

      {actionError ? (
        <p className="rounded-xl border border-red-200 bg-red-50 p-3 text-sm text-red-700">
          {actionError}
        </p>
      ) : null}

      {stuck ? (
        <div className="flex items-start gap-2 rounded-xl border border-amber-200 bg-amber-50 p-4 text-sm text-amber-900">
          <ShieldAlert className="mt-0.5 h-4 w-4" aria-hidden="true" />
          <p>
            Provisioning has not advanced for over 15 minutes. Stuck at step{" "}
            <span className="font-mono font-semibold">
              {detail.provisioning.current_step ?? "unknown"}
            </span>
            {detail.provisioning.failed_step
              ? ` (failed step: ${detail.provisioning.failed_step})`
              : ""}
            .
          </p>
        </div>
      ) : null}

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Section title="Domains">
          {detail.domains.length === 0 ? (
            <p className="text-sm text-slate-500">No domain registered.</p>
          ) : (
            <ul className="space-y-1 text-sm">
              {detail.domains.map((domain) => (
                <li key={domain.domain} className="flex justify-between">
                  <span className="font-mono text-xs text-slate-700">
                    {domain.domain}
                  </span>
                  {domain.is_primary ? (
                    <span className="text-[11px] font-semibold uppercase text-[#0E6B3A]">
                      primary
                    </span>
                  ) : null}
                </li>
              ))}
            </ul>
          )}
        </Section>

        <Section title="Subscription & plan">
          {detail.plan && detail.subscription ? (
            <dl className="space-y-1 text-sm">
              <Row label="Plan" value={detail.plan.name} />
              <Row label="Price" value={`PKR ${detail.plan.price}`} />
              <Row label="Status" value={detail.subscription.status} />
              <Row
                label="Started"
                value={
                  detail.subscription.started_at
                    ? new Date(detail.subscription.started_at).toLocaleDateString()
                    : "—"
                }
              />
            </dl>
          ) : (
            <p className="text-sm text-slate-500">No subscription on record.</p>
          )}
        </Section>

        <Section title="Branches (used vs plan limit)">
          <p className="text-2xl font-bold text-slate-900">
            {detail.branches_used}
            <span className="text-base font-medium text-slate-500">
              {" / "}
              {detail.branches_limit ?? "unlimited"}
            </span>
          </p>
          <p className="mt-1 text-[11px] text-slate-500">
            Counter mirrored into the public tenant row by the branch service.
          </p>
        </Section>

        <Section title="Schema & migrations">
          <dl className="space-y-1 text-sm">
            <Row label="Schema size" value={formatBytes(detail.schema_size_bytes)} />
            <Row
              label="Schema exists"
              value={detail.migration_state.schema_exists ? "yes" : "no"}
            />
            <Row
              label="Applied migrations"
              value={String(detail.migration_state.applied_migrations)}
            />
            <Row
              label="Pending migrations"
              value={String(detail.migration_state.pending_migrations)}
            />
            <Row
              label="In sync"
              value={detail.migration_state.in_sync ? "yes" : "no"}
            />
          </dl>
        </Section>

        <Section title="Provisioning pipeline">
          <dl className="space-y-1 text-sm">
            <Row label="Status" value={detail.status} />
            <Row label="Current step" value={detail.provisioning.current_step ?? "—"} />
            <Row label="Failed step" value={detail.provisioning.failed_step ?? "none"} />
            <Row
              label="Completed steps"
              value={
                detail.provisioning.completed_steps.length > 0
                  ? detail.provisioning.completed_steps.join(", ")
                  : "—"
              }
            />
            <Row label="Owner" value={detail.provisioning.owner_email || "—"} />
          </dl>
          {detail.provisioning.error ? (
            <p className="mt-2 rounded-lg bg-rose-50 p-2 font-mono text-[11px] text-rose-800">
              {detail.provisioning.error}
            </p>
          ) : null}
        </Section>

        <Section title="Audit history">
          {auditQuery.isLoading ? (
            <p className="text-sm text-slate-500">Loading…</p>
          ) : (auditQuery.data?.audit.length ?? 0) === 0 ? (
            <p className="text-sm text-slate-500">No audit entries yet.</p>
          ) : (
            <ul className="space-y-1.5 text-xs">
              {auditQuery.data?.audit.slice(0, 12).map((entry) => (
                <li key={entry.id} className="flex justify-between gap-3">
                  <span className="font-mono text-slate-700">{entry.action}</span>
                  <span className="shrink-0 text-slate-500">
                    {entry.at ? new Date(entry.at).toLocaleString() : "—"}
                  </span>
                </li>
              ))}
            </ul>
          )}
        </Section>
      </div>

      {confirmAction === "suspend" ? (
        <Modal title={`Suspend ${detail.name}`} onClose={() => setConfirmAction(null)}>
          <p className="text-sm text-slate-600">
            Suspending blocks tenant access immediately. A reason is required and
            is written to the platform audit log.
          </p>
          <textarea
            value={reason}
            onChange={(event) => setReason(event.target.value)}
            rows={3}
            className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder="Reason for suspension"
          />
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirmAction(null)}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={suspend.isPending || reason.trim().length === 0}
              onClick={() => suspend.mutate()}
              className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-50"
            >
              {suspend.isPending ? "Suspending…" : `Suspend ${detail.name}`}
            </button>
          </div>
        </Modal>
      ) : null}

      {confirmAction === "offboard" ? (
        <Modal title={`Offboard ${detail.name}`} onClose={() => setConfirmAction(null)}>
          <div className="space-y-2 text-sm text-slate-700">
            <p className="font-semibold text-rose-800">
              Export first, then offboard.
            </p>
            <ol className="list-decimal space-y-1 pl-5 text-xs">
              <li>The owner must complete a full data export.</li>
              <li>Offboarding suspends the tenant immediately.</li>
              <li>
                The schema is dropped only after the 30-day grace period, or with
                an explicit, audited waiver.
              </li>
            </ol>
            <p className="text-xs text-slate-500">
              Type the lab name to confirm:{" "}
              <span className="font-mono">{detail.name}</span>
            </p>
          </div>
          <input
            value={typedName}
            onChange={(event) => setTypedName(event.target.value)}
            className="mt-3 w-full rounded-lg border border-slate-300 px-3 py-2 text-sm"
            placeholder={detail.name}
          />
          <div className="mt-4 flex justify-end gap-2">
            <button
              type="button"
              onClick={() => setConfirmAction(null)}
              className="rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-100"
            >
              Cancel
            </button>
            <button
              type="button"
              disabled={offboard.isPending || typedName.trim() !== detail.name}
              onClick={() => offboard.mutate()}
              className="rounded-lg bg-rose-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-rose-700 disabled:opacity-50"
            >
              {offboard.isPending ? "Starting…" : "Execute offboarding"}
            </button>
          </div>
        </Modal>
      ) : null}
    </div>
  );
}

function Section({
  title,
  children,
}: {
  title: string;
  children: React.ReactNode;
}): ReactElement {
  return (
    <section className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
      <h2 className="mb-3 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
        {title}
      </h2>
      {children}
    </section>
  );
}

function Row({ label, value }: { label: string; value: string }): ReactElement {
  return (
    <div className="flex justify-between gap-3">
      <dt className="text-slate-500">{label}</dt>
      <dd className="text-right font-medium text-slate-900">{value}</dd>
    </div>
  );
}

function Modal({
  title,
  onClose,
  children,
}: {
  title: string;
  onClose: () => void;
  children: React.ReactNode;
}): ReactElement {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-900/40 p-4">
      <div className="w-full max-w-md rounded-2xl border border-slate-200 bg-white p-6 shadow-xl">
        <div className="mb-3 flex items-center justify-between">
          <h3 className="text-base font-bold text-slate-900">{title}</h3>
          <button
            type="button"
            onClick={onClose}
            className="text-slate-400 hover:text-slate-700"
            aria-label="Close"
          >
            ×
          </button>
        </div>
        {children}
      </div>
    </div>
  );
}

export type { TenantDetail };
