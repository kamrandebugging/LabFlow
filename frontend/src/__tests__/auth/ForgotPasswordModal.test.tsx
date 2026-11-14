import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { ForgotPasswordModal } from "@/features/auth/ForgotPasswordModal";

describe("ForgotPasswordModal", () => {
  const writeText = vi.fn().mockResolvedValue(undefined);

  beforeEach(() => {
    writeText.mockClear();
    Object.defineProperty(navigator, "clipboard", {
      value: { writeText },
      configurable: true,
    });
  });

  it("offers exactly the two chooser options", () => {
    render(
      <ForgotPasswordModal
        tenantName="Abubakar Diagnostic Lab"
        slug="abubakarlab"
        email="owner@lab.pk"
        onClose={vi.fn()}
      />,
    );

    expect(
      screen.getByRole("button", { name: "I'm the Lab Owner" }),
    ).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "I'm Staff" }),
    ).toBeInTheDocument();
  });

  it("shows the owner contact card with dynamic tenant data in the WhatsApp link", async () => {
    const user = userEvent.setup();
    render(
      <ForgotPasswordModal
        tenantName="Abubakar Diagnostic Lab"
        slug="abubakarlab"
        email="owner@lab.pk"
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "I'm the Lab Owner" }));

    expect(screen.getByText("Contact LabFlow Support")).toBeInTheDocument();
    expect(
      screen.getByText("Muhammad Kamran — Platform Owner"),
    ).toBeInTheDocument();
    expect(screen.getByText("kamrandebugging@gmail.com")).toBeInTheDocument();
    expect(screen.getByText("+92 320 6744652")).toBeInTheDocument();

    const chat = screen.getByRole("link", { name: "Chat" });
    const href = chat.getAttribute("href") ?? "";
    expect(href.startsWith("https://wa.me/923206744652?text=")).toBe(true);
    expect(decodeURIComponent(href)).toContain("Abubakar Diagnostic Lab");
    expect(decodeURIComponent(href)).toContain("abubakarlab");
    expect(decodeURIComponent(href)).toContain("owner@lab.pk");

    await user.click(screen.getByRole("button", { name: "Copy" }));
    expect(
      await screen.findByRole("button", { name: "Copied" }),
    ).toBeInTheDocument();
  });

  it("shows the staff request form without owner contact details", async () => {
    const user = userEvent.setup();
    const fetchMock = vi
      .spyOn(globalThis, "fetch")
      .mockResolvedValue(new Response("{}", { status: 202 }));
    render(
      <ForgotPasswordModal
        tenantName="Abubakar Diagnostic Lab"
        slug="abubakarlab"
        email="staff@lab.pk"
        onClose={vi.fn()}
      />,
    );

    await user.click(screen.getByRole("button", { name: "I'm Staff" }));

    expect(
      screen.getByText(/only they can reset your password/i),
    ).toBeInTheDocument();
    expect(
      screen.queryByText("kamrandebugging@gmail.com"),
    ).not.toBeInTheDocument();
    expect(screen.queryByText("+92 320 6744652")).not.toBeInTheDocument();

    // The request is addressed to the Lab Owner and the email is prefilled.
    expect(screen.getByLabelText("Login email")).toHaveValue("staff@lab.pk");
    await user.click(
      screen.getByRole("button", { name: "Send request to Lab Owner" }),
    );

    expect(fetchMock).toHaveBeenCalledWith(
      "/api/v1/auth/password-reset/staff-request",
      expect.objectContaining({
        method: "POST",
        body: JSON.stringify({ email: "staff@lab.pk", display_name: "" }),
      }),
    );
    expect(
      await screen.findByText(/Request sent to your Lab Owner/i),
    ).toBeInTheDocument();
    fetchMock.mockRestore();
  });
});
