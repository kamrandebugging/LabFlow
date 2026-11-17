import { createContext, useContext } from "react";

export interface InvoiceDrawerContextValue {
  hasProvider: boolean;
  invoiceId: string | null;
  openInvoice: (id: string) => void;
  closeInvoice: () => void;
  isNewOpen: boolean;
  openNew: () => void;
  closeNew: () => void;
  /** Bumps after a successful create so the list can refresh. */
  listRevision: number;
}

const noop = () => undefined;

export const InvoiceDrawerContext = createContext<InvoiceDrawerContextValue>({
  hasProvider: false,
  invoiceId: null,
  openInvoice: noop,
  closeInvoice: noop,
  isNewOpen: false,
  openNew: noop,
  closeNew: noop,
  listRevision: 0,
});

export function useInvoiceDrawer(): InvoiceDrawerContextValue {
  return useContext(InvoiceDrawerContext);
}
