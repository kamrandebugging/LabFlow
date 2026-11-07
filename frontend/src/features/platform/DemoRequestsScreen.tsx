import { useEffect, useMemo, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { platformService } from "./platformService";
import type {
  DemoRequestItem,
  DemoRequestStatus,
  DemoRequestSummary,
} from "./types";

export function DemoRequestsScreen() {
  const navigate = useNavigate();

  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [requests, setRequests] = useState<DemoRequestItem[]>([]);
  const [summary, setSummary] = useState<DemoRequestSummary | null>(null);

  const [search, setSearch] = useState("");
  const [statusTab, setStatusTab] = useState<"ALL" | DemoRequestStatus>("ALL");

  const loadRequests = async () => {
    try {
      setLoading(true);
      setError(null);
      const res = await platformService.listDemoRequests();
      setRequests(res.demo_requests);
      setSummary(res.summary);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Failed to load demo requests.");
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRequests();
  }, []);

  const filtered = useMemo(() => {
    return requests.filter((r) => {
      if (statusTab !== "ALL" && r.status !== statusTab) return false;
      if (search.trim()) {
        const q = search.toLowerCase();
        const matches =
          r.lab_name.toLowerCase().includes(q) ||
          r.contact_person.toLowerCase().includes(q) ||
          r.whatsapp.toLowerCase().includes(q) ||
          r.message.toLowerCase().includes(q);
        if (!matches) return false;
      }
      return true;
    });
  }, [requests, statusTab, search]);

  const getStatusBadge = (status: DemoRequestStatus) => {
    switch (status) {
      case "new":
        return (
          <span className="inline-flex items-center gap-1.5 px-space-xs py-0.5 rounded bg-primary-fixed text-on-primary-fixed font-label-sm text-label-sm font-semibold uppercase">
            <span className="w-1.5 h-1.5 rounded-full bg-primary animate-pulse" />
            NEW
          </span>
        );
      case "contacted":
        return (
          <span className="inline-flex items-center px-space-xs py-0.5 rounded bg-surface-container-high text-on-surface-variant font-label-sm text-label-sm font-semibold uppercase">
            CONTACTED
          </span>
        );
      case "demo_done":
        return (
          <span className="inline-flex items-center px-space-xs py-0.5 rounded bg-secondary-container text-on-secondary-fixed font-label-sm text-label-sm font-bold uppercase">
            DEMO DONE
          </span>
        );
      case "converted":
        return (
          <span className="inline-flex items-center px-space-xs py-0.5 rounded bg-primary text-on-primary font-label-sm text-label-sm font-bold uppercase">
            CONVERTED
          </span>
        );
      case "lost":
        return (
          <span className="inline-flex items-center px-space-xs py-0.5 rounded bg-error-container text-on-error-container font-label-sm text-label-sm font-semibold uppercase">
            LOST
          </span>
        );
    }
  };

  return (
    <div className="flex flex-col w-full gap-space-lg">
      {/* Top Breadcrumb & Actions */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-space-md bg-surface-container-lowest p-space-md rounded shadow-sm">
        <div className="flex flex-col gap-space-2xs">
          <div className="flex items-center gap-space-xs text-outline font-code-sm text-code-sm">
            <span>Platform Growth</span>
            <span className="material-symbols-outlined text-[14px]">chevron_right</span>
            <span className="text-on-surface font-semibold">Inbound Leads</span>
          </div>
          <div className="flex items-center gap-space-md">
            <h1 className="font-headline-lg text-headline-lg text-inverse-surface tracking-tight font-extrabold">
              Demo Requests Inbox
            </h1>
            <span className="font-code-sm text-code-sm px-2 py-0.5 bg-surface-container-high text-on-surface-variant rounded font-semibold">
              High-Intent Inbound Pipeline
            </span>
          </div>
        </div>

        <button
          onClick={loadRequests}
          className="h-8 px-space-sm bg-surface-container-low hover:bg-surface-container text-on-surface rounded font-label-sm text-label-sm flex items-center gap-1 transition-colors self-start md:self-auto"
        >
          <span className="material-symbols-outlined text-[16px]">refresh</span>
          Refresh Pipeline
        </button>
      </div>

      {/* Summary KPI Bento Strip */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-space-md">
        <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">New Inbound</span>
            <span className="material-symbols-outlined text-primary text-[20px]">mark_email_unread</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-primary font-bold tabular-nums">
              {summary?.new_count ?? 0}
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">Awaiting initial outreach</span>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">Contacted</span>
            <span className="material-symbols-outlined text-on-surface-variant text-[20px]">forum</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-inverse-surface font-bold tabular-nums">
              {summary?.contacted_count ?? 0}
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">In conversation / scheduled</span>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">Demo Done</span>
            <span className="material-symbols-outlined text-secondary text-[20px]">co_present</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-inverse-surface font-bold tabular-nums">
              {summary?.demo_done_count ?? 0}
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-outline">Walkthrough completed</span>
        </div>

        <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col justify-between">
          <div className="flex items-center justify-between text-outline">
            <span className="font-label-sm text-label-sm uppercase tracking-wider">Converted Labs</span>
            <span className="material-symbols-outlined text-primary text-[20px]">verified</span>
          </div>
          <div className="my-space-xs">
            <span className="font-headline-xl text-headline-xl text-inverse-surface font-bold tabular-nums">
              {summary?.converted_count ?? 0}
            </span>
          </div>
          <span className="font-body-xs text-body-xs text-primary font-semibold">
            {summary?.total_count ? Math.round(((summary.converted_count) / summary.total_count) * 100) : 0}% win rate
          </span>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-surface-container-lowest p-space-md rounded shadow-sm flex flex-col gap-space-sm">
        <div className="flex flex-col sm:flex-row items-center gap-space-sm">
          <div className="relative flex-1 w-full">
            <span className="material-symbols-outlined absolute left-2 top-1/2 -translate-y-1/2 text-outline text-[18px]">
              search
            </span>
            <input
              type="text"
              placeholder="Search by lab name, director, mobile number or requirements..."
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              className="w-full h-8 bg-surface-container-low pl-8 pr-2 font-body-sm text-body-sm text-on-surface rounded focus:outline-none focus:bg-surface-container-lowest transition-colors"
            />
          </div>

          <div className="flex items-center gap-1 overflow-x-auto w-full sm:w-auto">
            <button
              type="button"
              onClick={() => setStatusTab("ALL")}
              className={`px-3 py-1 font-label-sm text-label-sm rounded transition-colors whitespace-nowrap ${
                statusTab === "ALL"
                  ? "bg-primary text-on-primary font-bold"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              All Leads ({requests.length})
            </button>
            <button
              type="button"
              onClick={() => setStatusTab("new")}
              className={`px-3 py-1 font-label-sm text-label-sm rounded transition-colors whitespace-nowrap flex items-center gap-1 ${
                statusTab === "new"
                  ? "bg-primary text-on-primary font-bold"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              <span className="w-1.5 h-1.5 rounded-full bg-primary" />
              New ({summary?.new_count ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setStatusTab("contacted")}
              className={`px-3 py-1 font-label-sm text-label-sm rounded transition-colors whitespace-nowrap ${
                statusTab === "contacted"
                  ? "bg-primary text-on-primary font-bold"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              Contacted ({summary?.contacted_count ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setStatusTab("demo_done")}
              className={`px-3 py-1 font-label-sm text-label-sm rounded transition-colors whitespace-nowrap ${
                statusTab === "demo_done"
                  ? "bg-primary text-on-primary font-bold"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              Demo Done ({summary?.demo_done_count ?? 0})
            </button>
            <button
              type="button"
              onClick={() => setStatusTab("converted")}
              className={`px-3 py-1 font-label-sm text-label-sm rounded transition-colors whitespace-nowrap ${
                statusTab === "converted"
                  ? "bg-primary text-on-primary font-bold"
                  : "bg-surface-container text-on-surface-variant hover:bg-surface-container-high"
              }`}
            >
              Converted ({summary?.converted_count ?? 0})
            </button>
          </div>
        </div>
      </div>

      {/* Dense Leads Table */}
      <div className="bg-surface-container-lowest shadow-sm rounded overflow-hidden flex flex-col">
        {loading ? (
          <div className="p-12 text-center text-outline">
            <span className="inline-block w-6 h-6 border-2 border-primary/20 border-t-primary rounded-full animate-spin mb-2" />
            <p className="font-body-sm text-body-sm">Loading demo requests...</p>
          </div>
        ) : error ? (
          <div className="p-8 text-center text-error bg-error/5">
            <span className="material-symbols-outlined text-[32px] mb-1">error</span>
            <p className="font-title-sm text-title-sm font-bold">{error}</p>
          </div>
        ) : filtered.length === 0 ? (
          <div className="p-12 text-center text-outline">
            <span className="material-symbols-outlined text-[36px] text-outline/50 mb-2">
              contact_page
            </span>
            <p className="font-title-sm text-title-sm text-on-surface font-semibold">
              No demo requests found in this view
            </p>
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-surface-container-low h-9 font-label-sm text-label-sm text-outline uppercase tracking-wider">
                  <th className="px-3 py-1 font-semibold">Facility Name & Inquiry</th>
                  <th className="px-3 py-1 font-semibold">Contact Person</th>
                  <th className="px-3 py-1 font-semibold">WhatsApp Mobile</th>
                  <th className="px-3 py-1 font-semibold">Requested At</th>
                  <th className="px-3 py-1 font-semibold text-center">Status</th>
                  <th className="px-3 py-1 font-semibold text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-container-high font-body-sm text-body-sm text-on-surface">
                {filtered.map((req) => {
                  const cleanPhone = req.whatsapp.replace(/\D/g, "");
                  const initials = req.lab_name
                    .split(" ")
                    .slice(0, 2)
                    .map((w) => w[0])
                    .join("")
                    .toUpperCase();

                  return (
                    <tr key={req.id} className="h-12 hover:bg-surface-container-low transition-colors">
                      <td className="px-3 py-2">
                        <div className="flex items-center gap-space-sm">
                          <div className="w-8 h-8 rounded bg-primary-fixed text-primary font-bold text-xs flex items-center justify-center shrink-0">
                            {initials || "LF"}
                          </div>
                          <div className="flex flex-col">
                            <Link
                              to={`/platform/demo-requests/${req.id}`}
                              className="font-title-sm text-title-sm font-bold text-on-surface hover:text-primary transition-colors"
                            >
                              {req.lab_name}
                            </Link>
                            <span className="font-body-xs text-body-xs text-outline line-clamp-1">
                              {req.message || "Requested demo via public landing portal."}
                            </span>
                          </div>
                        </div>
                      </td>
                      <td className="px-3 py-2">
                        <div className="flex flex-col">
                          <span className="font-medium text-on-surface">{req.contact_person}</span>
                          <span className="font-code-sm text-xs text-outline">Lead Inquirer</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 font-code-sm font-semibold">
                        <div className="flex items-center gap-1">
                          <a
                            href={`https://wa.me/${cleanPhone}`}
                            target="_blank"
                            rel="noopener noreferrer"
                            className="w-6 h-6 rounded bg-primary-fixed text-primary flex items-center justify-center hover:opacity-80 transition-opacity"
                            title="Chat on WhatsApp"
                          >
                            <span className="material-symbols-outlined text-[14px]">chat</span>
                          </a>
                          <span>{req.whatsapp}</span>
                        </div>
                      </td>
                      <td className="px-3 py-2 font-code-sm text-outline">
                        {new Date(req.requested_at).toLocaleString("en-PK", {
                          day: "numeric",
                          month: "short",
                          hour: "2-digit",
                          minute: "2-digit",
                        })}
                      </td>
                      <td className="px-3 py-2 text-center">{getStatusBadge(req.status)}</td>
                      <td className="px-3 py-2 text-right">
                        <div className="inline-flex items-center gap-1 justify-end">
                          <button
                            type="button"
                            onClick={() => navigate(`/platform/demo-requests/${req.id}`)}
                            className="h-7 px-2.5 bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm rounded transition-colors"
                          >
                            View Lead
                          </button>
                          {req.status !== "converted" && (
                            <button
                              type="button"
                              onClick={() => {
                                const params = new URLSearchParams({
                                  name: req.lab_name,
                                  owner: req.contact_person,
                                  phone: req.whatsapp,
                                  demo_id: req.id,
                                });
                                navigate(`/platform/tenants/new?${params.toString()}`);
                              }}
                              className="h-7 px-2.5 bg-primary-container hover:bg-primary text-on-primary font-label-sm text-label-sm font-bold rounded transition-colors shadow-xs"
                            >
                              Convert
                            </button>
                          )}
                        </div>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
}
