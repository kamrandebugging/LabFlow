import { useState } from "react";
import { Check } from "lucide-react";

interface Plan {
  title: string;
  monthlyPrice: string;
  annualPrice: string;
  tagline: string;
  popular?: boolean;
  features: string[];
}

const PLANS: Plan[] = [
  {
    title: "Starter",
    monthlyPrice: "PKR 2,999",
    annualPrice: "PKR 29,990",
    tagline: "For a single lab leaving paper behind.",
    features: [
      "1 branch",
      "5 staff logins (all roles)",
      "Patient records, billing & invoices",
      "Barcode sample tracking",
      "Bilingual WhatsApp reports",
      "WhatsApp support",
    ],
  },
  {
    title: "Growth",
    monthlyPrice: "PKR 5,999",
    annualPrice: "PKR 59,990",
    tagline: "For growing labs with referrals.",
    popular: true,
    features: [
      "3 branches",
      "Unlimited staff logins",
      "Everything in Starter",
      "Referral partner & commission ledgers",
      "Monthly settlements",
      "Priority WhatsApp support",
    ],
  },
  {
    title: "Scale",
    monthlyPrice: "PKR 9,999",
    annualPrice: "PKR 99,990",
    tagline: "For lab chains.",
    features: [
      "Unlimited branches",
      "Everything in Growth",
      "Free white-glove setup",
      "Direct founder support",
    ],
  },
];

export default function Pricing() {
  const [billingPeriod, setBillingPeriod] = useState<"monthly" | "annual">(
    "monthly",
  );

  return (
    <section
      id="pricing"
      aria-label="Pricing plans"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        {/* Eyebrow */}
        <p
          className="text-xs font-semibold uppercase tracking-widest mb-4"
          style={{ color: "#0E6B3A" }}
        >
          Pricing
        </p>

        {/* H2 */}
        <h2
          className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl"
          style={{ color: "#101613" }}
        >
          Simple pricing, in rupees.
        </h2>

        {/* Subhead */}
        <p
          className="text-base sm:text-lg leading-relaxed mb-8 max-w-2xl"
          style={{ color: "#5b6660" }}
        >
          Monthly or yearly — or own it forever. Every plan in PKR. No hidden
          fees.
        </p>

        {/* Monthly / Annual billing toggle */}
        <div className="flex justify-center mb-10 sm:mb-12">
          <div
            role="group"
            aria-label="Billing period"
            className="inline-flex items-center p-1 rounded-full shadow-sm"
            style={{
              backgroundColor: "#FFFFFF",
              border: "1px solid rgba(16,22,19,0.08)",
            }}
          >
            <button
              type="button"
              aria-pressed={billingPeriod === "monthly"}
              onClick={() => setBillingPeriod("monthly")}
              className="px-5 py-2 rounded-full text-sm font-semibold transition-all"
              style={{
                backgroundColor:
                  billingPeriod === "monthly" ? "#0E6B3A" : "transparent",
                color: billingPeriod === "monthly" ? "#FFFFFF" : "#101613",
              }}
            >
              Monthly
            </button>
            <button
              type="button"
              aria-pressed={billingPeriod === "annual"}
              onClick={() => setBillingPeriod("annual")}
              className="inline-flex items-center gap-2 px-5 py-2 rounded-full text-sm font-semibold transition-all"
              style={{
                backgroundColor:
                  billingPeriod === "annual" ? "#0E6B3A" : "transparent",
                color: billingPeriod === "annual" ? "#FFFFFF" : "#101613",
              }}
            >
              <span>Annual</span>
              <span
                className="text-xs px-2 py-0.5 rounded-full font-medium"
                style={{
                  backgroundColor:
                    billingPeriod === "annual"
                      ? "rgba(255,255,255,0.22)"
                      : "rgba(14,107,58,0.10)",
                  color: billingPeriod === "annual" ? "#FFFFFF" : "#0E6B3A",
                }}
              >
                2 months free
              </span>
            </button>
          </div>
        </div>

        {/* Three cards */}
        <div className="grid grid-cols-1 lg:grid-cols-3 gap-8 items-stretch">
          {PLANS.map((plan) => {
            const price =
              billingPeriod === "monthly"
                ? plan.monthlyPrice
                : plan.annualPrice;
            const period = billingPeriod === "monthly" ? "/month" : "/year";

            return (
              <div
                key={plan.title}
                className={`rounded-xl p-8 flex flex-col justify-between relative ${
                  plan.popular ? "shadow-sm" : ""
                }`}
                style={{
                  backgroundColor: "#FFFFFF",
                  border: plan.popular
                    ? "2px solid #0E6B3A"
                    : "1px solid rgba(16,22,19,0.08)",
                }}
              >
                {plan.popular && (
                  <div
                    className="absolute -top-3.5 left-1/2 -translate-x-1/2 px-3 py-1 rounded-full text-xs font-semibold tracking-wide whitespace-nowrap shadow-sm"
                    style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
                  >
                    Most popular
                  </div>
                )}

                <div>
                  <h3
                    className="font-semibold text-lg mb-2"
                    style={{ color: "#101613" }}
                  >
                    {plan.title}
                  </h3>
                  <div className="flex items-baseline gap-1.5 mb-2">
                    <span
                      className="font-heading font-extrabold text-4xl transition-opacity duration-150"
                      style={{ color: "#101613" }}
                    >
                      {price}
                    </span>
                    <span
                      className="text-sm font-normal"
                      style={{ color: "#5b6660" }}
                    >
                      {period}
                    </span>
                  </div>
                  <p className="text-sm mb-6" style={{ color: "#5b6660" }}>
                    {plan.tagline}
                  </p>

                  {/* Features list */}
                  <ul role="list" className="space-y-3 mb-8">
                    {plan.features.map((feature) => (
                      <li key={feature} className="flex items-start gap-2.5">
                        <div className="flex-shrink-0 mt-0.5">
                          <Check
                            size={16}
                            style={{ color: "#0E6B3A" }}
                            aria-hidden="true"
                          />
                        </div>
                        <span className="text-sm" style={{ color: "#5b6660" }}>
                          {feature}
                        </span>
                      </li>
                    ))}
                  </ul>
                </div>

                {/* Card CTA */}
                <div className="mt-auto pt-4">
                  <a
                    href="#demo"
                    className="w-full inline-flex items-center justify-center px-6 py-3 rounded-lg text-sm font-semibold transition-opacity hover:opacity-95"
                    style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
                  >
                    Book a Demo
                  </a>
                </div>
              </div>
            );
          })}
        </div>

        {/* Lifetime card */}
        <div
          className="mt-12 rounded-xl p-8 flex flex-col lg:flex-row lg:items-center lg:justify-between gap-8"
          style={{
            border: "1px solid rgba(16,22,19,0.08)",
            backgroundColor: "#FFFFFF",
          }}
        >
          {/* Left: Title + Bullets */}
          <div className="text-center lg:text-left">
            <h3
              className="font-semibold text-xl mb-4"
              style={{ color: "#101613" }}
            >
              Prefer to own it forever?
            </h3>
            <ul role="list" className="space-y-2.5 inline-block text-left">
              <li className="flex items-start gap-2.5">
                <div className="flex-shrink-0 mt-0.5">
                  <Check
                    size={16}
                    style={{ color: "#0E6B3A" }}
                    aria-hidden="true"
                  />
                </div>
                <span className="text-sm" style={{ color: "#5b6660" }}>
                  One-time payment — no monthly bills
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <div className="flex-shrink-0 mt-0.5">
                  <Check
                    size={16}
                    style={{ color: "#0E6B3A" }}
                    aria-hidden="true"
                  />
                </div>
                <span className="text-sm" style={{ color: "#5b6660" }}>
                  All Growth features, forever
                </span>
              </li>
              <li className="flex items-start gap-2.5">
                <div className="flex-shrink-0 mt-0.5">
                  <Check
                    size={16}
                    style={{ color: "#0E6B3A" }}
                    aria-hidden="true"
                  />
                </div>
                <span className="text-sm" style={{ color: "#5b6660" }}>
                  15–20% yearly maintenance after year one (support + updates)
                </span>
              </li>
            </ul>
          </div>

          {/* Right: Prices + CTA */}
          <div className="flex flex-col items-center lg:items-end gap-5 shrink-0">
            <div className="flex items-center justify-center gap-6 sm:gap-8">
              <div className="text-center lg:text-right">
                <p
                  className="text-xs font-medium uppercase tracking-wider mb-0.5"
                  style={{ color: "#5b6660" }}
                >
                  Single-branch
                </p>
                <p
                  className="font-heading font-extrabold text-2xl"
                  style={{ color: "#101613" }}
                >
                  PKR 71,999
                </p>
                <p className="text-xs" style={{ color: "#5b6660" }}>
                  one-time
                </p>
              </div>

              <div
                className="h-10 w-px"
                style={{ backgroundColor: "rgba(16,22,19,0.08)" }}
                aria-hidden="true"
              />

              <div className="text-center lg:text-right">
                <p
                  className="text-xs font-medium uppercase tracking-wider mb-0.5"
                  style={{ color: "#5b6660" }}
                >
                  Multi-branch
                </p>
                <p
                  className="font-heading font-extrabold text-2xl"
                  style={{ color: "#101613" }}
                >
                  PKR 143,999
                </p>
                <p className="text-xs" style={{ color: "#5b6660" }}>
                  one-time
                </p>
              </div>
            </div>

            <a
              href="#demo"
              className="w-full sm:w-auto inline-flex items-center justify-center px-8 py-3 rounded-lg text-sm font-semibold transition-opacity hover:opacity-95 text-center"
              style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
            >
              Book a Demo
            </a>
          </div>
        </div>

        {/* Payment line */}
        <p
          className="mt-6 text-center text-xs sm:text-sm"
          style={{ color: "#5b6660" }}
        >
          Pay via bank transfer, Easypaisa, or JazzCash. No credit card
          required.
        </p>
      </div>
    </section>
  );
}
