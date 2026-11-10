import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";

import { useAuthStore } from "../auth/authStore";
import { ROLE_LABELS } from "../auth/access";
import { billingService } from "../billing/billingService";
import { patientService } from "../patients/patientService";
import { reportsService } from "../reports/reportsService";
import { resultsService } from "../results/resultsService";
import { sampleService } from "../samples/sampleService";

interface SummaryCard {
  label: string;
  value: string;
  hint: string;
  to: string;
  icon: string;
}

/**
 * Role-specific landing screen for non-Owner staff.
 *
 * Everything shown is read from the real APIs; a failed call renders an
 * honest em dash rather than a fabricated number.
 */
export function RoleHomeScreen(): ReactElement {
  const user = useAuthStore((state) => state.user);
  const role = user?.role;
  const [cards, setCards] = useState<SummaryCard[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let active = true;
    setLoading(true);
    setError(null);

    const load = async (): Promise<SummaryCard[]> => {
      if (role === "reception") {
        const [patients, invoices, samples] = await Promise.allSettled([
          patientService.listPatients(),
          billingService.listInvoices({ limit: 100 }),
          sampleService.listSamples({}),
        ]);
        return [
          {
            label: "Patients",
            value:
              patients.status === "fulfilled"
                ? String(patients.value.length)
                : "—",
            hint: "Registered in your branch",
            to: "/patients",
            icon: "personal_injury",
          },
          {
            label: "Invoices",
            value:
              invoices.status === "fulfilled"
                ? String(invoices.value.results?.length ?? 0)
                : "—",
            hint: "Recent billing activity",
            to: "/invoices",
            icon: "receipt_long",
          },
          {
            label: "Samples",
            value:
              samples.status === "fulfilled"
                ? String(samples.value.results.length)
                : "—",
            hint: "Accessions in your branch",
            to: "/samples",
            icon: "colorize",
          },
        ];
      }

      if (role === "technician") {
        const [worklist, samples] = await Promise.allSettled([
          resultsService.getWorklist(),
          sampleService.listSamples({}),
        ]);
        return [
          {
            label: "Worklist",
            value:
              worklist.status === "fulfilled"
                ? String(worklist.value.length)
                : "—",
            hint: "Samples awaiting bench work",
            to: "/worklist",
            icon: "assignment",
          },
          {
            label: "Samples",
            value:
              samples.status === "fulfilled"
                ? String(samples.value.results.length)
                : "—",
            hint: "Accessions in your branch",
            to: "/samples",
            icon: "colorize",
          },
        ];
      }

      if (role === "pathologist") {
        const [approvals, reports, exceptions] = await Promise.allSettled([
          resultsService.getApprovalsQueue(),
          reportsService.getReports({ limit: 100 }),
          reportsService.getExceptions(),
        ]);
        return [
          {
            label: "Approvals",
            value:
              approvals.status === "fulfilled"
                ? String(approvals.value.length)
                : "—",
            hint: "Results awaiting your signature",
            to: "/results/approvals",
            icon: "verified",
          },
          {
            label: "Reports",
            value:
              reports.status === "fulfilled"
                ? String(reports.value.results?.length ?? 0)
                : "—",
            hint: "Latest report versions",
            to: "/reports",
            icon: "lab_profile",
          },
          {
            label: "Exceptions",
            value:
              exceptions.status === "fulfilled"
                ? String(exceptions.value.counts?.total ?? 0)
                : "—",
            hint: "Operational exceptions to review",
            to: "/exceptions",
            icon: "warning",
          },
        ];
      }

      // Manager (and any future staff role) gets branch oversight.
      const [patients, invoices, samples] = await Promise.allSettled([
        patientService.listPatients(),
        billingService.listInvoices({ limit: 100 }),
        sampleService.listSamples({}),
      ]);
      return [
        {
          label: "Patients",
          value:
            patients.status === "fulfilled"
              ? String(patients.value.length)
              : "—",
          hint: "Registered in your branches",
          to: "/patients",
          icon: "personal_injury",
        },
        {
          label: "Invoices",
          value:
            invoices.status === "fulfilled"
              ? String(invoices.value.results?.length ?? 0)
              : "—",
          hint: "Recent billing activity",
          to: "/invoices",
          icon: "receipt_long",
        },
        {
          label: "Samples",
          value:
            samples.status === "fulfilled"
              ? String(samples.value.results.length)
              : "—",
          hint: "Accessions in your branches",
          to: "/samples",
          icon: "colorize",
        },
      ];
    };

    void load()
      .then((items) => {
        if (active) setCards(items);
      })
      .catch(() => {
        if (active) setError("Some live figures could not be loaded.");
      })
      .finally(() => {
        if (active) setLoading(false);
      });

    return () => {
      active = false;
    };
  }, [role]);

  const displayName =
    user?.display_name || user?.name || user?.email || "Staff member";

  return (
    <div className="max-w-6xl mx-auto px-4 sm:px-8 py-8 space-y-6">
      <div>
        <p className="text-xs text-slate-500">
          <span className="material-symbols-outlined align-middle text-[14px] mr-1">
            home
          </span>
          {role ? ROLE_LABELS[role] : "Staff"} workspace
        </p>
        <h1 className="text-2xl font-bold text-slate-900 tracking-tight mt-1">
          Welcome, {displayName}
        </h1>
        <p className="text-sm text-slate-600 mt-1">
          This is your role&apos;s workspace. Only the tools your role needs are
          listed here.
        </p>
      </div>

      {error && (
        <div className="rounded-lg border border-amber-200 bg-amber-50 px-4 py-3 text-sm text-amber-900">
          {error}
        </div>
      )}

      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {loading
          ? [0, 1, 2, 3].map((index) => (
              <div
                key={index}
                className="h-36 rounded-xl bg-slate-100 animate-pulse"
              />
            ))
          : cards.map((card) => (
              <Link
                key={card.label}
                to={card.to}
                className="group rounded-xl border border-slate-200 bg-white p-5 shadow-sm hover:border-teal-300 hover:shadow transition-all"
              >
                <div className="flex items-start justify-between">
                  <div>
                    <p className="text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                      {card.label}
                    </p>
                    <p className="text-3xl font-bold text-slate-900 mt-1">
                      {card.value}
                    </p>
                  </div>
                  <span className="w-10 h-10 rounded-lg bg-[#86f2e4]/40 text-[#005c55] flex items-center justify-center">
                    <span className="material-symbols-outlined text-[22px]">
                      {card.icon}
                    </span>
                  </span>
                </div>
                <p className="text-xs text-slate-500 mt-3 group-hover:text-teal-700">
                  {card.hint}
                </p>
              </Link>
            ))}
      </div>

      <div className="rounded-xl border border-slate-200 bg-white p-5 shadow-sm">
        <div className="flex items-center gap-2">
          <span className="material-symbols-outlined text-[#005c55] text-[20px]">
            shield
          </span>
          <h2 className="text-sm font-bold text-slate-900">
            Your access is limited to this role
          </h2>
        </div>
        <p className="text-xs text-slate-600 mt-2 max-w-3xl">
          The server checks your role on every request. Owner-only screens
          (staff, branches, partner registry, catalog management) redirect here,
          and the API refuses them even if a link is typed manually.
        </p>
      </div>
    </div>
  );
}
