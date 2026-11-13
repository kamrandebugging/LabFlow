import React, { useEffect, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import {
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  RefreshCw,
  Activity,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { patientService } from "./patientService";
import type { PatientDetail } from "./types";

interface PatientHistoryScreenProps {
  patientId: string;
  onBack?: () => void;
  service?: typeof patientService;
}

export const PatientHistoryScreen: React.FC<PatientHistoryScreenProps> = ({
  patientId,
  onBack,
  service = patientService,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    service
      .getPatient(patientId)
      .then((data) => {
        if (isMounted) setPatient(data);
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err && typeof err === "object" && ("code" in err || "status" in err)
              ? messageForError(err, t)
              : t("patients:history.errors.load"),
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service, t]);

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[350px] text-slate-500 gap-2">
        <RefreshCw className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">
          {t("patients:history.loading")}
        </span>
      </div>
    );
  }

  if (error || !patient) {
    return (
      <div className="max-w-2xl mx-auto p-6 text-center space-y-4">
        <div className="w-12 h-12 bg-red-50 text-red-600 rounded-full flex items-center justify-center mx-auto">
          <AlertCircle className="w-6 h-6" />
        </div>
        <h2 className="text-lg font-bold text-slate-900">
          {t("patients:history.unavailable_title")}
        </h2>
        <p className="text-sm text-slate-600">
          {error || t("patients:not_found")}
        </p>
        <button
          type="button"
          onClick={onBack}
          className="px-4 py-2 bg-slate-900 text-white rounded-lg text-sm font-medium hover:bg-slate-800"
        >
          {t("patients:return_to_patients")}
        </button>
      </div>
    );
  }

  return (
    <div className="max-w-5xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* 1. Header */}
      <div>
        <nav aria-label={t("patients:breadcrumb_aria")} className="mb-2">
          <ol className="flex items-center gap-x-2 text-xs text-slate-500">
            <li>
              <button
                type="button"
                onClick={onBack}
                className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
                <span>{t("common:nav.patients")}</span>
              </button>
            </li>
            <li className="text-slate-300">/</li>
            <li dir="ltr" className="font-mono text-slate-700">
              {patient.mrn}
            </li>
            <li className="text-slate-300">/</li>
            <li className="font-medium text-slate-900">
              {t("patients:history.breadcrumb")}
            </li>
          </ol>
        </nav>
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-2">
          <div>
            <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-headline">
              {t("patients:history.title")} <bdi dir="ltr">{patient.name}</bdi>
            </h1>
            <p className="text-xs text-slate-500 mt-1 flex items-center gap-2">
              <span>
                {patient.sex === "M"
                  ? t("patients:sex.male")
                  : t("patients:sex.female")}
              </span>
              <span className="text-slate-300">•</span>
              <span className="font-mono">
                {patient.phone ? (
                  <bdi dir="ltr">{patient.phone}</bdi>
                ) : (
                  t("patients:history.no_phone")
                )}
              </span>
              <span className="text-slate-300">•</span>
              <span>{patient.branch_name || t("patients:main_branch")}</span>
            </p>
          </div>
          <span className="text-xs font-medium text-slate-500 bg-slate-100 px-3 py-1 rounded-full border border-slate-200">
            {t("patients:history.audit_active")}
          </span>
        </div>
      </div>

      {/* Info notice */}
      <div className="bg-teal-50/50 border border-teal-200/80 rounded-xl p-4 flex items-start gap-3">
        <Activity className="w-5 h-5 text-teal-700 mt-0.5 shrink-0" />
        <div className="text-xs text-slate-600 leading-relaxed">
          <span className="font-semibold text-slate-800">
            {t("patients:history.ledger_scope_label")}
          </span>{" "}
          <Trans
            i18nKey="patients:history.ledger_scope_body"
            values={{ mrn: patient.mrn }}
            components={{ strong: <strong dir="ltr" className="font-mono" /> }}
          />
        </div>
      </div>

      {/* Timeline of Clinical Episodes */}
      <div className="space-y-4">
        {/* Registration event */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-teal-600 ring-4 ring-teal-50" />
              <span className="font-semibold text-slate-900 text-sm">
                {t("patients:history.event_registration")}
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400">
              <bdi dir="ltr">{formatDate(patient.created_at)}</bdi>
            </span>
          </div>

          <div className="text-xs text-slate-600 grid grid-cols-1 sm:grid-cols-3 gap-3">
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("patients:history.system_mrn")}
              </span>
              <span className="font-mono font-medium text-slate-800">
                <bdi dir="ltr">{patient.mrn}</bdi>
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("patients:history.home_branch")}
              </span>
              <span className="font-medium text-slate-800">
                {patient.branch_name || t("patients:main_branch")}
              </span>
            </div>
            <div>
              <span className="text-slate-400 block text-[11px]">
                {t("patients:history.iso_status")}
              </span>
              <span className="text-emerald-700 font-medium flex items-center gap-1">
                <CheckCircle2 className="w-3.5 h-3.5" />
                {t("patients:history.verified_active")}
              </span>
            </div>
          </div>
        </div>

        {/* Subsequent visit summary card */}
        <div className="bg-white border border-slate-200 rounded-xl p-5 shadow-sm space-y-3">
          <div className="flex items-center justify-between border-b border-slate-100 pb-3">
            <div className="flex items-center gap-2.5">
              <span className="w-2.5 h-2.5 rounded-full bg-slate-400" />
              <span className="font-semibold text-slate-900 text-sm">
                {t("patients:history.event_visit")}
              </span>
            </div>
            <span className="text-xs font-mono text-slate-400">
              {patient.last_visit ? (
                <bdi dir="ltr">{patient.last_visit}</bdi>
              ) : (
                t("patients:history.recent_visit")
              )}
            </span>
          </div>

          <div className="text-xs text-slate-500 italic">
            {t("patients:history.visit_note")}
          </div>
        </div>
      </div>
    </div>
  );
};
export default PatientHistoryScreen;
