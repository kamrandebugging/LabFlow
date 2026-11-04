import Navbar from "./Navbar";

export default function Hero(): JSX.Element {
  return (
    <div
      className="min-h-screen bg-paper text-ink font-body selection:bg-emerald-light selection:text-emerald overflow-x-hidden relative"
      style={{
        backgroundImage:
          "radial-gradient(circle at 18% 26%, rgba(14, 107, 58, 0.05) 0%, rgba(14, 107, 58, 0) 55%)",
      }}
    >
      {/* Sticky Professional Navbar */}
      <Navbar />

      {/* Hero Content Section */}
      <main className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 pt-6 sm:pt-8 lg:pt-10 pb-10 sm:pb-14 lg:pb-16">
        <div className="grid grid-cols-1 lg:grid-cols-12 gap-10 lg:gap-12 items-center">
          {/* Left Column: Eyebrow, H1, Subhead, CTAs, Microcopy */}
          <div className="lg:col-span-6 xl:col-span-5 flex flex-col items-start">
            {/* Eyebrow Badge */}
            <div className="inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-xs sm:text-sm font-semibold tracking-wide bg-emerald-light/60 text-emerald border border-emerald/20 mb-5">
              <span
                className="w-2 h-2 rounded-full bg-gold flex-shrink-0"
                aria-hidden="true"
              />
              <span>Built for diagnostic labs in Pakistan</span>
            </div>

            {/* Main Headline (single H1 on page) */}
            <h1 className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl text-ink tracking-tight leading-[1.15] mb-4">
              Run your diagnostic lab without the paperwork.
            </h1>

            {/* Subhead */}
            <p className="text-base sm:text-lg text-[#2D3748] leading-relaxed mb-6 max-w-xl">
              LabFlow brings patient records, billing, samples, and reports into
              one simple system — designed for how labs in Pakistan actually
              work.
            </p>

            {/* CTAs Row */}
            <div className="flex flex-wrap items-center gap-4 sm:gap-6">
              <a
                href="#demo"
                style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
                className="inline-flex items-center justify-center px-6 py-3 text-base font-semibold text-white bg-[#0E6B3A] hover:bg-[#0A522C] rounded-lg shadow-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#0E6B3A]"
              >
                Book a Demo
              </a>
              <a
                href="#how-it-works"
                className="inline-flex items-center gap-1.5 text-base font-semibold text-[#0E6B3A] hover:text-[#0A522C] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] rounded py-2 px-1"
              >
                <span>See how it works</span>
                <span aria-hidden="true" className="text-lg">
                  &rarr;
                </span>
              </a>
            </div>

            {/* Microcopy under CTAs */}
            <p className="text-xs sm:text-sm text-[#4B5563] mt-3.5 flex items-center gap-1.5">
              <span className="text-[#0E6B3A]" aria-hidden="true">
                ✓
              </span>
              <span>Free 20-minute demo · No commitment</span>
            </p>
          </div>

          {/* Right Column: Owner Dashboard Interface Mockup inside Browser Frame */}
          <div className="lg:col-span-6 xl:col-span-7 w-full">
            <div className="rounded-xl border border-slate-200/90 bg-white shadow-xl shadow-slate-900/5 overflow-hidden transition-all duration-300 hover:shadow-2xl hover:shadow-slate-900/10">
              {/* Browser Window Chrome */}
              <div
                className="px-4 py-3 bg-[#F4F4F1] border-b border-slate-200/80 flex items-center gap-2 select-none"
                aria-hidden="true"
              >
                <div className="flex items-center gap-1.5">
                  <div className="w-2.5 h-2.5 rounded-full bg-[#E2E8F0]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#E2E8F0]" />
                  <div className="w-2.5 h-2.5 rounded-full bg-[#E2E8F0]" />
                </div>
                <div className="ml-2 flex-1 max-w-xs bg-white/80 border border-slate-200/60 rounded px-2.5 py-0.5 text-[11px] text-[#718096] truncate">
                  app.labflow.pk/dashboard
                </div>
              </div>

              {/* Product Visual */}
              <div className="relative bg-slate-100">
                <img
                  src="/hero-dashboard.webp"
                  alt="LabFlow owner dashboard interface"
                  width={2560}
                  height={2048}
                  className="w-full h-auto block"
                  loading="eager"
                />
              </div>
            </div>
          </div>
        </div>
      </main>
    </div>
  );
}
