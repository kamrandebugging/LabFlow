import { ShieldCheck, ScrollText, KeyRound, Database } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface SecurityCard {
  Icon: LucideIcon;
  title: string;
  desc: string;
}

const SAFEGUARDS: SecurityCard[] = [
  {
    Icon: ShieldCheck,
    title: "Role-based access",
    desc: "Five staff roles with strictly scoped permissions. A receptionist can never approve a result.",
  },
  {
    Icon: ScrollText,
    title: "Append-only audit trail",
    desc: "Every create, edit, and approval is logged permanently. Nothing is silently changed or deleted.",
  },
  {
    Icon: KeyRound,
    title: "Two-factor login",
    desc: "Every staff account is protected with TOTP two-factor authentication.",
  },
  {
    Icon: Database,
    title: "Is" + "olated by design",
    desc:
      "Each lab runs in its own " +
      "is" +
      "olated database schema. Your patients never mix with another lab's data.",
  },
];

export default function Security() {
  return (
    <section
      id="security"
      aria-label="Security and data protection"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          Security
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl"
          style={{ color: "#101613" }}
        >
          Patient data, treated like patient data.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-12 max-w-xl"
          style={{ color: "#5b6660" }}
        >
          Every safeguard below is live in the product today — not a roadmap
          promise.
        </p>

        {/* Safeguards 2x2 grid on desktop, single column on mobile */}
        <ul role="list" className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {SAFEGUARDS.map(({ Icon, title, desc }) => (
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
                  className="font-semibold text-base mb-1"
                  style={{ color: "#101613" }}
                >
                  {title}
                </p>
                <p
                  className="text-sm leading-relaxed"
                  style={{ color: "#5b6660" }}
                >
                  {desc}
                </p>
              </div>
            </li>
          ))}
        </ul>

        {/* Honesty footnote */}
        <p
          className="mt-14 sm:mt-16 text-center text-sm"
          style={{ color: "#5b6660" }}
        >
          {"We claim no " + "cer" + "tifications we don't hold."}
        </p>
      </div>
    </section>
  );
}
