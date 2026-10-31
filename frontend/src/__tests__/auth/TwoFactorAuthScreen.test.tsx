/**
 * Component & Integration tests for LabFlow Screen 02: Two-Factor Authentication
 * Specification: docs/screen-pack/02-two-factor-auth.html, Doc 07 §5.1
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { TwoFactorAuthScreen } from "@/features/auth/TwoFactorAuthScreen";
import type { AuthService, AuthUser } from "@/features/auth/types";

describe("Screen 02: Two-Factor Authentication (02-two-factor-auth.html & Doc 07 §5.1)", () => {
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

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthService = createMockAuthService();
  });

  describe("UI Rendering and Context Banner", () => {
    it("renders LabFlow portal branding, tenant info, and email context", () => {
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          tenantName="City Diagnostic Lab — Lahore"
          terminalId="PK-LHE-04"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      expect(screen.getByText("LabFlow")).toBeInTheDocument();
      expect(screen.getByText("Two-factor authentication")).toBeInTheDocument();
      expect(
        screen.getByText(/Enter the 6-digit code from your authenticator app/i),
      ).toBeInTheDocument();

      // Tenant and user context
      expect(
        screen.getByText("City Diagnostic Lab — Lahore"),
      ).toBeInTheDocument();
      expect(screen.getByText(/ali\.raza@citylab\.pk/i)).toBeInTheDocument();
    });

    it("renders TOTP sync feedback hint and ISO 15189 compliance footer", () => {
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          terminalId="PK-LHE-04"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      expect(screen.getByText(/Time-synced TOTP/i)).toBeInTheDocument();
      expect(screen.getByText(/SHA-1 \/ 30s/i)).toBeInTheDocument();
      expect(screen.getByText(/ISO 15189 Certified Node/i)).toBeInTheDocument();
      expect(
        screen.getByText(/Encrypted Terminal PK-LHE-04/i),
      ).toBeInTheDocument();
    });

    it("renders 6 individual OTP input boxes by default with aria labels", () => {
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      for (let i = 1; i <= 6; i++) {
        expect(screen.getByLabelText(`Digit ${i}`)).toBeInTheDocument();
      }

      expect(
        screen.getByRole("button", { name: /Verify Session/i }),
      ).toBeInTheDocument();
      expect(
        screen.getByRole("button", { name: /Back to sign in/i }),
      ).toBeInTheDocument();
    });
  });

  describe("6-digit TOTP Input Behavior", () => {
    it("allows entering 6 digits and auto-advances focus between inputs", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const d1 = screen.getByLabelText("Digit 1");
      const d2 = screen.getByLabelText("Digit 2");
      const d3 = screen.getByLabelText("Digit 3");

      await user.type(d1, "8");
      expect(d1).toHaveValue("8");
      expect(d2).toHaveFocus();

      await user.type(d2, "4");
      expect(d2).toHaveValue("4");
      expect(d3).toHaveFocus();
    });

    it("ignores non-numeric keystrokes in TOTP digits", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const d1 = screen.getByLabelText("Digit 1");
      await user.type(d1, "a");
      expect(d1).toHaveValue("");

      await user.type(d1, "!");
      expect(d1).toHaveValue("");
    });

    it("moves focus to previous digit on Backspace when current input is empty", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const d1 = screen.getByLabelText("Digit 1");
      const d2 = screen.getByLabelText("Digit 2");

      await user.type(d1, "8");
      expect(d2).toHaveFocus();

      await user.keyboard("{Backspace}");
      expect(d1).toHaveFocus();
    });

    it("distributes pasted 6-digit code across all input boxes", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const d1 = screen.getByLabelText("Digit 1");
      await user.click(d1);
      await user.paste("841203");

      expect(screen.getByLabelText("Digit 1")).toHaveValue("8");
      expect(screen.getByLabelText("Digit 2")).toHaveValue("4");
      expect(screen.getByLabelText("Digit 3")).toHaveValue("1");
      expect(screen.getByLabelText("Digit 4")).toHaveValue("2");
      expect(screen.getByLabelText("Digit 5")).toHaveValue("0");
      expect(screen.getByLabelText("Digit 6")).toHaveValue("3");
    });
  });

  describe("Backup Code Mode Toggle", () => {
    it("toggles to backup code mode and allows entering alphanumeric backup code", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const backupToggle = screen.getByRole("button", {
        name: /Use a backup code/i,
      });
      await user.click(backupToggle);

      // In backup mode, single backup code input appears and 6-digit inputs disappear
      expect(screen.queryByLabelText("Digit 1")).not.toBeInTheDocument();
      const backupInput = screen.getByLabelText(/Backup code/i);
      expect(backupInput).toBeInTheDocument();

      // Typing backup code
      await user.type(backupInput, "BK-9842-X");
      expect(backupInput).toHaveValue("BK-9842-X");

      // Can toggle back to TOTP mode
      const totpToggle = screen.getByRole("button", {
        name: /Use authenticator app/i,
      });
      await user.click(totpToggle);
      expect(screen.getByLabelText("Digit 1")).toBeInTheDocument();
      expect(screen.queryByLabelText(/Backup code/i)).not.toBeInTheDocument();
    });
  });

  describe("Verification Submission", () => {
    it("submits 6-digit TOTP code and calls onSuccess on valid verification", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.verifyTotp).mockResolvedValueOnce({
        access: "jwt_session_valid",
        expires_in: 900,
        user: mockUser,
      });

      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const d1 = screen.getByLabelText("Digit 1");
      await user.click(d1);
      await user.paste("841203");

      const verifyBtn = screen.getByRole("button", { name: /Verify Session/i });
      await user.click(verifyBtn);

      expect(mockAuthService.verifyTotp).toHaveBeenCalledWith({
        code: "841203",
        isBackupCode: false,
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

    it("submits backup code with isBackupCode=true in backup code mode", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.verifyTotp).mockResolvedValueOnce({
        access: "jwt_session_backup_valid",
        expires_in: 900,
        user: mockUser,
      });

      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

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
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });
  });

  describe("Loading State ('Verifying...')", () => {
    it("disables button and shows 'Verifying...' while request is pending", async () => {
      const user = userEvent.setup();

      let resolvePromise: (value: unknown) => void = () => {};
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      vi.mocked(mockAuthService.verifyTotp).mockReturnValueOnce(
        pendingPromise as unknown as ReturnType<AuthService["verifyTotp"]>,
      );

      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      await user.click(screen.getByLabelText("Digit 1"));
      await user.paste("841203");
      await user.click(screen.getByRole("button", { name: /Verify Session/i }));

      const submitBtn = screen.getByRole("button", {
        name: /Verifying\.\.\./i,
      });
      expect(submitBtn).toBeInTheDocument();
      expect(submitBtn).toBeDisabled();

      resolvePromise({ access: "tok", expires_in: 900, user: mockUser });

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });
  });

  describe("Error Handling (Doc 07 §5.1)", () => {
    it("shows generic error notice on invalid code failure without revealing details", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.verifyTotp).mockRejectedValueOnce(
        new Error("401 invalid_code"),
      );

      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      await user.click(screen.getByLabelText("Digit 1"));
      await user.paste("000000");
      await user.click(screen.getByRole("button", { name: /Verify Session/i }));

      const errorNotice = await screen.findByRole("alert");
      expect(errorNotice).toBeInTheDocument();
      expect(errorNotice).toHaveTextContent(
        "Email, password or code is not correct",
      );

      // Verify button is re-enabled to retry
      const submitBtn = screen.getByRole("button", { name: /Verify Session/i });
      expect(submitBtn).toBeEnabled();
    });
  });

  describe("Navigation Back", () => {
    it("triggers onBack callback when clicking 'Back to sign in'", async () => {
      const user = userEvent.setup();
      render(
        <TwoFactorAuthScreen
          email="ali.raza@citylab.pk"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onBack={mockOnBack}
        />,
      );

      const backBtn = screen.getByRole("button", { name: /Back to sign in/i });
      await user.click(backBtn);

      expect(mockOnBack).toHaveBeenCalledTimes(1);
    });
  });
});
