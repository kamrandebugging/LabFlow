/**
 * Screen 02: Two-Factor Authentication — the shared VerifyCodeCard mounted by
 * the tenant 2FA route (Doc 07 §5.1, locked Verify Code design).
 */
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TwoFactorAuthScreen } from "@/features/auth/TwoFactorAuthScreen";
import type { AuthService, AuthUser } from "@/features/auth/types";
import { ThemeProvider } from "@/theme/ThemeProvider";

describe("Screen 02: Two-Factor Authentication", () => {
  const mockUser: AuthUser = {
    id: "usr_1001",
    name: "Dr. Ali Raza",
    role: "pathologist",
    branch_ids: ["br_lahore_01"],
  };

  const createMockAuthService = (): AuthService => ({
    login: vi.fn(),
    verifyTotp: vi.fn(),
    logout: vi.fn(),
  });

  let mockAuthService: AuthService;
  const mockOnSuccess = vi.fn();
  const mockOnBack = vi.fn();

  const originalMatchMedia = window.matchMedia;

  const renderScreen = () =>
    render(
      <ThemeProvider>
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />
      </ThemeProvider>,
    );

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthService = createMockAuthService();
    // Keep the success hold instant; the animation timing itself is covered by
    // the VerifyCodeCard reduced-motion test.
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
  });

  afterEach(() => {
    window.matchMedia = originalMatchMedia;
  });

  it("mounts the one shared Verify Code card", () => {
    renderScreen();

    expect(screen.getByText("Verify it's you")).toBeInTheDocument();
    expect(
      screen.getByText("· open your authenticator app"),
    ).toBeInTheDocument();
    expect(screen.getByText("Security check")).toBeInTheDocument();
    for (let index = 1; index <= 6; index += 1) {
      expect(screen.getByLabelText(`Digit ${index}`)).toBeInTheDocument();
    }
    expect(screen.getByRole("button", { name: "Verify" })).toBeInTheDocument();
    expect(
      screen.getByRole("button", { name: "Back to sign in" }),
    ).toBeInTheDocument();
  });

  it("verifies the 6-digit code and lands the session", async () => {
    const user = userEvent.setup();
    vi.mocked(mockAuthService.verifyTotp).mockResolvedValueOnce({
      access: "jwt_session_valid",
      expires_in: 900,
      user: mockUser,
    });

    renderScreen();

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("841203");

    await waitFor(() => {
      expect(mockAuthService.verifyTotp).toHaveBeenCalledWith({
        code: "841203",
        isBackupCode: false,
      });
    });
    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalledWith(
        expect.objectContaining({
          access: "jwt_session_valid",
          user: mockUser,
        }),
      );
    });
  });

  it("keeps the backup-code path with isBackupCode=true", async () => {
    const user = userEvent.setup();
    vi.mocked(mockAuthService.verifyTotp).mockResolvedValueOnce({
      access: "jwt_session_backup_valid",
      expires_in: 900,
      user: mockUser,
    });

    renderScreen();

    await user.click(
      screen.getByRole("button", { name: /Use a backup code/i }),
    );
    const backupInput = screen.getByLabelText(/Backup code/i);
    await user.type(backupInput, "BKP-112233");
    await user.click(screen.getByRole("button", { name: /Verify Session/i }));

    expect(mockAuthService.verifyTotp).toHaveBeenCalledWith({
      code: "BKP-112233",
      isBackupCode: true,
    });
    await waitFor(() => {
      expect(mockOnSuccess).toHaveBeenCalledWith(
        expect.objectContaining({ access: "jwt_session_backup_valid" }),
      );
    });
  });

  it("shows the existing generic error and clears the cells on a wrong code", async () => {
    const user = userEvent.setup();
    vi.mocked(mockAuthService.verifyTotp).mockRejectedValueOnce(
      new Error("401 invalid_code"),
    );

    renderScreen();

    await user.click(screen.getByLabelText("Digit 1"));
    await user.paste("000000");

    const errorNotice = await screen.findByRole("alert");
    expect(errorNotice).toHaveTextContent(
      "Email, password or code is not correct",
    );
    expect(screen.getByLabelText("Digit 1")).toHaveValue("");
    expect(mockOnSuccess).not.toHaveBeenCalled();
  });

  it("triggers onBack from 'Back to sign in'", async () => {
    const user = userEvent.setup();
    renderScreen();

    await user.click(screen.getByRole("button", { name: /Back to sign in/i }));
    expect(mockOnBack).toHaveBeenCalledTimes(1);
  });
});
