import React, { useEffect, useRef, useState } from "react";
import { Trans, useTranslation } from "react-i18next";
import { useAuthStore } from "../auth/authStore";
import { messageForError } from "../../lib/errors";
import { settingsService } from "./settingsService";
import type { DataExport } from "./types";

export const DataExportScreen: React.FC = () => {
  const { t } = useTranslation(["settings", "common"]);
  const user = useAuthStore((s) => s.user);
  const isOwner = user?.role === "owner";

  const [activeExport, setActiveExport] = useState<DataExport | null>(null);
  const [isRequesting, setIsRequesting] = useState<boolean>(false);
  const [errorMsg, setErrorMsg] = useState<string | null>(null);
  const [successMsg, setSuccessMsg] = useState<string | null>(null);

  // Poll timer ref to safely clean up polling on unmount
  const pollIntervalRef = useRef<NodeJS.Timeout | null>(null);

  const cleanupPolling = (): void => {
    if (pollIntervalRef.current) {
      clearInterval(pollIntervalRef.current);
      pollIntervalRef.current = null;
    }
  };

  useEffect(() => {
    return () => {
      cleanupPolling();
    };
  }, []);

  const startPolling = (exportId: string): void => {
    cleanupPolling();

    pollIntervalRef.current = setInterval(async () => {
      try {
        const statusData = await settingsService.getExportStatus(exportId);
        setActiveExport(statusData);

        if (statusData.status === "complete" || statusData.status === "ready") {
          cleanupPolling();
          setSuccessMsg(t("settings:exports.generated"));
        } else if (statusData.status === "failed") {
          cleanupPolling();
          setErrorMsg(t("settings:exports.failed_poll"));
        }
      } catch (err: unknown) {
        cleanupPolling();
        setErrorMsg(
          messageForError(err, (key, options) => t(`common:${key}`, options)),
        );
      }
    }, 2000);
  };

  const handleRequestExport = async (): Promise<void> => {
    if (!isOwner) return;

    setIsRequesting(true);
    setErrorMsg(null);
    setSuccessMsg(null);
    cleanupPolling();

    try {
      const result = await settingsService.requestExport();
      const initialExport: DataExport = {
        id: result.export_id,
        status: "pending",
        requested_at: new Date().toISOString(),
        completed_at: null,
      };
      setActiveExport(initialExport);
      startPolling(result.export_id);
    } catch (err: unknown) {
      setErrorMsg(
        messageForError(err, (key, options) => t(`common:${key}`, options)),
      );
    } finally {
      setIsRequesting(false);
    }
  };

  return (
    <div className="flex-1 bg-slate-50 min-h-screen px-4 sm:px-8 py-6 max-w-4xl mx-auto space-y-6">
      {/* Header & Breadcrumb */}
      <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4 pb-3 border-b border-slate-200">
        <div>
          <div className="flex items-center gap-2 text-xs text-slate-500 mb-1">
            <span>{t("common:nav.settings")}</span>
            <span className="material-symbols-outlined text-[14px] rtl:rotate-180">
              chevron_right
            </span>
            <span className="text-teal-700 font-medium">
              {t("settings:exports.breadcrumb")}
            </span>
          </div>
          <h1 className="text-2xl font-bold text-slate-900 tracking-tight">
            {t("settings:exports.title")}
          </h1>
          <p className="text-sm text-slate-600 mt-0.5">
            {t("settings:exports.subtitle")}
          </p>
        </div>

        <div className="flex items-center gap-2">
          <span className="inline-flex items-center gap-1.5 font-mono text-xs text-slate-700 bg-white px-3 py-1.5 rounded-lg border border-slate-200 shadow-xs">
            <span className="material-symbols-outlined text-[15px] text-teal-600">
              lock
            </span>
            <span>{t("settings:exports.archive_badge")}</span>
          </span>
        </div>
      </div>

      {/* Notifications */}
      {errorMsg && (
        <div className="bg-red-50 border border-red-200 rounded-lg p-4 flex items-start gap-3 text-red-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-red-600 shrink-0">
            error
          </span>
          <div>
            <p className="font-semibold">{t("settings:exports.error_title")}</p>
            <p className="text-red-700 mt-0.5">{errorMsg}</p>
          </div>
        </div>
      )}

      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 rounded-lg p-4 flex items-start gap-3 text-emerald-800 text-sm">
          <span className="material-symbols-outlined text-[20px] text-emerald-600 shrink-0">
            check_circle
          </span>
          <p className="font-medium">{successMsg}</p>
        </div>
      )}

      {/* Security Guarantee Banner */}
      <div className="bg-amber-50/70 border border-amber-200 rounded-xl p-4 flex items-start gap-3.5 text-xs text-amber-900">
        <span className="material-symbols-outlined text-[22px] text-amber-700 shrink-0 mt-0.5">
          security
        </span>
        <div className="space-y-1">
          <p className="font-bold text-amber-950">
            {t("settings:exports.guarantee_title")}
          </p>
          <p className="leading-relaxed text-amber-800">
            <Trans
              i18nKey="settings:exports.guarantee_body"
              components={{
                code: (
                  <code className="font-mono bg-amber-100/80 px-1 py-0.5 rounded text-amber-900" />
                ),
              }}
            />
          </p>
          <p className="font-semibold text-amber-950 pt-0.5">
            <Trans
              i18nKey="settings:exports.secrets_body"
              components={{ bdi: <bdi dir="ltr" /> }}
            />
          </p>
        </div>
      </div>

      {/* Main Request Card */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-6">
        <div className="flex items-start justify-between">
          <div>
            <h2 className="text-base font-bold text-slate-900">
              {t("settings:exports.request_title")}
            </h2>
            <p className="text-xs text-slate-500 mt-1">
              {t("settings:exports.request_desc")}
            </p>
          </div>
          <span className="text-xs text-slate-500 bg-slate-100 border border-slate-200 px-2.5 py-1 rounded-md font-medium">
            {t("settings:exports.owner_only")}
          </span>
        </div>

        {/* Export Scope Details */}
        <div className="space-y-2">
          <p className="text-xs font-semibold text-slate-700 uppercase tracking-wider">
            {t("settings:exports.scope_title")}
          </p>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3 text-xs">
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
              <span className="font-bold text-slate-900 block">
                {t("settings:exports.scope_patients")}
              </span>
              <span className="text-slate-500 block">
                {t("settings:exports.scope_patients_desc")}
              </span>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
              <span className="font-bold text-slate-900 block">
                {t("settings:exports.scope_samples")}
              </span>
              <span className="text-slate-500 block">
                {t("settings:exports.scope_samples_desc")}
              </span>
            </div>
            <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg space-y-1">
              <span className="font-bold text-slate-900 block">
                {t("settings:exports.scope_reports")}
              </span>
              <span className="text-slate-500 block">
                {t("settings:exports.scope_reports_desc")}
              </span>
            </div>
          </div>
        </div>

        {/* Read-only Mode Notice */}
        <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-xs text-slate-600 flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-teal-600 shrink-0">
            verified_user
          </span>
          <span>{t("settings:exports.read_only_note")}</span>
        </div>

        {/* Action Button */}
        {isOwner ? (
          <div className="pt-2 flex items-center justify-between">
            <span className="text-xs text-slate-500">
              {t("settings:exports.links_note")}
            </span>
            <button
              type="button"
              onClick={handleRequestExport}
              disabled={isRequesting || activeExport?.status === "pending"}
              className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 active:bg-teal-800 disabled:bg-teal-400 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
            >
              <span className="material-symbols-outlined text-[18px]">
                download
              </span>
              <span>
                {isRequesting
                  ? t("settings:exports.initiating")
                  : activeExport?.status === "pending"
                    ? t("settings:exports.generating")
                    : t("settings:exports.request")}
              </span>
            </button>
          </div>
        ) : (
          <div className="bg-slate-100 border border-slate-200 rounded-lg p-3 text-xs text-slate-600 text-center">
            {t("settings:exports.not_owner")}
          </div>
        )}
      </div>

      {/* Active Export Status Card */}
      {activeExport && (
        <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm space-y-4">
          <div className="flex items-center justify-between pb-2 border-b border-slate-100">
            <div className="flex items-center gap-2">
              <h3 className="text-base font-bold text-slate-900">
                {t("settings:exports.status_title")}
              </h3>
              <span className="font-mono text-xs text-slate-500">
                ({activeExport.id})
              </span>
            </div>

            {activeExport.status === "pending" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-amber-50 text-amber-700 border border-amber-200 font-semibold">
                <span className="w-2 h-2 rounded-full bg-amber-500 animate-ping"></span>
                {t("settings:exports.processing")}
              </span>
            )}

            {(activeExport.status === "complete" ||
              activeExport.status === "ready") && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-emerald-50 text-emerald-700 border border-emerald-200 font-semibold">
                <span className="w-2 h-2 rounded-full bg-emerald-600"></span>
                {t("settings:exports.ready")}
              </span>
            )}

            {activeExport.status === "failed" && (
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-xs bg-red-50 text-red-700 border border-red-200 font-semibold">
                <span className="w-2 h-2 rounded-full bg-red-600"></span>
                {t("settings:exports.failed")}
              </span>
            )}
          </div>

          <div className="text-xs text-slate-600 space-y-2">
            <p>
              <strong>{t("settings:exports.requested")}</strong>{" "}
              {new Date(activeExport.requested_at).toLocaleString("en-GB")}
            </p>

            {activeExport.status === "pending" && (
              <div className="space-y-2 pt-2">
                <div className="w-full bg-slate-100 h-2 rounded-full overflow-hidden">
                  <div className="bg-teal-600 h-full w-2/3 animate-pulse"></div>
                </div>
                <p className="text-slate-500 text-[11px]">
                  {t("settings:exports.compiling")}
                </p>
              </div>
            )}

            {(activeExport.status === "complete" ||
              activeExport.status === "ready") && (
              <div className="pt-3 space-y-3">
                <p className="text-emerald-700 font-semibold">
                  {t("settings:exports.verified")}
                </p>
                {activeExport.download_url ? (
                  <a
                    href={activeExport.download_url}
                    download
                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      file_download
                    </span>
                    <span>{t("settings:exports.download")}</span>
                  </a>
                ) : (
                  <a
                    href={`/api/v1/exports/${activeExport.id}/download`}
                    download
                    className="inline-flex items-center gap-2 px-5 py-2.5 bg-teal-600 hover:bg-teal-700 text-white rounded-lg text-sm font-semibold shadow-sm transition-all"
                  >
                    <span className="material-symbols-outlined text-[18px]">
                      file_download
                    </span>
                    <span>{t("settings:exports.download")}</span>
                  </a>
                )}
              </div>
            )}

            {activeExport.status === "failed" && (
              <p className="text-red-600">
                {t("settings:exports.error_details")}{" "}
                {t("settings:exports.failed_generic")}
              </p>
            )}
          </div>
        </div>
      )}
    </div>
  );
};
