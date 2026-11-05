import { FileSearch, ReceiptText, PhoneCall, NotebookPen } from "lucide-react";

const PAIN_CARDS = [
  {
    Icon: FileSearch,
    title: "Lost reports",
    desc: "Paper slips go missing between reception and the patient. Every reprint costs time — and a little trust.",
  },
  {
    Icon: ReceiptText,
    title: "Billing that leaks",
    desc: "Handwritten invoices, mental-math discounts, no record of who paid what. The money is there; the record isn't.",
  },
  {
    Icon: PhoneCall,
    title: "Results by phone call",
    desc: "Patients call all day asking 'report ready?'. Your staff stop working to answer.",
  },
  {
    Icon: NotebookPen,
    title: "No full picture",
    desc: "Samples in one register, payments in another, approvals in someone's head. The owner finds out at month-end.",
  },
] as const;

export default function Problem() {
  return (
    <section
      aria-label="The problem with paper-based labs"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          The problem
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl"
          style={{ color: "#101613" }}
        >
          Your lab runs on paper, phone calls, and memory.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-12 max-w-2xl"
          style={{ color: "#5b6660" }}
        >
          Most diagnostic labs in Pakistan still run on registers and WhatsApp
          threads. It works — until the day it doesn't.
        </p>

        {/* Pain cards grid */}
        <ul role="list" className="grid grid-cols-1 lg:grid-cols-2 gap-6">
          {PAIN_CARDS.map(({ Icon, title, desc }) => (
            <li
              key={title}
              className="rounded-xl p-6"
              style={{
                backgroundColor: "#FFFFFF",
                border: "1px solid rgba(16,22,19,0.08)",
              }}
            >
              <div className="flex items-start gap-4">
                <div className="flex-shrink-0 mt-0.5">
                  <Icon
                    size={22}
                    style={{ color: "#B54434" }}
                    aria-hidden="true"
                  />
                </div>
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
              </div>
            </li>
          ))}
        </ul>

        {/* Bridge line */}
        <p
          className="mt-12 text-center text-lg sm:text-xl font-semibold"
          style={{ color: "#0E6B3A" }}
        >
          LabFlow was built to end exactly this.
        </p>
      </div>
    </section>
  );
}
