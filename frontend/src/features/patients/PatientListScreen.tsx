import React, { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import {
  AlertTriangle,
  ArrowRight,
  AlertCircle,
  CircleCheck,
  Plus,
  RefreshCw,
  Search,
  User,
} from "lucide-react";
import { messageForError } from "../../lib/errors";
import { formatDate } from "../../lib/format";
import { patientService } from "./patientService";
import { usePatientsDrawer } from "./patientsDrawerContext";
import { RegisterDrawerHost } from "./PatientDrawerHost";
import { calculatePatientAge } from "./patientAge";
import type { PatientSummary } from "./types";
import styles from "./PatientListScreen.module.css";

interface PatientListScreenProps {
  /**
   * Retained for host compatibility: when it is provided the user is allowed
   * to register a patient. The registration itself now happens in the Veyla
   * side drawer so the list keeps its scroll position, search query and
   * filters while a patient is being registered.
   */
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
  // First successful load only: rows fade + slide up once. Search and filter
  // swaps stay instant and never replay the stagger.
  const [animateRows, setAnimateRows] = useState(false);
  const entrancePlayed = useRef(false);

  // Veyla side drawers are owned by the tenant shell so exactly one panel
  // exists at a time, outside the animated page layers.
  const {
    hasProvider,
    openRegister,
    setRegisterTrigger,
    registerRevision,
    openDetail,
    setDetailTrigger,
  } = usePatientsDrawer();

  // Standalone render (no tenant shell): the same drawer is mounted locally so
  // the page still works on its own. The shell path never uses this.
  const [localRegisterOpen, setLocalRegisterOpen] = useState(false);
  const localTriggerRef = useRef<HTMLElement | null>(null);
  const usesLocalDrawer = !hasProvider;

  const searchInputRef = useRef<HTMLInputElement | null>(null);
  const newPatientButtonRef = useRef<HTMLButtonElement | null>(null);

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

  // Patient rows enter once, on the first load after mount.
  useEffect(() => {
    if (isLoading || entrancePlayed.current) return;
    entrancePlayed.current = true;
    setAnimateRows(true);
    const timer = window.setTimeout(() => setAnimateRows(false), 600);
    return () => window.clearTimeout(timer);
  }, [isLoading]);

  // Register the "New patient" button as the drawer's focus-return target.
  useEffect(() => {
    localTriggerRef.current = newPatientButtonRef.current;
    setRegisterTrigger(newPatientButtonRef.current);
  }, [setRegisterTrigger]);

  // A successful registration refreshes the list behind the drawer; its
  // scroll position, search query and filters are untouched.
  useEffect(() => {
    if (registerRevision === 0) return;
    void fetchPatients(searchQuery);
  }, [registerRevision, fetchPatients, searchQuery]);

  // "/" focuses the patient search field. Local to this screen.
  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "/" || event.metaKey || event.ctrlKey || event.altKey) {
        return;
      }
      const target = event.target as HTMLElement | null;
      if (
        target &&
        (target.tagName === "INPUT" ||
          target.tagName === "TEXTAREA" ||
          target.isContentEditable)
      ) {
        return;
      }
      event.preventDefault();
      searchInputRef.current?.focus();
    };

    document.addEventListener("keydown", onKeyDown);
    return () => document.removeEventListener("keydown", onKeyDown);
  }, []);

  const handleSearchChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    setSearchQuery(e.target.value);
  };

  const openRegisterDrawer = () => {
    if (usesLocalDrawer) {
      setLocalRegisterOpen(true);
      return;
    }
    openRegister();
  };

  // Opening a record keeps the list mounted behind the drawer: scroll
  // position, search query and filters are preserved.
  const openPatient = (patientId: string, trigger: HTMLElement | null) => {
    setDetailTrigger(trigger);
    openDetail(patientId);
    onSelectPatient?.(patientId);
  };

  const formatSex = (sex?: string) => {
    if (sex === "M") return t("patients:sex.male");
    if (sex === "F") return t("patients:sex.female");
    if (sex === "O") return t("patients:sex.other");
    return sex || t("patients:sex.unknown");
  };

  return (
    <div className={styles.page}>
      <div className={styles.container}>
        {/* Top Header */}
        <div className={styles.header}>
          <div>
            <h1 className={styles.title}>{t("common:nav.patients")}</h1>
            <p className={styles.subtitle}>{t("patients:list.subtitle")}</p>
          </div>
          <span className={styles.syncBadge}>
            <CircleCheck className={styles.syncIcon} aria-hidden="true" />
            {t("patients:list.branch_sync_active")}
          </span>
        </div>

        {/* Search & Action Bar */}
        <div className={styles.toolbar}>
          <div className={styles.searchWrap}>
            <Search className={styles.searchIcon} aria-hidden="true" />
            <input
              id="patient-search-input"
              ref={searchInputRef}
              type="search"
              value={searchQuery}
              onChange={handleSearchChange}
              placeholder={t("patients:list.search_placeholder")}
              aria-label={t("patients:list.search_placeholder")}
              className={styles.searchInput}
              autoComplete="off"
            />
          </div>
          <div className={styles.toolbarActions}>
            <button
              type="button"
              onClick={() => fetchPatients(searchQuery)}
              className={styles.iconButton}
              title={t("patients:list.refresh_aria")}
              aria-label={t("patients:list.refresh_aria")}
            >
              <RefreshCw
                className={`${styles.spin} ${isLoading ? "" : styles.spinHidden}`}
                aria-hidden="true"
              />
            </button>
            {onNewPatient ? (
              <button
                type="button"
                ref={newPatientButtonRef}
                onClick={openRegisterDrawer}
                className={styles.primaryButton}
              >
                <Plus className={styles.buttonIcon} aria-hidden="true" />
                <span>{t("patients:list.new_patient")}</span>
              </button>
            ) : null}
          </div>
        </div>

        {/* Error Notice */}
        {error && (
          <div role="alert" className={styles.alert}>
            <div className={styles.alertBody}>
              <AlertCircle className={styles.alertIcon} aria-hidden="true" />
              <span>{error}</span>
            </div>
            <button
              type="button"
              onClick={() => fetchPatients(searchQuery)}
              className={styles.retry}
            >
              {t("patients:list.retry")}
            </button>
          </div>
        )}

        {/* Table Card */}
        <div className={styles.tableCard}>
          <div className={styles.tableScroll}>
            <table className={styles.table} data-testid="patient-table">
              <thead>
                <tr>
                  <th scope="col" className={styles.th}>
                    {t("patients:list.col_patient")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("patients:mrn")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("common:labels.phone")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("patients:list.col_branch")}
                  </th>
                  <th scope="col" className={styles.th}>
                    {t("patients:list.col_last_visit")}
                  </th>
                  <th scope="col" className={`${styles.th} ${styles.thEnd}`}>
                    {t("common:labels.actions")}
                  </th>
                </tr>
              </thead>
              <tbody>
                {isLoading ? (
                  /* Flat grey skeleton rows. Strictly no shimmer. */
                  [0, 1, 2, 3].map((row) => (
                    <tr key={row} className={styles.row}>
                      <td colSpan={6} className={styles.td}>
                        <div
                          className={styles.skeletonRow}
                          aria-hidden="true"
                          data-testid="patient-skeleton-row"
                        >
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonCircle}`}
                          />
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonName}`}
                          />
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonMono}`}
                          />
                          <span
                            className={`${styles.skeletonBlock} ${styles.skeletonShort}`}
                          />
                        </div>
                      </td>
                    </tr>
                  ))
                ) : patients.length === 0 ? (
                  /* Full-bleed empty state inside the table card — no nested
                     bordered panel. */
                  <tr className={styles.row}>
                    <td colSpan={6} className={styles.emptyCell}>
                      <div className={styles.emptyInner}>
                        <span className={styles.emptyIconCircle}>
                          <User
                            className={styles.emptyIcon}
                            aria-hidden="true"
                          />
                        </span>
                        <p className={styles.emptyTitle}>
                          {t("patients:list.empty_title")}
                        </p>
                        <p className={styles.emptyHint}>
                          {searchQuery
                            ? t("patients:list.empty_search")
                            : onNewPatient
                              ? t("patients:list.empty_first")
                              : t("patients:list.empty_scope")}
                        </p>
                        {onNewPatient ? (
                          <button
                            type="button"
                            onClick={openRegisterDrawer}
                            className={styles.emptyAction}
                          >
                            <Plus
                              className={styles.buttonIcon}
                              aria-hidden="true"
                            />
                            <span>{t("patients:register.title")}</span>
                          </button>
                        ) : null}
                      </div>
                    </td>
                  </tr>
                ) : (
                  patients.map((patient, index) => {
                    const age = calculatePatientAge(
                      patient.date_of_birth,
                      patient.year_of_birth,
                    );
                    return (
                      <tr
                        key={patient.id}
                        role="button"
                        tabIndex={0}
                        aria-label={patient.name}
                        className={`${styles.row} ${styles.rowClickable}${
                          animateRows ? ` ${styles.rowEnter}` : ""
                        }`}
                        style={
                          animateRows
                            ? {
                                animationDelay: `${Math.min(index, 9) * 20}ms`,
                              }
                            : undefined
                        }
                        onClick={(event) =>
                          openPatient(patient.id, event.currentTarget)
                        }
                        onKeyDown={(event) => {
                          if (event.key !== "Enter" && event.key !== " ") {
                            return;
                          }
                          event.preventDefault();
                          openPatient(patient.id, event.currentTarget);
                        }}
                      >
                        <td className={styles.td}>
                          <span className={styles.patientName}>
                            {patient.name}
                          </span>
                          <span className={styles.patientMeta}>
                            {age !== null
                              ? `${t("patients:list.age_years", { age })} · `
                              : ""}
                            {formatSex(patient.sex)}
                          </span>
                        </td>
                        <td className={styles.td}>
                          <span dir="ltr" className={styles.mrn}>
                            {patient.mrn}
                          </span>
                        </td>
                        <td className={styles.td}>
                          {patient.phone ? (
                            <bdi dir="ltr" className={styles.phone}>
                              {patient.phone}
                            </bdi>
                          ) : (
                            "—"
                          )}
                        </td>
                        <td className={styles.td}>
                          {patient.is_cross_branch ? (
                            <span className={styles.branchBadge}>
                              <AlertTriangle
                                className={styles.branchIcon}
                                aria-hidden="true"
                              />
                              {t("patients:list.cross_branch")}
                            </span>
                          ) : (
                            patient.branch_name || "—"
                          )}
                        </td>
                        <td className={styles.td}>
                          <span className={styles.lastVisit}>
                            {patient.last_visit ||
                              (patient.created_at
                                ? formatDate(patient.created_at)
                                : "—")}
                          </span>
                        </td>
                        <td className={`${styles.td} ${styles.cellEnd}`}>
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              openPatient(
                                patient.id,
                                e.currentTarget.closest("tr"),
                              );
                            }}
                            className={styles.viewButton}
                          >
                            {t("common:actions.view")}
                            <ArrowRight
                              className={styles.arrow}
                              aria-hidden="true"
                            />
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

      {usesLocalDrawer ? (
        <RegisterDrawerHost
          open={localRegisterOpen}
          triggerRef={localTriggerRef}
          onClose={() => setLocalRegisterOpen(false)}
          onRegistered={() => void fetchPatients(searchQuery)}
        />
      ) : null}
    </div>
  );
};
export default PatientListScreen;
