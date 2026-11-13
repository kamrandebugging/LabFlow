import React, { useEffect, useState } from "react";
import { useTranslation } from "react-i18next";
import { ArrowLeft, Check, Loader2, AlertCircle } from "lucide-react";
import { messageForError } from "../../lib/errors";
import { patientService } from "./patientService";
import type { PatientDetail, PatientUpdateInput } from "./types";

interface PatientEditScreenProps {
  patientId: string;
  onBack?: () => void;
  onSuccess?: () => void;
  onCancel?: () => void;
  service?: typeof patientService;
}

export const PatientEditScreen: React.FC<PatientEditScreenProps> = ({
  patientId,
  onSuccess,
  onCancel,
  service = patientService,
}) => {
  const { t } = useTranslation(["patients", "common"]);
  const [patient, setPatient] = useState<PatientDetail | null>(null);
  const [name, setName] = useState("");
  const [phone, setPhone] = useState("");
  const [sex, setSex] = useState<"M" | "F">("M");
  const [dateOfBirth, setDateOfBirth] = useState("");

  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let isMounted = true;
    setIsLoading(true);
    setError(null);

    service
      .getPatient(patientId)
      .then((data) => {
        if (!isMounted) return;
        setPatient(data);
        setName(data.name || "");
        setPhone(data.phone || "");
        setSex(data.sex === "F" ? "F" : "M");
        setDateOfBirth(
          data.date_of_birth ? data.date_of_birth.slice(0, 10) : "",
        );
      })
      .catch((err) => {
        if (isMounted)
          setError(
            err && typeof err === "object" && ("code" in err || "status" in err)
              ? messageForError(err, t)
              : t("patients:edit.errors.load"),
          );
      })
      .finally(() => {
        if (isMounted) setIsLoading(false);
      });

    return () => {
      isMounted = false;
    };
  }, [patientId, service, t]);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError(null);

    const trimmedName = name.trim();
    if (trimmedName.length < 2 || trimmedName.length > 120) {
      setError(t("patients:edit.validation.name"));
      return;
    }

    const cleanPhone = phone.replace(/[\s\-()+]/g, "");
    if (!/^\d{10,15}$/.test(cleanPhone)) {
      setError(t("patients:validation.phone"));
      return;
    }

    setIsSaving(true);
    try {
      const payload: PatientUpdateInput = {
        name: trimmedName,
        phone: cleanPhone,
        sex,
        date_of_birth: dateOfBirth || null,
      };

      await service.updatePatient(patientId, payload, patient?.version);
      onSuccess?.();
    } catch (err: unknown) {
      setError(
        err && typeof err === "object" && ("code" in err || "status" in err)
          ? messageForError(err, t)
          : t("patients:edit.errors.save"),
      );
    } finally {
      setIsSaving(false);
    }
  };

  if (isLoading) {
    return (
      <div className="flex flex-col items-center justify-center min-h-[350px] text-slate-500 gap-2">
        <Loader2 className="w-6 h-6 animate-spin text-teal-600" />
        <span className="text-sm font-medium">
          {t("patients:edit.loading")}
        </span>
      </div>
    );
  }

  return (
    <div className="max-w-2xl mx-auto p-4 sm:p-6 lg:p-8 space-y-6">
      {/* Header */}
      <div>
        <nav aria-label={t("patients:breadcrumb_aria")} className="mb-2">
          <ol className="flex items-center gap-x-2 text-xs text-slate-500">
            <li>
              <button
                type="button"
                onClick={onCancel}
                className="hover:text-slate-800 transition-colors inline-flex items-center gap-1"
              >
                <ArrowLeft className="w-3.5 h-3.5 rtl:rotate-180" />
                <span>{t("patients:edit.breadcrumb_record")}</span>
              </button>
            </li>
            <li className="text-slate-300">/</li>
            <li className="font-medium text-slate-900">
              {t("patients:edit_demographics")}
            </li>
          </ol>
        </nav>
        <div className="flex items-baseline justify-between">
          <h1 className="text-2xl font-bold tracking-tight text-slate-900 font-headline">
            {t("patients:edit.title")}
          </h1>
          {patient?.mrn && (
            <span dir="ltr" className="text-xs font-mono text-slate-500">
              {patient.mrn}
            </span>
          )}
        </div>
      </div>

      {/* Error alert */}
      {error && (
        <div
          role="alert"
          className="flex items-start gap-2.5 p-4 rounded-xl bg-red-50 border border-red-200 text-red-700 text-sm"
        >
          <AlertCircle className="w-5 h-5 text-red-600 shrink-0 mt-0.5" />
          <div className="flex flex-col">
            <span className="font-semibold">
              {t("patients:edit.save_failed")}
            </span>
            <span className="text-xs text-red-600 mt-0.5">{error}</span>
          </div>
        </div>
      )}

      {/* Form Card */}
      <div className="bg-white rounded-xl border border-slate-200 p-6 sm:p-8 shadow-sm">
        <form onSubmit={handleSubmit} className="space-y-6">
          <div className="space-y-4">
            <div>
              <label
                htmlFor="editFullName"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                {t("patients:field_full_name")}{" "}
                <span className="text-red-500">*</span>
              </label>
              <input
                id="editFullName"
                name="name"
                type="text"
                required
                value={name}
                onChange={(e) => setName(e.target.value)}
                className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div>
                <label
                  htmlFor="editPhone"
                  className="block text-xs font-semibold text-slate-700 mb-1.5"
                >
                  {t("patients:edit.field_phone")}{" "}
                  <span className="text-red-500">*</span>
                </label>
                <input
                  id="editPhone"
                  name="phone"
                  type="tel"
                  dir="ltr"
                  required
                  value={phone}
                  onChange={(e) => setPhone(e.target.value)}
                  className="w-full rounded-lg border border-slate-300 bg-white px-3.5 py-2.5 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
                />
              </div>

              <div>
                <span className="block text-xs font-semibold text-slate-700 mb-1.5">
                  {t("patients:edit.field_sex")}{" "}
                  <span className="text-red-500">*</span>
                </span>
                <div className="flex items-center gap-x-6 h-10 px-1">
                  <label className="inline-flex items-center cursor-pointer select-none">
                    <input
                      type="radio"
                      name="editSex"
                      value="M"
                      checked={sex === "M"}
                      onChange={() => setSex("M")}
                      className="w-4 h-4 text-teal-600 border-slate-300 focus:ring-teal-500"
                    />
                    <span className="ms-2 text-sm text-slate-700">
                      {t("patients:sex.male")}
                    </span>
                  </label>
                  <label className="inline-flex items-center cursor-pointer select-none">
                    <input
                      type="radio"
                      name="editSex"
                      value="F"
                      checked={sex === "F"}
                      onChange={() => setSex("F")}
                      className="w-4 h-4 text-teal-600 border-slate-300 focus:ring-teal-500"
                    />
                    <span className="ms-2 text-sm text-slate-700">
                      {t("patients:sex.female")}
                    </span>
                  </label>
                </div>
              </div>
            </div>

            <div>
              <label
                htmlFor="editDob"
                className="block text-xs font-semibold text-slate-700 mb-1.5"
              >
                {t("common:labels.dob")}
              </label>
              <input
                id="editDob"
                name="dateOfBirth"
                type="date"
                value={dateOfBirth}
                onChange={(e) => setDateOfBirth(e.target.value)}
                className="w-full sm:w-64 rounded-lg border border-slate-300 bg-white px-3.5 py-2 text-sm text-slate-900 focus:outline-none focus:ring-2 focus:ring-teal-500/20 focus:border-teal-600 transition-all"
              />
            </div>
          </div>

          <div className="pt-6 border-t border-slate-100 flex items-center justify-end gap-3">
            <button
              type="button"
              onClick={onCancel}
              className="px-4 py-2.5 rounded-lg border border-slate-300 text-slate-700 bg-white hover:bg-slate-50 text-sm font-medium transition-colors"
            >
              {t("common:actions.cancel")}
            </button>
            <button
              type="submit"
              disabled={isSaving}
              className="px-5 py-2.5 rounded-lg bg-[#005c55] hover:bg-[#0f766e] text-white text-sm font-medium shadow-sm transition-colors flex items-center gap-2 cursor-pointer disabled:opacity-60"
            >
              {isSaving ? (
                <Loader2 className="w-4 h-4 animate-spin" />
              ) : (
                <Check className="w-4 h-4" />
              )}
              <span>
                {isSaving
                  ? t("common:actions.saving")
                  : t("patients:edit.save")}
              </span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
};
export default PatientEditScreen;
