import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";

import { PostLoginNotice } from "@/components/ui/PostLoginNotice";
import { ThemeProvider } from "@/theme/ThemeProvider";
import {
  clearNoticeDismissals,
  dismissNotice,
  isNoticeDismissed,
} from "@/features/auth/postLoginNotice";

describe("PostLoginNotice (D1 temporary password)", () => {
  beforeEach(() => {
    vi.clearAllMocks();
    clearNoticeDismissals();
  });

  it("renders the password notice with exactly two options", async () => {
    const user = userEvent.setup();
    const onPrimary = vi.fn();
    const onDismiss = vi.fn();

    render(
      <ThemeProvider>
        <PostLoginNotice
          title="Change Your Password"
          body="Your temporary password will be invalidated automatically."
          primaryLabel="Change Now"
          onPrimary={onPrimary}
          onDismiss={onDismiss}
        />
      </ThemeProvider>,
    );

    expect(screen.getByText("Change Your Password")).toBeInTheDocument();
    const buttons = screen.getAllByRole("button");
    expect(buttons).toHaveLength(2);

    await user.click(screen.getByRole("button", { name: "Remind me later" }));
    expect(onDismiss).toHaveBeenCalledTimes(1);

    await user.click(screen.getByRole("button", { name: "Change Now" }));
    expect(onPrimary).toHaveBeenCalledTimes(1);
  });

  it("renders the 2FA notice with Enable Now", async () => {
    const user = userEvent.setup();
    const onPrimary = vi.fn();

    render(
      <ThemeProvider>
        <PostLoginNotice
          title="Enable 2FA on Your Account"
          primaryLabel="Enable Now"
          onPrimary={onPrimary}
          onDismiss={vi.fn()}
        />
      </ThemeProvider>,
    );

    expect(screen.getByText("Enable 2FA on Your Account")).toBeInTheDocument();
    await user.click(screen.getByRole("button", { name: "Enable Now" }));
    expect(onPrimary).toHaveBeenCalledTimes(1);
  });
});

describe("post-login notice dismissal", () => {
  beforeEach(() => {
    clearNoticeDismissals();
  });

  it("remembers a dismissal for the rest of the login", () => {
    expect(isNoticeDismissed("password", "usr_1")).toBe(false);
    dismissNotice("password", "usr_1");
    expect(isNoticeDismissed("password", "usr_1")).toBe(true);
    expect(isNoticeDismissed("totp", "usr_1")).toBe(false);
  });

  it("re-arms the notices on the next login", () => {
    dismissNotice("totp", "usr_1");
    expect(isNoticeDismissed("totp", "usr_1")).toBe(true);
    clearNoticeDismissals();
    expect(isNoticeDismissed("totp", "usr_1")).toBe(false);
  });
});
