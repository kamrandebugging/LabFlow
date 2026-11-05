export default function FinalCta() {
  return (
    <section
      id="demo"
      aria-label="Book a demo"
      style={{ backgroundColor: "#FAF9F6" }}
      className="py-20 lg:py-28"
    >
      <div className="max-w-6xl mx-auto px-4 sm:px-6 lg:px-8">
        <div
          className="rounded-2xl p-8 sm:p-12 lg:p-16 text-center shadow-sm"
          style={{
            backgroundColor: "#0E6B3A",
            color: "#FAF9F6",
          }}
        >
          {/* H2 */}
          <h2
            className="font-heading font-extrabold text-3xl sm:text-4xl lg:text-5xl leading-tight mb-4 max-w-2xl mx-auto"
            style={{ color: "#FAF9F6" }}
          >
            Ready to run your lab on LabFlow?
          </h2>

          {/* Subhead */}
          <p
            className="text-base sm:text-lg leading-relaxed mb-8 sm:mb-10 max-w-xl mx-auto"
            style={{ color: "rgba(250, 249, 246, 0.88)" }}
          >
            Book a demo and see it on your own lab's workflow.
          </p>

          {/* Primary CTA */}
          <div className="flex justify-center">
            <a
              href="#demo"
              className="inline-flex items-center justify-center px-8 py-3.5 rounded-lg text-base font-semibold transition-opacity hover:opacity-95 shadow-sm"
              style={{ backgroundColor: "#FAF9F6", color: "#0E6B3A" }}
            >
              Book a Demo
            </a>
          </div>
        </div>
      </div>
    </section>
  );
}
