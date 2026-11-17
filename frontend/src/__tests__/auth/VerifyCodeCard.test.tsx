import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import {
  act,
  fireEvent,
  render,
  screen,
  waitFor,
} from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { VerifyCodeCard } from "@/components/ui/VerifyCodeCard";
import type { VerifyCodeCardProps } from "@/components/ui/VerifyCodeCard";
import { ThemeProvider } from "@/theme/ThemeProvider";

function renderCard(overrides: Partial<VerifyCodeCardProps> = {}) {
  const props: VerifyCodeCardProps = {
    mode: "totp",
    error: null,
    verifying: false,
    onSubmit: vi.fn().mockResolvedValue(undefined),
    onSuccess: vi.fn(),
    onSecondary: vi.fn(),
    secondaryLabel: "Use backup code",
    ...overrides,
  };

  render(
    <ThemeProvider>
      <VerifyCodeCard {...props} />
    </ThemeProvider>,
  );

  return props;
}

describe("VerifyCodeCard", () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.useRealTimers();
  });

  it("renders the locked copy, six cells and the secondary action", () => {
    renderCard();

    expect(screen.getByText("Verify it's you")).toBeInTheDocument();
    expect(
      screen.getByText("· open your authenticator app"),
    ).toBeInTheDocument();
    expect(screen.getByText("Security check")).toBeInTheDocument();
    expect(screen.getByText(/Code expires in 0:\d\d/)).toBeInTheDocument();
    for (let index = 1; index <= 6; index += 1) {
      expect(screen.getByLabelText(`Digit ${index}`)).toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: "Use backup code" }),
    ).toBeInTheDocument();
  });

  it("shows the masked contact in email mode", () => {
    renderCard({ mode: "email", maskedContact: "a•••@lab.pk" });
    expect(screen.getByText("· code sent to a•••@lab.pk")).toBeInTheDocument();
  });

  it("auto-advances and accepts digits only", async () => {
    const user = userEvent.setup();
    renderCard();

    const first = screen.getByLabelText("Digit 1");
    const second = screen.getByLabelText("Digit 2");

    await user.type(first, "8");
    expect(first).toHaveValue("8");
    expect(second).toHaveFocus();

    await user.type(second, "a");
    expect(second).toHaveValue("");
  });

  it("moves back and clears on Backspace", async () => {
    const user = userEvent.setup();
    renderCard();

    const first = screen.getByLabelText("Digit 1");
    const second = screen.getByLabelText("Digit 2");

    await user.type(first, "8");
    expect(second).toHaveFocus();

    await user.keyboard("{Backspace}");
    expect(first).toHaveFocus();
    expect(first).toHaveValue("");

    await user.type(first, "7");
    await user.keyboard("{Backspace}");
    expect(first).toHaveValue("");
  });

  it("fills every cell from a pasted code", async () => {
    const user = userEvent.setup();
    renderCard();

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("841203");

    expect(screen.getByLabelText("Digit 1")).toHaveValue("8");
    expect(screen.getByLabelText("Digit 2")).toHaveValue("4");
    expect(screen.getByLabelText("Digit 3")).toHaveValue("1");
    expect(screen.getByLabelText("Digit 4")).toHaveValue("2");
    expect(screen.getByLabelText("Digit 5")).toHaveValue("0");
    expect(screen.getByLabelText("Digit 6")).toHaveValue("3");
  });

  it("auto-submits exactly once when the sixth digit lands", async () => {
    const user = userEvent.setup();
    const props = renderCard();

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("841203");

    await waitFor(() => {
      expect(props.onSubmit).toHaveBeenCalledTimes(1);
    });
    expect(props.onSubmit).toHaveBeenCalledWith("841203");
  });

  it("surfaces the error prop and clears the cells after a failed verify", async () => {
    const user = userEvent.setup();
    const onSubmit = vi.fn().mockRejectedValue(new Error("401 invalid_code"));
    const props = renderCard({ onSubmit });

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("000000");

    await waitFor(() => {
      expect(onSubmit).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByLabelText("Digit 1")).toHaveValue("");
    expect(props.onSuccess).not.toHaveBeenCalled();
  });

  it("calls onSecondary from the secondary action", async () => {
    const user = userEvent.setup();
    const props = renderCard();

    await user.click(screen.getByRole("button", { name: "Use backup code" }));
    expect(props.onSecondary).toHaveBeenCalledTimes(1);
  });

  it("clears a half-typed code when the 30-second step rolls over", () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date("2026-11-14T10:00:05Z"));
    renderCard();

    const first = screen.getByLabelText("Digit 1");
    fireEvent.change(first, { target: { value: "8" } });
    expect(first).toHaveValue("8");

    act(() => {
      vi.setSystemTime(new Date("2026-11-14T10:00:35Z"));
      vi.advanceTimersByTime(300);
    });

    expect(screen.getByLabelText("Digit 1")).toHaveValue("");
    expect(
      screen.getByText("Code expired — enter the new code"),
    ).toBeInTheDocument();
  });

  it("reduces motion to instant state changes when the OS asks", async () => {
    const original = window.matchMedia;
    window.matchMedia = vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("prefers-reduced-motion"),
      media: query,
      onchange: null,
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      addListener: vi.fn(),
      removeListener: vi.fn(),
      dispatchEvent: vi.fn(),
    }));

    const user = userEvent.setup();
    const props = renderCard();

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("841203");

    await waitFor(() => {
      expect(props.onSuccess).toHaveBeenCalledTimes(1);
    });
    expect(screen.getByText("Verified")).toBeInTheDocument();
    expect(screen.getByText("Session secured")).toBeInTheDocument();

    window.matchMedia = original;
  });
});
