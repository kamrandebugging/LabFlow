import { useEffect, useRef, useState } from "react";
import { UserPlus, FlaskConical, Send } from "lucide-react";

const STEPS = [
  {
    num: "01",
    Icon: UserPlus,
    title: "Register and bill",
    desc: "Add the patient once — duplicates are caught automatically. The invoice prices itself from your test catalog.",
  },
  {
    num: "02",
    Icon: FlaskConical,
    title: "Collect and test",
    desc: "Samples are barcoded at collection and tracked to the bench. Technicians see exactly what's waiting, and out-of-range results get flagged.",
  },
  {
    num: "03",
    Icon: Send,
    title: "Approve and deliver",
    desc: "The pathologist approves with one click. Patients receive a bilingual PDF report on WhatsApp — no phone calls.",
  },
] as const;

export default function HowItWorks() {
  const sectionRef = useRef<HTMLElement>(null);
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const el = sectionRef.current;
    if (!el) return;
    const obs = new IntersectionObserver(
      (entries) => { if (entries[0]?.isIntersecting) { setVisible(true); obs.disconnect(); } },
      { threshold: 0.15 }
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, []);

  return (
    <section
      id="how-it-works"
      ref={sectionRef}
      aria-label="How LabFlow works"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          How it works
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl"
          style={{ color: "#101613" }}
        >
          From reception to report, in three steps.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-16 max-w-xl"
          style={{ color: "#5b6660" }}
        >
          The daily flow your staff already knows — without the paper.
        </p>

        {/* Steps */}
        <ol className="relative list-none p-0 m-0 flex flex-col lg:flex-row lg:gap-0 gap-0">
          {/* Desktop connector line — behind badges */}
          <li className="hidden lg:block absolute top-[22px] left-[calc(16.666%+16px)] right-[calc(16.666%+16px)] h-px pointer-events-none" style={{ backgroundColor: "rgba(14,107,58,0.18)", zIndex: 0 }} aria-hidden="true" />

          {STEPS.map(({ num, Icon, title, desc }, i) => (
            <li
              key={num}
              className="relative flex lg:flex-col lg:flex-1 lg:items-center lg:text-center"
              style={{
                opacity: visible ? 1 : 0,
                transform: visible ? "translateY(0)" : "translateY(24px)",
                transition: `opacity 0.5s ease ${i * 0.12}s, transform 0.5s ease ${i * 0.12}s`,
              }}
            >
              {/* Mobile vertical connector */}
              {i < STEPS.length - 1 && (
                <span
                  className="lg:hidden absolute left-[22px] top-[44px] bottom-0 w-px"
                  style={{ backgroundColor: "rgba(14,107,58,0.18)" }}
                  aria-hidden="true"
                />
              )}

              {/* Badge + content row (mobile) / column (desktop) */}
              <div className="flex lg:flex-col lg:items-center gap-5 lg:gap-4 pb-10 lg:pb-0 lg:px-6 w-full">
                {/* Step badge */}
                <div
                  className="relative flex-shrink-0 w-11 h-11 rounded-full flex items-center justify-center font-heading font-extrabold text-sm"
                  style={{
                    backgroundColor: "#FAF9F6",
                    border: "2px solid #0E6B3A",
                    color: "#0E6B3A",
                    zIndex: 1,
                  }}
                >
                  {num}
                </div>

                {/* Text block */}
                <div className="lg:mt-6 flex-1">
                  {/* Icon — hidden on mobile since badge gives sequence; shown on desktop */}
                  <div className="hidden lg:flex justify-center mb-4">
                    <Icon size={22} style={{ color: "#0E6B3A" }} aria-hidden="true" />
                  </div>
                  {/* Mobile icon inline */}
                  <div className="flex lg:hidden items-center gap-2 mb-1">
                    <Icon size={18} style={{ color: "#0E6B3A" }} aria-hidden="true" />
                  </div>
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
                    {desc}
                  </p>
                </div>
              </div>
            </li>
          ))}
        </ol>
      </div>
    </section>
  );
}
