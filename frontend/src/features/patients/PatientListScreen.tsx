import React, { useCallback, useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Plus,
  Search,
  User,
  ArrowRight,
  AlertCircle,
  RefreshCw,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { patientService } from "./patientService";
import type { PatientSummary } from "./types";

interface PatientListScreenProps {
  onNewPatient?: () => void;
  onSelectPatient?: (patientId: string) => void;
  service?: typeof patientService;
}

export const PatientListScreen: React.FC<PatientListScreenProps> = ({
  onNewPatient,
  onSelectPatient,
  service = patientService,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [patients, setPatients] = useState<PatientSummary[]>([]);
  const [searchQuery, setSearchQuery] = useState("");
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchPatients = useCallback(
    async (query?: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const data = await service.listPatients({ q: query });
        setPatients(data);
      } catch (err: unknown) {
        setError(
          err && typeof err === "object" && ("code" in err || "status" in err)
            ? messageForError(err, t)
            : t("patients:list.errors.load"),
        );
      } finally {
        setIsLoading(false);
      }
    },
    [service, t],
  );

  useEffect(() => {
    fetchPatients(searchQuery);
  }, [fetchPatients, searchQuery]);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
  };

  const calculateAge = (dobString?: string | null, yob?: number | null) => {
    if (dobString) {
      const birth = new Date(dobString);
      const diff = Date.now() - birth.getTime();
      const ageDate = new Date(diff);
      return Math.abs(ageDate.getUTCFullYear() - 1970);
    }
    if (yob) {
      return new Date().getFullYear() - yob;
    }
    return null;
  };

  const formatSex = (sex?: string) => {
    if (sex === "M") return t("patients:sex.male");
    if (sex === "F") return t("patients:sex.female");
    if (sex === "O") return t("patients:sex.other");
    return sex || t("patients:sex.unknown");
  };

  return (
    <div className="flex flex-col w-full max-w-7xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Top Header */}
      <div className="flex flex-col sm:flex-row sm:items-end justify-between gap-4">
        <div>
          <h1 className="text-2xl sm:text-3xl font-bold tracking-tight text-slate-900 font-headline">
            {t("common:nav.patients")}
          </h1>
          <p className="text-xs sm:text-sm text-slate-500 mt-1">
            {t("patients:list.subtitle")}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-slate-100 text-slate-600 text-xs font-medium">
            <span className="w-2 h-2 rounded-full bg-teal-600 animate-pulse" />
            {t("patients:list.branch_sync_active")}
          </span>
        </div>
      </div>

      {/* Search & Action Bar */}
      <div className="flex flex-col sm:flex-row items-stretch sm:items-center justify-between gap-4">
        <div className="relative w-full sm:w-96">
          <Search className="absolute start-3 top-1/2 -translate-y-1/2 text-slate-400 w-4 h-4 pointer-events-none" />
          <input
            id="patient-search-input"
            type="search"
            value={searchQuery}
            onChange={handleSearchChange}
            placeholder={t("patients:list.search_placeholder")}
            className="w-full ps-9 pe-4 py-2 bg-white text-slate-900 text-sm placeholder:text-slate-400 rounded-lg border border-slate-200 shadow-sm focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
            autoComplete="off"
          />
        </div>
        <div className="flex items-center justify-end gap-2">
          <button
            type="button"
            onClick={() => fetchPatients(searchQuery)}
            className="p-2 text-slate-500 hover:text-slate-700 hover:bg-slate-100 rounded-lg border border-slate-200 transition-colors"
            title={t("patients:list.refresh_aria")}
            aria-label={t("patients:list.refresh_aria")}
          >
            <RefreshCw
              className={`w-4 h-4 ${isLoading ? "animate-spin" : ""}`}
            />
          </button>
          {onNewPatient ? (
            <button
              type="button"
              onClick={onNewPatient}
              className="inline-flex items-center justify-center gap-1.5 px-4 py-2 bg-[#005c55] hover:bg-[#0f766e] text-white text-sm font-medium rounded-lg shadow-sm transition-colors cursor-pointer"
            >
              <Plus className="w-4 h-4" />
              <span>{t("patients:list.new_patient")}</span>
            </button>
          ) : null}
        </div>
      </div>

      {/* Error Notice */}
      {error && (
        <div
          role="alert"
          className="flex items-center justify-between p-4 rounded-lg bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <div className="flex items-center gap-2">
            <AlertCircle className="w-5 h-5 shrink-0 text-red-600" />
            <span>{error}</span>
          </div>
          <button
            type="button"
            onClick={() => fetchPatients(searchQuery)}
            className="underline font-semibold hover:text-red-900 ms-4"
          >
            {t("patients:list.retry")}
          </button>
        </div>
      )}

      {/* Table Card */}
      <div className="bg-white rounded-xl border border-slate-200 shadow-sm overflow-hidden">
        <div className="overflow-x-auto">
          <table
            className="w-full text-start border-collapse"
            data-testid="patient-table"
          >
            <thead>
              <tr className="bg-slate-50 border-b border-slate-200">
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-start"
                >
                  {t("patients:list.col_patient")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-start"
                >
                  {t("patients:mrn")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-start"
                >
                  {t("common:labels.phone")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-start"
                >
                  {t("patients:list.col_branch")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-start"
                >
                  {t("patients:list.col_last_visit")}
                </th>
                <th
                  scope="col"
                  className="py-3 px-4 text-xs font-semibold uppercase tracking-wider text-slate-500 text-end"
                >
                  {t("common:labels.actions")}
                </th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {isLoading ? (
                <tr>
                  <td
                    colSpan={6}
                    className="py-12 text-center text-slate-500 text-sm"
                  >
                    <div className="inline-flex items-center gap-2">
                      <RefreshCw className="w-4 h-4 animate-spin text-teal-600" />
                      <span>{t("patients:list.loading")}</span>
                    </div>
                  </td>
                </tr>
              ) : patients.length === 0 ? (
                <tr>
                  <td
                    colSpan={6}
                    className="py-12 text-center text-slate-500 text-sm"
                  >
                    <User className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                    <p className="font-medium text-slate-700">
                      {t("patients:list.empty_title")}
                    </p>
                    <p className="text-xs text-slate-400 mt-1">
                      {searchQuery
                        ? t("patients:list.empty_search")
                        : onNewPatient
                          ? t("patients:list.empty_first")
                          : t("patients:list.empty_scope")}
                    </p>
                  </td>
                </tr>
              ) : (
                patients.map((patient) => {
                  const age = calculateAge(
                    patient.date_of_birth,
                    patient.year_of_birth,
                  );
                  return (
                    <tr
                      key={patient.id}
                      className="hover:bg-slate-50/80 transition-colors group cursor-pointer"
                      onClick={() => onSelectPatient?.(patient.id)}
                    >
                      <td className="py-3.5 px-4 align-middle">
                        <div className="flex flex-col">
                          <span className="font-semibold text-slate-900 text-sm leading-snug">
                            {patient.name}
                          </span>
                          <span className="text-xs text-slate-500">
                            {age !== null
                              ? `${t("patients:list.age_years", { age })} · `
                              : ""}
                            {formatSex(patient.sex)}
                          </span>
                        </div>
                      </td>
                      <td className="py-3.5 px-4 align-middle">
                        <span
                          dir="ltr"
                          className="font-mono text-xs font-medium text-slate-800 bg-slate-100 px-2 py-0.5 rounded border border-slate-200"
                        >
                          {patient.mrn}
                        </span>
                      </td>
                      <td className="py-3.5 px-4 align-middle text-sm text-slate-600">
                        {patient.phone ? (
                          <bdi dir="ltr">{patient.phone}</bdi>
                        ) : (
                          "—"
                        )}
                      </td>
                      <td className="py-3.5 px-4 align-middle text-sm text-slate-700">
                        {patient.is_cross_branch ? (
                          <span className="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
                            {t("patients:list.cross_branch")}
                          </span>
                        ) : (
                          patient.branch_name || "—"
                        )}
                      </td>
                      <td className="py-3.5 px-4 align-middle text-sm text-slate-500">
                        {patient.last_visit ||
                          (patient.created_at
                            ? formatDate(patient.created_at)
                            : "—")}
                      </td>
                      <td className="py-3.5 px-4 align-middle text-end">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            onSelectPatient?.(patient.id);
                          }}
                          className="text-xs font-semibold text-teal-700 hover:text-teal-900 inline-flex items-center gap-1 transition-colors"
                        >
                          {t("common:actions.view")}{" "}
                          <ArrowRight className="w-3.5 h-3.5 rtl:rotate-180" />
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
};
export default PatientListScreen;
