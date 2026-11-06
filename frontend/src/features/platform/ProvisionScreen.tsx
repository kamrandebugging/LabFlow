import type { ReactElement } from "react";
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { platformService } from "./platformService";
import { slugProblem, type ProvisionTenantPayload } from "./types";

export function ProvisionScreen(): ReactElement {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ProvisionTenantPayload>({
    name: "",
    slug: "",
    plan_id: "",
    owner_email: "",
    owner_name: "",
  });
  const [serverError, setServerError] = useState<string | null>(null);

  const plansQuery = useQuery({
    queryKey: ["platform", "plans"],
    queryFn: () => platformService.listPlans(),
  });

  const slugError = useMemo(
    () => (form.slug ? slugProblem(form.slug) : null),
    [form.slug],
  );

  const provision = useMutation({
    mutationFn: () => platformService.provisionTenant(form),
    onSuccess: async (result) => {
      await queryClient.invalidateQueries({
        queryKey: ["platform", "tenants"],
      });
      // 202: the tenant exists in provisioning; the detail screen polls it.
      navigate(`/platform/tenants/${result.id}`, { replace: true });
    },
    onError: (error: Error) => setServerError(error.message),
  });

  const canSubmit =
    form.name.trim().length > 0 &&
    form.slug.trim().length > 0 &&
    slugError === null &&
    form.plan_id !== "" &&
    form.owner_email.trim().length > 0 &&
    form.owner_name.trim().length > 0 &&
    !provision.isPending;

  return (
    <div className="flex flex-col gap-6 p-6">
      <header>
        <h1
          className="text-2xl font-bold tracking-tight text-slate-900"
          style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
        >
          Provision a new lab
        </h1>
        <p className="text-sm text-slate-600">
          Creates the tenant record, primary domain and subscription, then
          queues the provisioning pipeline. The lab stays in provisioning until
          every step completes.
        </p>
      </header>

      <form
        className="max-w-2xl space-y-5 rounded-xl border border-slate-200 bg-white p-6 shadow-sm"
        onSubmit={(event) => {
          event.preventDefault();
          setServerError(null);
          if (canSubmit) provision.mutate();
        }}
      >
        <Field label="Lab name">
          <input
            required
            value={form.name}
            onChange={(event) =>
              setForm((previous) => ({ ...previous, name: event.target.value }))
            }
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
            placeholder="City Diagnostic Lab"
          />
        </Field>

        <Field
          label="Slug"
          hint="Becomes <slug>.<platform-domain> and schema tenant_<slug>."
        >
          <input
            required
            value={form.slug}
            onChange={(event) =>
              setForm((previous) => ({
                ...previous,
                slug: event.target.value.toLowerCase(),
              }))
            }
            className={`w-full rounded-lg border px-3 py-2 font-mono text-sm focus:outline-none focus:ring-1 ${
              slugError
                ? "border-red-300 focus:border-red-500 focus:ring-red-500"
                : "border-slate-300 focus:border-[#0E6B3A] focus:ring-[#0E6B3A]"
            }`}
            placeholder="citylab"
          />
          {slugError ? (
            <p className="mt-1 text-[11px] text-red-700">{slugError}</p>
          ) : form.slug ? (
            <p className="mt-1 text-[11px] text-emerald-700">
              Slug looks valid.
            </p>
          ) : null}
        </Field>

        <Field label="Plan">
          <select
            required
            value={form.plan_id}
            onChange={(event) =>
              setForm((previous) => ({
                ...previous,
                plan_id: event.target.value,
              }))
            }
            className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
          >
            <option value="">Select a plan…</option>
            {(plansQuery.data?.plans ?? [])
              .filter((plan) => plan.is_active)
              .map((plan) => (
                <option key={plan.id} value={plan.id}>
                  {plan.name} — PKR {plan.price}
                  {plan.max_branches === null
                    ? " · unlimited branches"
                    : ` · ${plan.max_branches} branches`}
                </option>
              ))}
          </select>
          {plansQuery.isError ? (
            <p className="mt-1 text-[11px] text-red-700">
              Could not load plans. The form cannot be submitted without one.
            </p>
          ) : null}
        </Field>

        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
          <Field label="Owner name">
            <input
              required
              value={form.owner_name}
              onChange={(event) =>
                setForm((previous) => ({
                  ...previous,
                  owner_name: event.target.value,
                }))
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
              placeholder="Dr. Ayesha Khan"
            />
          </Field>
          <Field label="Owner email">
            <input
              required
              type="email"
              value={form.owner_email}
              onChange={(event) =>
                setForm((previous) => ({
                  ...previous,
                  owner_email: event.target.value,
                }))
              }
              className="w-full rounded-lg border border-slate-300 px-3 py-2 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
              placeholder="owner@citylab.pk"
            />
          </Field>
        </div>

        {serverError ? (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-xs text-red-700">
            {serverError}
          </p>
        ) : null}

        <div className="flex items-center justify-end gap-3 border-t border-slate-100 pt-4">
          <button
            type="button"
            onClick={() => navigate("/platform/tenants")}
            className="rounded-lg px-4 py-2 text-xs font-semibold text-slate-700 hover:bg-slate-100"
          >
            Cancel
          </button>
          <button
            type="submit"
            disabled={!canSubmit}
            className="rounded-lg bg-[#0E6B3A] px-4 py-2 text-xs font-semibold text-white hover:bg-[#0A522C] disabled:opacity-50"
          >
            {provision.isPending ? "Provisioning…" : "Provision lab"}
          </button>
        </div>
      </form>
    </div>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}): ReactElement {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-semibold uppercase tracking-wide text-slate-600">
        {label}
      </span>
      {children}
      {hint ? (
        <span className="mt-1 block text-[11px] text-slate-500">{hint}</span>
      ) : null}
    </label>
  );
}
