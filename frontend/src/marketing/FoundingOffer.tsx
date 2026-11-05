import { Wrench, Phone, Vote } from "lucide-react";
import type { LucideIcon } from "lucide-react";

interface Benefit {
  Icon: LucideIcon;
  title: string;
  desc: string;
}

const BENEFITS: Benefit[] = [
  {
    Icon: Wrench,
    title: "Free setup, done with you",
    desc: "We configure your test catalog, prices, branches, and staff accounts together on a call.",
  },
  {
    Icon: Phone,
    title: "Direct line to the founder",
    desc: "No support queue. You talk to the person who built LabFlow.",
  },
  {
    Icon: Vote,
    title: "You shape the roadmap",
    desc: "Founding members vote on what gets built next.",
  },
];

export default function FoundingOffer() {
  return (
    <section
      id="offer"
      aria-label="Founding member offer"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div
          className="rounded-2xl p-8 sm:p-12 lg:p-16 text-center"
          style={{
            backgroundColor: "rgba(14, 107, 58, 0.06)",
            border: "1px solid rgba(14, 107, 58, 0.15)",
          }}
        >
          {/* Eyebrow */}
          <p
            className="text-xs font-semibold uppercase tracking-widest mb-4"
            style={{ color: "#0E6B3A" }}
          >
            Founding members
          </p>

          {/* H2 */}
          <h2
            className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl mx-auto"
            style={{ color: "#101613" }}
          >
            Join as a founding member.
          </h2>

          {/* Subhead */}
          <p
            className="text-base sm:text-lg leading-relaxed mb-12 sm:mb-16 max-w-2xl mx-auto"
            style={{ color: "#5b6660" }}
          >
            LabFlow is opening to a small group of labs first. Founding members
            get the closest version of the product — and the loudest voice in
            where it goes.
          </p>

          {/* Three benefit items */}
          <ul
            role="list"
            className="grid grid-cols-1 lg:grid-cols-3 gap-8 sm:gap-10 text-center"
          >
            {BENEFITS.map(({ Icon, title, desc }) => (
              <li key={title} className="flex flex-col items-center">
                <div className="mb-4">
                  <Icon
                    size={22}
                    style={{ color: "#0E6B3A" }}
                    aria-hidden="true"
                  />
                </div>
                <h3
                  className="font-semibold text-base mb-2"
                  style={{ color: "#101613" }}
                >
                  {title}
                </h3>
                <p
                  className="text-sm leading-relaxed max-w-xs"
                  style={{ color: "#5b6660" }}
                >
                  {desc}
                </p>
              </li>
            ))}
          </ul>

          {/* CTA & Risk Reverser */}
          <div className="mt-12 sm:mt-16 flex flex-col items-center">
            <a
              href="#demo"
              className="inline-flex items-center justify-center px-8 py-3.5 rounded-lg text-base font-semibold shadow-sm hover:opacity-95 transition-opacity"
              style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
            >
              Book a Demo
            </a>
            <p className="mt-4 text-xs sm:text-sm" style={{ color: "#5b6660" }}>
              Cancel anytime · Your data exports with you · No long-term
              contract
            </p>
          </div>
        </div>
      </div>
    </section>
  );
}
