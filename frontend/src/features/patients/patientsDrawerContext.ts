import { createContext, useContext } from "react";

export interface PatientsDrawerContextValue {
  /** Register-patient drawer. */
  registerOpen: boolean;
  openRegister: () => void;
  closeRegister: () => void;
  /** Increments after a successful registration so the list can refresh. */
  registerRevision: number;
  /** The element the register drawer returns focus to. */
  setRegisterTrigger: (element: HTMLElement | null) => void;
  /** Patient detail drawer. */
  detailPatientId: string | null;
  openDetail: (patientId: string) => void;
  closeDetail: () => void;
  /** The element the detail drawer returns focus to. */
  setDetailTrigger: (element: HTMLElement | null) => void;
}

/**
 * Standalone fallback so a screen can still be rendered without the tenant
 * shell (unit tests, isolated stories). Opening a drawer is a no-op there.
 */
const noop = () => undefined;

export const PatientsDrawerContext = createContext<PatientsDrawerContextValue>({
  registerOpen: false,
  openRegister: noop,
  closeRegister: noop,
  registerRevision: 0,
  setRegisterTrigger: noop,
  detailPatientId: null,
  openDetail: noop,
  closeDetail: noop,
  setDetailTrigger: noop,
});

export function usePatientsDrawer(): PatientsDrawerContextValue {
  return useContext(PatientsDrawerContext);
}
