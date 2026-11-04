import { useState, useEffect } from "react";

const NAV_LINKS = [
  { label: "Features", href: "#features" },
  { label: "How it works", href: "#how-it-works" },
  { label: "Pricing", href: "#pricing" },
  { label: "FAQ", href: "#faq" },
] as const;

export default function Navbar(): JSX.Element {
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false);
  const [logoFailed, setLogoFailed] = useState(false);

  useEffect(() => {
    if (!mobileMenuOpen) return;
    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setMobileMenuOpen(false);
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [mobileMenuOpen]);

  return (
    <header className="sticky top-0 z-50 w-full bg-[#FAF9F6]/90 backdrop-blur-md border-b border-[#0E6B3A]/10">
      <nav
        aria-label="Main Navigation"
        className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 h-18 sm:h-20 flex items-center justify-between"
      >
        {/* Left: Logo Mark + Wordmark */}
        <a
          href="/"
          className="flex items-center gap-3 group focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] rounded-lg p-0.5"
          aria-label="LabFlow Home"
        >
          {!logoFailed ? (
            <img
              src="/logo.svg"
              alt="LabFlow mark"
              width={36}
              height={36}
              className="w-9 h-9 rounded-lg flex-shrink-0"
              onError={() => setLogoFailed(true)}
            />
          ) : null}
          <span className="font-heading font-extrabold text-2xl tracking-tight text-[#101613]">
            LabFlow
          </span>
        </a>

        {/* Center: Desktop Navigation Links (>=1024px) */}
        <div className="hidden lg:flex items-center gap-8">
          {NAV_LINKS.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-[#101613] hover:text-[#0E6B3A] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] rounded px-1 py-0.5"
            >
              {link.label}
            </a>
          ))}
        </div>

        {/* Right: Desktop "Sign in" + Primary CTA (>=1024px) */}
        <div className="hidden lg:flex items-center gap-6">
          <a
            href="/login"
            className="text-sm font-medium text-[#101613] hover:text-[#0E6B3A] transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] rounded px-2 py-1"
          >
            Sign in
          </a>
          <a
            href="#demo"
            style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
            className="inline-flex items-center justify-center px-4 py-2 text-sm font-semibold text-white bg-[#0E6B3A] hover:bg-[#0A522C] rounded-lg transition-colors shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-offset-2 focus-visible:ring-[#0E6B3A]"
          >
            Book a Demo
          </a>
        </div>

        {/* Mobile Hamburger Button (<1024px) */}
        <div className="flex items-center lg:hidden">
          <button
            type="button"
            onClick={() => setMobileMenuOpen((prev) => !prev)}
            className="p-2 text-[#101613] hover:text-[#0E6B3A] focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[#0E6B3A] rounded-lg transition-colors"
            aria-expanded={mobileMenuOpen}
            aria-controls="mobile-nav-menu"
            aria-label={mobileMenuOpen ? "Close menu" : "Open menu"}
          >
            {mobileMenuOpen ? (
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M6 18L18 6M6 6l12 12"
                />
              </svg>
            ) : (
              <svg
                className="w-6 h-6"
                fill="none"
                viewBox="0 0 24 24"
                strokeWidth={2}
                stroke="currentColor"
                aria-hidden="true"
              >
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  d="M3.75 6.75h16.5M3.75 12h16.5m-16.5 5.25h16.5"
                />
              </svg>
            )}
          </button>
        </div>
      </nav>

      {/* Mobile Dropdown Panel (<1024px) */}
      {mobileMenuOpen && (
        <div
          id="mobile-nav-menu"
          className="lg:hidden border-t border-[#0E6B3A]/10 bg-[#FAF9F6] px-4 pt-4 pb-6 shadow-xl space-y-4"
        >
          <div className="flex flex-col space-y-1">
            {NAV_LINKS.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setMobileMenuOpen(false)}
                className="text-base font-medium text-[#101613] hover:text-[#0E6B3A] hover:bg-emerald-light/40 transition-colors py-2 px-3 rounded-lg"
              >
                {link.label}
              </a>
            ))}
          </div>
          <div className="pt-3 border-t border-[#0E6B3A]/10 flex flex-col space-y-3">
            <a
              href="/login"
              onClick={() => setMobileMenuOpen(false)}
              className="text-base font-medium text-[#101613] hover:text-[#0E6B3A] hover:bg-emerald-light/40 transition-colors py-2 px-3 rounded-lg"
            >
              Sign in
            </a>
            <a
              href="#demo"
              onClick={() => setMobileMenuOpen(false)}
              style={{ backgroundColor: "#0E6B3A", color: "#FFFFFF" }}
              className="inline-flex items-center justify-center px-4 py-2.5 text-base font-semibold text-white bg-[#0E6B3A] hover:bg-[#0A522C] rounded-lg text-center transition-colors shadow-sm"
            >
              Book a Demo
            </a>
          </div>
        </div>
      )}
    </header>
  );
}
