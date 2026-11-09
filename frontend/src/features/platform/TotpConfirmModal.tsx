import { useState } from "react";

interface TotpConfirmModalProps {
  isOpen: boolean;
  title: string;
  description: string;
  confirmLabel?: string;
  confirmVariant?: "primary" | "danger";
  isLoading?: boolean;
  error?: string | null;
  onConfirm: (totpCode: string) => Promise<void> | void;
  onCancel: () => void;
}

export function TotpConfirmModal({
  isOpen,
  title,
  description,
  confirmLabel = "Confirm Action",
  confirmVariant = "primary",
  isLoading = false,
  error = null,
  onConfirm,
  onCancel,
}: TotpConfirmModalProps) {
  const [totpCode, setTotpCode] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);

  if (!isOpen) return null;

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    const clean = totpCode.trim();
    if (!clean || clean.length < 6) {
      setLocalError("Please enter a valid 6-digit authenticator code.");
      return;
    }
    setLocalError(null);
    onConfirm(clean);
  };

  const isDanger = confirmVariant === "danger";

  return (
    <div className="fixed inset-0 bg-black/50 z-50 flex items-center justify-center p-4">
      <div className="bg-surface-container-lowest max-w-md w-full p-space-lg rounded-lg shadow-xl border border-outline-variant/40 flex flex-col gap-space-md animate-in fade-in zoom-in-95 duration-150">
        <div className="flex items-center gap-space-xs">
          <span
            className={`material-symbols-outlined text-[24px] ${
              isDanger ? "text-error" : "text-primary"
            }`}
          >
            {isDanger ? "warning" : "lock"}
          </span>
          <h3 className="font-title-md text-title-md text-on-surface font-bold">
            {title}
          </h3>
        </div>

        <p className="font-body-sm text-body-sm text-outline leading-relaxed">
          {description}
        </p>

        <form onSubmit={handleSubmit} className="flex flex-col gap-space-md">
          <div className="flex flex-col gap-1.5">
            <label className="font-label-sm text-label-sm text-on-surface font-semibold flex items-center justify-between">
              <span>Security Code (TOTP) *</span>
              <span className="font-body-xs text-body-xs text-outline font-normal">
                Google Authenticator
              </span>
            </label>
            <input
              type="text"
              inputMode="numeric"
              pattern="[0-9]*"
              maxLength={6}
              autoFocus
              placeholder="000000"
              className="w-full text-center tracking-[0.4em] font-mono font-bold text-lg p-2.5 bg-surface-container-low border border-outline-variant/60 rounded text-on-surface focus:outline-none focus:border-primary"
              value={totpCode}
              onChange={(e) => {
                setTotpCode(e.target.value.replace(/\D/g, "").slice(0, 6));
                setLocalError(null);
              }}
            />
          </div>

          {(localError || error) && (
            <div className="p-2.5 bg-error/10 border border-error/20 rounded flex items-center gap-2 text-error font-body-xs text-body-xs">
              <span className="material-symbols-outlined text-[18px]">
                error
              </span>
              <span>{localError || error}</span>
            </div>
          )}

          <div className="flex items-center justify-end gap-space-sm pt-space-xs">
            <button
              type="button"
              disabled={isLoading}
              onClick={() => {
                setTotpCode("");
                setLocalError(null);
                onCancel();
              }}
              className="px-space-md py-space-xs bg-surface-container hover:bg-surface-container-high rounded text-sm font-semibold text-on-surface transition-colors"
            >
              Cancel
            </button>
            <button
              type="submit"
              disabled={isLoading || totpCode.trim().length !== 6}
              className={`px-space-md py-space-xs rounded text-sm font-bold text-white transition-colors flex items-center gap-1.5 disabled:opacity-50 disabled:cursor-not-allowed ${
                isDanger
                  ? "bg-error hover:bg-error/90"
                  : "bg-primary hover:bg-primary-container"
              }`}
            >
              {isLoading && (
                <span className="inline-block w-4 h-4 border-2 border-white/30 border-t-white rounded-full animate-spin" />
              )}
              <span>{confirmLabel}</span>
            </button>
          </div>
        </form>
      </div>
    </div>
  );
}
