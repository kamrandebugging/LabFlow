import type { ReactElement } from "react";
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PlusCircle, Search } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";

import { platformService } from "./platformService";
import {
  TENANT_STATUSES,
  type TenantListItem,
  type TenantStatus,
} from "./types";

const STATUS_STYLES: Record<TenantStatus, string> = {
  active: "bg-emerald-50 text-emerald-800 border-emerald-200",
  provisioning: "bg-sky-50 text-sky-800 border-sky-200",
  suspended: "bg-amber-50 text-amber-800 border-amber-200",
  deleted: "bg-slate-100 text-slate-600 border-slate-200",
};

export function LabsListScreen(): ReactElement {
  const navigate = useNavigate();
  const [query, setQuery] = useState("");
  const [debouncedQuery, setDebouncedQuery] = useState("");
  const [status, setStatus] = useState<TenantStatus | "">("");
  const [cursor, setCursor] = useState<string | null>(null);
  const [rows, setRows] = useState<TenantListItem[]>([]);

  useEffect(() => {
    const timer = window.setTimeout(() => setDebouncedQuery(query.trim()), 300);
    return () => window.clearTimeout(timer);
  }, [query]);

  useEffect(() => {
    setCursor(null);
    setRows([]);
  }, [debouncedQuery, status]);

  const { data, isLoading, isError, error, isFetching } = useQuery({
    queryKey: ["platform", "tenants", debouncedQuery, status, cursor],
    queryFn: () =>
      platformService.listTenants({
        q: debouncedQuery,
        status,
        cursor,
        limit: 25,
      }),
  });

  useEffect(() => {
    if (!data) return;
    setRows((previous) =>
      cursor ? [...previous, ...data.tenants] : data.tenants,
    );
  }, [data, cursor]);

  return (
    <div className="flex flex-col gap-6 p-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1
            className="text-2xl font-bold tracking-tight text-slate-900"
            style={{ fontFamily: "'Plus Jakarta Sans', 'Inter', sans-serif" }}
          >
            Labs registry
          </h1>
          <p className="text-sm text-slate-600">
            Every provisioned tenant with its lifecycle state. Registry metadata
            only — no tenant business data.
          </p>
        </div>
        <button
          type="button"
          onClick={() => navigate("/platform/tenants/new")}
          className="flex items-center gap-2 self-start rounded-lg bg-[#0E6B3A] px-4 py-2 text-sm font-semibold text-white hover:bg-[#0A522C]"
        >
          <PlusCircle className="h-4 w-4" aria-hidden="true" />
          Provision new lab
        </button>
      </header>

      <section className="flex flex-col gap-3 rounded-xl border border-slate-200 bg-white p-3 shadow-sm md:flex-row md:items-center">
        <div className="relative flex-1">
          <Search
            className="pointer-events-none absolute left-3 top-2.5 h-4 w-4 text-slate-400"
            aria-hidden="true"
          />
          <input
            type="search"
            value={query}
            onChange={(event) => setQuery(event.target.value)}
            placeholder="Search by name or slug…"
            className="w-full rounded-lg border border-slate-300 py-1.5 pl-9 pr-3 text-sm focus:border-[#0E6B3A] focus:outline-none focus:ring-1 focus:ring-[#0E6B3A]"
          />
        </div>

        <div className="flex flex-wrap items-center gap-1.5">
          <button
            type="button"
            onClick={() => setStatus("")}
            className={`rounded-md px-2.5 py-1 text-xs font-semibold ${
              status === ""
                ? "bg-slate-900 text-white"
                : "bg-slate-100 text-slate-600"
            }`}
          >
            All
          </button>
          {TENANT_STATUSES.map((option) => (
            <button
              key={option}
              type="button"
              onClick={() => setStatus(option)}
              className={`rounded-md px-2.5 py-1 text-xs font-semibold capitalize ${
                status === option
                  ? "bg-slate-900 text-white"
                  : "bg-slate-100 text-slate-600"
              }`}
            >
              {option}
            </button>
          ))}
        </div>
      </section>

      {isError ? (
        <div className="rounded-xl border border-red-200 bg-red-50 p-4 text-sm text-red-700">
          {error instanceof Error ? error.message : "Could not load labs."}
        </div>
      ) : null}

      <section className="overflow-hidden rounded-xl border border-slate-200 bg-white shadow-sm">
        {isLoading ? (
          <p className="p-10 text-center text-sm text-slate-500">
            Loading labs…
          </p>
        ) : rows.length === 0 ? (
          <div className="flex flex-col items-center gap-2 p-12 text-center">
            <p className="font-semibold text-slate-800">No labs found</p>
            <p className="max-w-sm text-xs text-slate-500">
              {debouncedQuery || status
                ? "No tenant matches these filters."
                : "No labs have been provisioned yet. Provision the first one to get started."}
            </p>
          </div>
        ) : (
          <table className="w-full border-collapse text-left">
            <thead>
              <tr className="border-b border-slate-200 bg-slate-50 text-[11px] font-semibold uppercase tracking-wider text-slate-500">
                <th className="px-4 py-3">Lab</th>
                <th className="px-4 py-3">Slug</th>
                <th className="px-4 py-3">Status</th>
                <th className="px-4 py-3">Provisioned</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100 text-sm">
              {rows.map((row) => (
                <tr key={row.id} className="hover:bg-slate-50">
                  <td className="px-4 py-3">
                    <Link
                      to={`/platform/tenants/${row.id}`}
                      className="font-semibold text-slate-900 hover:text-[#0E6B3A]"
                    >
                      {row.name}
                    </Link>
                  </td>
                  <td className="px-4 py-3 font-mono text-xs text-slate-600">
                    {row.slug}
                  </td>
                  <td className="px-4 py-3">
                    <span
                      className={`inline-flex items-center gap-1.5 rounded-full border px-2 py-0.5 text-xs font-medium capitalize ${STATUS_STYLES[row.status]}`}
                    >
                      <span className="h-1.5 w-1.5 rounded-full bg-current" />
                      {row.status}
                    </span>
                  </td>
                  <td className="px-4 py-3 text-xs text-slate-600">
                    {new Date(row.created_at).toLocaleDateString()}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}

        {data?.next_cursor ? (
          <div className="border-t border-slate-100 p-3 text-center">
            <button
              type="button"
              onClick={() => setCursor(data.next_cursor)}
              disabled={isFetching}
              className="rounded-lg border border-slate-300 px-4 py-1.5 text-xs font-semibold text-slate-700 hover:bg-slate-50 disabled:opacity-60"
            >
              {isFetching ? "Loading…" : "Load more"}
            </button>
          </div>
        ) : null}
      </section>
    </div>
  );
}
