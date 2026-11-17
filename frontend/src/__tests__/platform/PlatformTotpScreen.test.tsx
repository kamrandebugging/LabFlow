import { describe, it, expect, beforeEach } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";

import { PlatformTotpScreen } from "@/features/platform/PlatformTotpScreen";
import { usePlatformAuthStore } from "@/features/platform/platformAuthStore";
import { ThemeProvider } from "@/theme/ThemeProvider";

describe("Platform 2FA", () => {
  beforeEach(() => {
    usePlatformAuthStore.getState().clear();
  });

  it("mounts the same shared Verify Code card as the tenant screen", () => {
    render(
      <ThemeProvider>
        <MemoryRouter>
          <PlatformTotpScreen />
        </MemoryRouter>
      </ThemeProvider>,
    );

    expect(screen.getByText("Verify it's you")).toBeInTheDocument();
    expect(
      screen.getByText("· open your authenticator app"),
    ).toBeInTheDocument();
    expect(screen.getByText("Security check")).toBeInTheDocument();
    for (let index = 1; index <= 6; index += 1) {
      expect(screen.getByLabelText(`Digit ${index}`)).toBeInTheDocument();
    }
    expect(
      screen.getByRole("button", { name: "Use backup code" }),
    ).toBeInTheDocument();
    expect(screen.getByText("Back to sign in")).toBeInTheDocument();
  });
});
