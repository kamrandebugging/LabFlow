import { describe, it, expect } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import Hero from "../Hero";
import Navbar from "../Navbar";
import TrustStrip from "../TrustStrip";

describe("Marketing Hero, Navbar, and TrustStrip", () => {
  it("renders Navbar with all desktop links, sign in, and primary CTA", () => {
    render(<Navbar />);

    expect(screen.getByLabelText("LabFlow Home")).toBeInTheDocument();
    expect(screen.getByText("LabFlow")).toBeInTheDocument();

    expect(screen.getByText("Features")).toHaveAttribute("href", "#features");
    expect(screen.getByText("How it works")).toHaveAttribute(
      "href",
      "#how-it-works",
    );
    expect(screen.getByText("Pricing")).toHaveAttribute("href", "#pricing");
    expect(screen.getByText("FAQ")).toHaveAttribute("href", "#faq");

    expect(screen.getByText("Sign in")).toHaveAttribute("href", "/login");
    const bookDemoBtn = screen.getByRole("link", { name: "Book a Demo" });
    expect(bookDemoBtn).toHaveAttribute("href", "#demo");
    expect(bookDemoBtn).toHaveStyle({
      backgroundColor: "#0E6B3A",
      color: "#FFFFFF",
    });
  });

  it("toggles mobile menu and closes on link click", () => {
    render(<Navbar />);

    const menuToggle = screen.getByLabelText("Open menu");
    expect(menuToggle).toBeInTheDocument();

    fireEvent.click(menuToggle);
    expect(screen.getByLabelText("Close menu")).toBeInTheDocument();

    const mobileFeatures = screen.getAllByText("Features")[1];
    if (mobileFeatures) {
      fireEvent.click(mobileFeatures);
    }
    expect(screen.queryByLabelText("Close menu")).not.toBeInTheDocument();
  });

  it("renders Hero with exact content, primary CTA, secondary CTA, and product visual", () => {
    render(<Hero />);

    // Eyebrow
    expect(
      screen.getByText("Built for diagnostic labs in Pakistan"),
    ).toBeInTheDocument();

    // H1
    const h1 = screen.getByRole("heading", { level: 1 });
    expect(h1).toHaveTextContent(
      "Run your diagnostic lab without the paperwork.",
    );

    // Subhead
    expect(
      screen.getByText(
        "LabFlow brings patient records, billing, samples, and reports into one simple system — designed for how labs in Pakistan actually work.",
      ),
    ).toBeInTheDocument();

    // Primary CTA in hero
    const ctas = screen.getAllByRole("link", { name: "Book a Demo" });
    expect(ctas.length).toBeGreaterThanOrEqual(2); // In navbar and in hero
    const heroPrimary = ctas[1];
    expect(heroPrimary).toHaveAttribute("href", "#demo");
    expect(heroPrimary).toHaveStyle({
      backgroundColor: "#0E6B3A",
      color: "#FFFFFF",
    });

    // Secondary CTA in hero
    const secondary = screen.getByRole("link", { name: /See how it works/i });
    expect(secondary).toHaveAttribute("href", "#how-it-works");

    // Microcopy
    expect(
      screen.getByText("Free 20-minute demo · No commitment"),
    ).toBeInTheDocument();

    // Product visual
    const visual = screen.getByAltText("LabFlow owner dashboard interface");
    expect(visual).toHaveAttribute("src", "/hero-dashboard.webp");
  });

  it("renders TrustStrip with exact 4 items and correct semantic section", () => {
    render(<TrustStrip />);

    const section = screen.getByLabelText("Why labs trust LabFlow");
    expect(section).toBeInTheDocument();

    expect(screen.getByText("Urdu + English")).toBeInTheDocument();
    expect(screen.getByText("Bilingual patient reports")).toBeInTheDocument();

    expect(screen.getByText("Role-based access")).toBeInTheDocument();
    expect(
      screen.getByText("Owner, manager, receptionist, technician, pathologist"),
    ).toBeInTheDocument();

    expect(screen.getByText("Complete audit trail")).toBeInTheDocument();
    expect(
      screen.getByText("Every action logged, nothing silent"),
    ).toBeInTheDocument();

    expect(screen.getByText("WhatsApp delivery")).toBeInTheDocument();
    expect(
      screen.getByText("Send reports to patients in one tap"),
    ).toBeInTheDocument();
  });
});
