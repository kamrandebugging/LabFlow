import React, {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ReactNode } from "react";
import { useTranslation } from "react-i18next";
import { useLocation, useNavigate } from "react-router-dom";
import { AlertCircle } from "lucide-react";

import { useAuthStore } from "../auth/authStore";
import { canAccessPath } from "../auth/access";
import type { UserRole } from "../auth/types";
import { settingsService } from "../settings/settingsService";
import { RegisterPatientScreen } from "./RegisterPatientScreen";
import { PatientDetailsScreen } from "./PatientDetailsScreen";
import { VeylaDrawer } from "./VeylaDrawer";
import { patientService } from "./patientService";
import {
  PatientsDrawerContext,
  type PatientsDrawerContextValue,
} from "./patientsDrawerContext";
import styles from "./PatientForm.module.css";
import listStyles from "./PatientListScreen.module.css";

interface PatientsDrawerProviderProps {
  children: ReactNode;
}

/**
 * Owns the two patient drawers and renders them ONCE, outside the animated
 * page layers.
 *
 * Why it lives here: `PageTransition` keeps the leaving page mounted for its
 * 150ms exit animation. A drawer rendered inside that page therefore existed
 * twice during a navigation — once in the leaving layer and once in the
 * arriving one — and the leaving copy was positioned against the transition's
 * `transform`, which offset the panel and clipped its backdrop. Mounting the
 * drawers at the shell level means there is always exactly one panel, one
 * backdrop and one open state, and no page transition can duplicate them.
 */
export function PatientsDrawerProvider({
  children,
}: PatientsDrawerProviderProps): JSX.Element {
  const user = useAuthStore((state) => state.user);

  const [registerOpen, setRegisterOpen] = useState(false);
  const [registerRevision, setRegisterRevision] = useState(0);
  const registerTriggerRef = useRef<HTMLElement | null>(null);

  const [detailPatientId, setDetailPatientId] = useState<string | null>(null);
  const detailTriggerRef = useRef<HTMLElement | null>(null);

  const openRegister = useCallback(() => setRegisterOpen(true), []);
  const closeRegister = useCallback(() => setRegisterOpen(false), []);
  const setRegisterTrigger = useCallback((element: HTMLElement | null) => {
    registerTriggerRef.current = element;
  }, []);

  const openDetail = useCallback((patientId: string) => {
    setDetailPatientId(patientId);
    // Update the address bar without a router navigation, so the page
    // transition does not replay. Direct loads of the same URL are handled
    // by the /patients/:id route, which opens this drawer on mount.
    if (
      typeof window !== "undefined" &&
      window.location.pathname !== `/patients/${patientId}`
    ) {
      window.history.replaceState(
        window.history.state,
        "",
        `/patients/${patientId}`,
      );
    }
  }, []);

  const closeDetail = useCallback(() => {
    setDetailPatientId(null);
    if (
      typeof window !== "undefined" &&
      window.location.pathname.startsWith("/patients/")
    ) {
      window.history.replaceState(window.history.state, "", "/patients");
    }
  }, []);

  const setDetailTrigger = useCallback((element: HTMLElement | null) => {
    detailTriggerRef.current = element;
  }, []);

  // Leaving the Patients area must not leave a drawer hanging over another
  // screen. The state clears without touching the address bar.
  const location = useLocation();
  useEffect(() => {
    if (!location.pathname.startsWith("/patients")) {
      setRegisterOpen(false);
      setDetailPatientId(null);
    }
  }, [location.pathname]);

  const value = useMemo<PatientsDrawerContextValue>(
    () => ({
      registerOpen,
      openRegister,
      closeRegister,
      registerRevision,
      setRegisterTrigger,
      detailPatientId,
      openDetail,
      closeDetail,
      setDetailTrigger,
    }),
    [
      registerOpen,
      openRegister,
      closeRegister,
      registerRevision,
      setRegisterTrigger,
      detailPatientId,
      openDetail,
      closeDetail,
      setDetailTrigger,
    ],
  );

  return (
    <PatientsDrawerContext.Provider value={value}>
      {children}
      <RegisterDrawerHost
        open={registerOpen}
        triggerRef={registerTriggerRef}
        onClose={closeRegister}
        onRegistered={() => setRegisterRevision((n) => n + 1)}
      />
      <DetailDrawerHost
        patientId={detailPatientId}
        triggerRef={detailTriggerRef}
        onClose={closeDetail}
        role={user?.role}
      />
    </PatientsDrawerContext.Provider>
  );
}

/* ------------------------------------------------------- register drawer -- */

interface RegisterDrawerHostProps {
  open: boolean;
  triggerRef: React.MutableRefObject<HTMLElement | null>;
  onClose: () => void;
  onRegistered: () => void;
}

function RegisterDrawerHost({
  open,
  triggerRef,
  onClose,
  onRegistered,
}: RegisterDrawerHostProps): JSX.Element | null {
  const { t } = useTranslation(["patients", "common"]);
  const user = useAuthStore((state) => state.user);
  const [branchId, setBranchId] = useState<string | null>(null);
  const [branchError, setBranchError] = useState<string | null>(null);

  useEffect(() => {
    if (!open) return;
    let active = true;
    setBranchError(null);

    settingsService
      .getBranches()
      .then((branches) => {
        if (!active) return;
        const preferred =
          branches.find((b) => user?.branch_ids?.includes(b.id)) ??
          branches.find((b) => b.code === "HQ1") ??
          branches[0];
        if (preferred) setBranchId(preferred.id);
        else setBranchError("No active branch is available for registration.");
      })
      .catch(() => {
        if (active) setBranchError("Could not load the branch list.");
      });

    return () => {
      active = false;
    };
  }, [open, user?.branch_ids]);

  if (!open) return null;

  return branchId ? (
    <RegisterPatientScreen
      variant="drawer"
      branchId={branchId}
      service={patientService}
      onSuccess={onRegistered}
      onCancel={onClose}
    />
  ) : (
    <VeylaDrawer
      open
      onClose={onClose}
      title={t("patients:register.title")}
      subtitle={t("patients:register.iso_badge")}
      triggerRef={triggerRef}
    >
      {branchError ? (
        <div role="alert" className={listStyles.alert}>
          <div className={listStyles.alertBody}>
            <AlertCircle className={listStyles.alertIcon} aria-hidden="true" />
            <span>{branchError}</span>
          </div>
        </div>
      ) : (
        <p className={styles.drawerLoading}>{t("common:empty.loading")}</p>
      )}
    </VeylaDrawer>
  );
}

/* --------------------------------------------------------- detail drawer -- */

interface DetailDrawerHostProps {
  patientId: string | null;
  triggerRef: React.MutableRefObject<HTMLElement | null>;
  onClose: () => void;
  role?: UserRole;
}

function DetailDrawerHost({
  patientId,
  triggerRef,
  onClose,
  role,
}: DetailDrawerHostProps): JSX.Element | null {
  const navigate = useNavigate();

  if (!patientId) return null;

  const canManage = canAccessPath(role, `/patients/${patientId}/edit`);
  const canDelete = role === "owner" || role === "manager";

  return (
    <PatientDetailsScreen
      key={patientId}
      variant="drawer"
      patientId={patientId}
      triggerRef={triggerRef}
      onBack={onClose}
      onEdit={(id) => navigate(`/patients/${id}/edit`)}
      onViewHistory={(id) => navigate(`/patients/${id}/history`)}
      onNewVisit={() => {
        onClose();
        navigate("/patients");
      }}
      canManage={canManage}
      canDelete={canDelete}
    />
  );
}
