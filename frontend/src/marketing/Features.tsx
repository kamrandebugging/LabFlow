import {
  MessageCircle,
  ReceiptText,
  Barcode,
  Flag,
  Fingerprint,
  Handshake,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Feature {
  Icon: LucideIcon;
  title: string;
  sentence1: string;
  sentence2: string;
}

const FEATURES: Feature[] = [
  {
    Icon: MessageCircle,
    title: "Bilingual WhatsApp reports",
    sentence1:
      "Every approved result becomes a bilingual PDF (Urdu + English) delivered to the patient on WhatsApp in one tap.",
    sentence2: "No printing, no reprints, no 'report ready?' phone calls.",
  },
  {
    Icon: ReceiptText,
    title: "Billing that prices itself",
    sentence1:
      "Invoices pull prices straight from your test catalog, with discounts and payments tracked per invoice.",
    sentence2: "The register stops leaking money you already earned.",
  },
  {
    Icon: Barcode,
    title: "Barcoded sample tracking",
    sentence1:
      "Every sample gets a Code128 barcode at collection and a full custody trail to the bench.",
    sentence2: "No more mystery samples.",
  },
  {
    Icon: Flag,
    title: "Results with safety flags",
    sentence1:
      "Out-of-range values are flagged against reference ranges before the pathologist approves.",
    sentence2: "Abnormal results never slip through quietly.",
  },
  {
    Icon: Fingerprint,
    title: "Duplicate-proof patients",
    sentence1:
      "One MRN per patient, with automatic duplicate detection at registration.",
    sentence2: "No more three files for the same person.",
  },
  {
    Icon: Handshake,
    title: "Referral partner settlements",
    sentence1:
      "Track referring doctors and clinics, their revenue share, and monthly settlements in one ledger.",
    sentence2: "Partnerships stay transparent — and paid on time.",
  },
];

export default function Features() {
  return (
    <section
      id="features"
      aria-label="LabFlow features"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          Features
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl"
          style={{ color: "#101613" }}
        >
          Everything the register did — done properly.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-12 max-w-xl"
          style={{ color: "#5b6660" }}
        >
          Six parts of LabFlow your staff will touch every single day.
        </p>

        {/* Grid */}
        <ul
          role="list"
          className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-6"
        >
          {FEATURES.map(({ Icon, title, sentence1, sentence2 }) => (
            <li
              key={title}
              className="rounded-xl p-6 flex flex-col gap-4"
              style={{
                backgroundColor: "#FFFFFF",
                border: "1px solid rgba(16,22,19,0.08)",
              }}
            >
              {/* Icon badge */}
              <div
                className="w-10 h-10 rounded-lg flex items-center justify-center flex-shrink-0"
                style={{ backgroundColor: "rgba(14,107,58,0.10)" }}
              >
                <Icon
                  size={22}
                  style={{ color: "#0E6B3A" }}
                  aria-hidden="true"
                />
              </div>

              {/* Text */}
              <div>
                <p
                  className="font-semibold text-base mb-2"
                  style={{ color: "#101613" }}
                >
                  {title}
                </p>
                <p
                  className="text-sm leading-relaxed"
                  style={{ color: "#5b6660" }}
                >
                  {sentence1} {sentence2}
                </p>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
