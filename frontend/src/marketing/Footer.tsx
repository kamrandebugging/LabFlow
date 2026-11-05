import { useState } from "react";

export default function Footer() {
  const [logoFailed, setLogoFailed] = useState(false);

  return (
    <footer
      aria-label="Footer"
      style={{
        backgroundColor: "#FAF9F6",
        borderTop: "1px solid rgba(16,22,19,0.08)",
      }}
      className="py-12 lg:py-16"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8 flex flex-col items-center text-center">
        {/* LabFlow wordmark + mark */}
        <div className="flex items-center gap-2.5 mb-3">
          {!logoFailed ? (
            <img
              src="/logo.svg"
              alt="LabFlow mark"
              width={28}
              height={28}
              className="w-7 h-7 rounded-md flex-shrink-0"
              onError={() => setLogoFailed(true)}
            />
          ) : null}
          <span className="font-heading font-extrabold text-xl tracking-tight text-[#101613]">
            LabFlow
          </span>
        </div>

        {/* Product description line */}
        <p className="text-sm text-[#5b6660] mb-2">
          Multi-tenant software for diagnostic labs in Pakistan.
        </p>

        {/* Discreet acquisition line */}
        <p className="text-xs text-[#718096] mb-6">
          Interested in acquiring LabFlow? &rarr; Let's talk
        </p>

        {/* Copyright line */}
        <p className="text-xs text-[#A0AEC0]">&copy; 2026 LabFlow</p>
      </div>
    </footer>
  );
}
