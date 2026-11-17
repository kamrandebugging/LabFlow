import { useCallback, useEffect, useMemo, useState } from "react";
import type { ReactNode } from "react";
import { useLocation, useNavigate } from "react-router-dom";

import { NewInvoiceScreen } from "./NewInvoiceScreen";
import { InvoiceRecordDrawer } from "./InvoiceRecordDrawer";
import {
  InvoiceDrawerContext,
  type InvoiceDrawerContextValue,
} from "./invoiceDrawerContext";

/**
 * Owns the invoice drawers and renders them once, outside the animated page
 * layers — the same architecture as the patient drawers, so a navigation can
 * never duplicate a panel.
 */
export function InvoiceDrawerProvider({
  children,
}: {
  children: ReactNode;
}): JSX.Element {
  const navigate = useNavigate();
  const location = useLocation();
  const [invoiceId, setInvoiceId] = useState<string | null>(null);
  const [isNewOpen, setIsNewOpen] = useState(false);
  const [listRevision, setListRevision] = useState(0);

  const openInvoice = useCallback((id: string) => {
    setIsNewOpen(false);
    setInvoiceId(id);
    if (window.location.pathname !== `/invoices/${id}`) {
      window.history.replaceState(window.history.state, "", `/invoices/${id}`);
    }
  }, []);

  const closeInvoice = useCallback(() => {
    setInvoiceId(null);
    if (window.location.pathname.startsWith("/invoices/")) {
      window.history.replaceState(window.history.state, "", "/invoices");
    }
  }, []);

  const openNew = useCallback(() => {
    setInvoiceId(null);
    setIsNewOpen(true);
  }, []);

  const closeNew = useCallback(() => setIsNewOpen(false), []);

  // Leaving the section must not leave a drawer over another screen.
  useEffect(() => {
    if (!location.pathname.startsWith("/invoices")) {
      setInvoiceId(null);
      setIsNewOpen(false);
    }
  }, [location.pathname]);

  const value = useMemo<InvoiceDrawerContextValue>(
    () => ({
      hasProvider: true,
      invoiceId,
      openInvoice,
      closeInvoice,
      isNewOpen,
      openNew,
      closeNew,
      listRevision,
    }),
    [
      invoiceId,
      openInvoice,
      closeInvoice,
      isNewOpen,
      openNew,
      closeNew,
      listRevision,
    ],
  );

  return (
    <InvoiceDrawerContext.Provider value={value}>
      {children}
      {invoiceId ? (
        <InvoiceRecordDrawer
          key={invoiceId}
          invoiceId={invoiceId}
          onClose={closeInvoice}
        />
      ) : null}
      {isNewOpen ? (
        <NewInvoiceDrawer
          onClose={closeNew}
          onCreated={(id) => {
            setIsNewOpen(false);
            setListRevision((n) => n + 1);
            navigate(`/invoices/${id}`);
          }}
        />
      ) : null}
    </InvoiceDrawerContext.Provider>
  );
}

function NewInvoiceDrawer({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: (id: string) => void;
}): JSX.Element {
  return (
    <div className="fixed inset-0 z-[60] flex justify-end bg-black/40">
      <div className="h-full w-full max-w-[760px] overflow-y-auto bg-[var(--color-surface)] shadow-[var(--shadow-veyla-dropdown)]">
        <NewInvoiceScreen
          onCancel={onClose}
          onSuccess={(invoice) => onCreated(invoice.id)}
        />
      </div>
    </div>
  );
}
