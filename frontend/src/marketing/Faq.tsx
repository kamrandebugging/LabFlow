import { useState } from "react";
import { Plus } from "lucide-react";

interface FaqItem {
  question: string;
  answer: string;
}

const FAQS: FaqItem[] = [
  {
    question: "Do I need to install anything?",
    answer:
      "No. LabFlow runs in your browser — nothing to install, and no server to maintain on your side.",
  },
  {
    question: "My staff isn't technical. Can they use it?",
    answer:
      "Yes. Each role sees only its own simple screen — receptionists see reception, technicians see their worklist, nothing more.",
  },
  {
    question: "What happens to my existing patient data?",
    answer:
      "We migrate your registers and Excel sheets with you during the free setup.",
  },
  {
    question: "Can patients get reports without visiting the lab?",
    answer:
      "Yes. Approved reports go out as bilingual PDFs on WhatsApp, or through a secure link that expires automatically after 7 days.",
  },
  {
    question: "What if I cancel?",
    answer:
      "You can cancel anytime. Your data exports with you — patient records, invoices, everything.",
  },
  {
    question: "Is my lab's data mixed with other labs'?",
    answer:
      "No. Every lab runs in its own isolated database schema — your patients never touch another lab's data.",
  },
];

export default function Faq() {
  const [openIndex, setOpenIndex] = useState<number | null>(0);

  const toggle = (index: number) => {
    setOpenIndex((current) => (current === index ? null : index));
  };

  return (
    <section
      id="faq"
      aria-label="Frequently asked questions"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-3xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          FAQ
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4"
          style={{ color: "#101613" }}
        >
          Questions, answered.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-12 sm:mb-16"
          style={{ color: "#5b6660" }}
        >
          The ones every lab owner asks on the demo call.
        </p>

        {/* Accordion list */}
        <div
          className="border-t"
          style={{ borderColor: "rgba(16,22,19,0.08)" }}
        >
          {FAQS.map((item, index) => {
            const isOpen = openIndex === index;
            const questionId = `faq-question-${index}`;
            const answerId = `faq-answer-${index}`;

            return (
              <div
                key={item.question}
                className="border-b"
                style={{ borderColor: "rgba(16,22,19,0.08)" }}
              >
                <button
                  type="button"
                  id={questionId}
                  aria-expanded={isOpen}
                  aria-controls={answerId}
                  onClick={() => toggle(index)}
                  className="w-full py-6 flex items-center justify-between text-left gap-4 focus:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] focus-visible:ring-offset-2 rounded-sm"
                >
                  <span
                    className="font-semibold text-base sm:text-lg"
                    style={{ color: "#101613" }}
                  >
                    {item.question}
                  </span>
                  <span
                    className="flex-shrink-0 transition-transform duration-200"
                    style={{
                      transform: isOpen ? "rotate(45deg)" : "rotate(0deg)",
                    }}
                    aria-hidden="true"
                  >
                    <Plus size={20} style={{ color: "#0E6B3A" }} />
                  </span>
                </button>

                <div
                  id={answerId}
                  role="region"
                  aria-labelledby={questionId}
                  className={`grid transition-[grid-template-rows] duration-200 ease-out ${
                    isOpen ? "grid-rows-[1fr]" : "grid-rows-[0fr]"
                  }`}
                >
                  <div className="overflow-hidden">
                    <p
                      className="pb-6 text-sm sm:text-base leading-relaxed"
                      style={{ color: "#5b6660" }}
                    >
                      {item.answer}
                    </p>
                  </div>
                </div>
              </div>
            );
          })}
        </div>
      </div>
    </section>
  );
}
