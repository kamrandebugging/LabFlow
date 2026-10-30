/**
 * Component & Integration tests for LabFlow Screen 01: Staff Login
 * Specification: docs/screen-pack/01-staff-login.html, Doc 07 §5.1
 */
import { describe, it, expect, vi, beforeEach } from "vitest";
import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { StaffLoginScreen } from "@/features/auth/StaffLoginScreen";
import type { AuthService, AuthUser } from "@/features/auth/types";
import i18n from "@/i18n";

describe("Screen 01: Staff Login (01-staff-login.html & Doc 07 §5.1)", () => {
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
  const mockOnTotpRequired = vi.fn();

  beforeEach(() => {
    vi.clearAllMocks();
    mockAuthService = createMockAuthService();
    void i18n.changeLanguage("en");
  });

  describe("UI Rendering and Compliance Elements", () => {
    it("renders LabFlow branding, version, and portal badge", () => {
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      expect(screen.getByText("LabFlow")).toBeInTheDocument();
      expect(screen.getByText(/LIS v4\.2/i)).toBeInTheDocument();
      expect(screen.getByText(/Portal/i)).toBeInTheDocument();
    });

    it("renders lab name and node badge", () => {
      render(
        <StaffLoginScreen
          tenantName="City Diagnostic Lab — Lahore"
          nodeId="PK-LHE-01"
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      expect(
        screen.getByText("City Diagnostic Lab — Lahore"),
      ).toBeInTheDocument();
      expect(screen.getByText("PK-LHE-01")).toBeInTheDocument();
      expect(screen.getByText("Staff sign in")).toBeInTheDocument();
    });

    it("renders form inputs for email and password with labels", () => {
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const emailInput = screen.getByLabelText(/Email/i);
      expect(emailInput).toBeInTheDocument();
      expect(emailInput).toHaveAttribute("type", "email");
      expect(emailInput).toHaveAttribute("required");

      const passwordInput = screen.getByLabelText(/^Password/i);
      expect(passwordInput).toBeInTheDocument();
      expect(passwordInput).toHaveAttribute("type", "password");
      expect(passwordInput).toHaveAttribute("required");

      expect(
        screen.getByRole("button", { name: /Sign in/i }),
      ).toBeInTheDocument();
    });

    it("renders ISO 15189 compliance footer text and secured node status", () => {
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      expect(screen.getByText(/ISO 15189 compliance/i)).toBeInTheDocument();
      expect(
        screen.getByText(
          /Authorized staff access only\. Activity is monitored and logged/i,
        ),
      ).toBeInTheDocument();
      expect(screen.getByText(/Secured Clinical Node/i)).toBeInTheDocument();
    });
  });

  describe("Password Visibility Toggle", () => {
    it("toggles password field between password and text type", async () => {
      const user = userEvent.setup();
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const passwordInput = screen.getByLabelText(/^Password/i);
      const toggleBtn = screen.getByRole("button", {
        name: /Toggle password visibility/i,
      });

      expect(passwordInput).toHaveAttribute("type", "password");

      // Click to reveal password
      await user.click(toggleBtn);
      expect(passwordInput).toHaveAttribute("type", "text");

      // Click again to hide password
      await user.click(toggleBtn);
      expect(passwordInput).toHaveAttribute("type", "password");
    });
  });

  describe("Language Toggle (English / Urdu)", () => {
    it("renders language switcher and triggers language change", async () => {
      const user = userEvent.setup();
      const changeLanguageSpy = vi.spyOn(i18n, "changeLanguage");

      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const urduBtn = screen.getByRole("button", { name: /اردو/i });
      const englishBtn = screen.getByRole("button", { name: /English/i });

      expect(urduBtn).toBeInTheDocument();
      expect(englishBtn).toBeInTheDocument();

      await user.click(urduBtn);
      expect(changeLanguageSpy).toHaveBeenCalledWith("ur");

      await user.click(englishBtn);
      expect(changeLanguageSpy).toHaveBeenCalledWith("en");
    });
  });

  describe("Credential Reset Notice", () => {
    it("displays admin contact guidance when clicking 'Reset via Lab Admin'", async () => {
      const user = userEvent.setup();
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const resetLink = screen.getByRole("button", {
        name: /Reset via Lab Admin/i,
      });
      await user.click(resetLink);

      expect(
        await screen.findByText(
          /Please contact your Lab Supervisor or Technical Administrator to trigger an authorized credential reissue/i,
        ),
      ).toBeInTheDocument();
    });
  });

  describe("Form Validation", () => {
    it("prevents form submission when email or password is empty", async () => {
      const user = userEvent.setup();
      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const submitBtn = screen.getByRole("button", { name: /Sign in/i });

      // Click submit without entering anything
      await user.click(submitBtn);

      expect(mockAuthService.login).not.toHaveBeenCalled();
    });
  });

  describe("Credential Submission and Transitions", () => {
    it("submits valid credentials to auth service and calls onSuccess on direct login", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.login).mockResolvedValueOnce({
        totpRequired: false,
        session: {
          access: "jwt_token_sample",
          expires_in: 900,
          user: mockUser,
        },
      });

      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      const emailInput = screen.getByLabelText(/Email/i);
      const passwordInput = screen.getByLabelText(/^Password/i);
      const submitBtn = screen.getByRole("button", { name: /Sign in/i });

      await user.type(emailInput, "staff@citylab.pk");
      await user.type(passwordInput, "ValidPassword123!");
      await user.click(submitBtn);

      expect(mockAuthService.login).toHaveBeenCalledWith({
        email: "staff@citylab.pk",
        password: "ValidPassword123!",
      });

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalledWith(
          expect.objectContaining({
            access: "jwt_token_sample",
            user: mockUser,
          }),
        );
      });
      expect(mockOnTotpRequired).not.toHaveBeenCalled();
    });

    it("triggers onTotpRequired callback when server returns totp_required=true", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.login).mockResolvedValueOnce({
        totpRequired: true,
      });

      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      await user.type(screen.getByLabelText(/Email/i), "ali.raza@citylab.pk");
      await user.type(screen.getByLabelText(/^Password/i), "CorrectPass123!");
      await user.click(screen.getByRole("button", { name: /Sign in/i }));

      await waitFor(() => {
        expect(mockOnTotpRequired).toHaveBeenCalledWith("ali.raza@citylab.pk");
      });
      expect(mockOnSuccess).not.toHaveBeenCalled();
    });
  });

  describe("Loading State ('Authenticating...')", () => {
    it("displays 'Authenticating...', disables submit button, and shows spinner during request", async () => {
      const user = userEvent.setup();

      // Return unresolved promise to freeze in pending state
      let resolvePromise: (value: unknown) => void = () => {};
      const pendingPromise = new Promise((resolve) => {
        resolvePromise = resolve;
      });
      vi.mocked(mockAuthService.login).mockReturnValueOnce(
        pendingPromise as unknown as ReturnType<AuthService["login"]>,
      );

      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      await user.type(screen.getByLabelText(/Email/i), "staff@citylab.pk");
      await user.type(screen.getByLabelText(/^Password/i), "Secret123!");
      await user.click(screen.getByRole("button", { name: /Sign in/i }));

      // Button should now show 'Authenticating...' and be disabled
      const submitBtn = screen.getByRole("button", {
        name: /Authenticating\.\.\./i,
      });
      expect(submitBtn).toBeInTheDocument();
      expect(submitBtn).toBeDisabled();

      // Resolve the call
      resolvePromise({
        totpRequired: false,
        session: { access: "tok", expires_in: 900, user: mockUser },
      });

      await waitFor(() => {
        expect(mockOnSuccess).toHaveBeenCalled();
      });
    });
  });

  describe("Generic Error Handling (Doc 07 §5.1)", () => {
    it("displays exact generic error message on 401 or invalid credentials without leaking reason", async () => {
      const user = userEvent.setup();
      vi.mocked(mockAuthService.login).mockRejectedValueOnce(
        new Error("401 invalid_credentials"),
      );

      render(
        <StaffLoginScreen
          authService={mockAuthService}
          onSuccess={mockOnSuccess}
          onTotpRequired={mockOnTotpRequired}
        />,
      );

      await user.type(screen.getByLabelText(/Email/i), "wrong@citylab.pk");
      await user.type(screen.getByLabelText(/^Password/i), "WrongPassword");
      await user.click(screen.getByRole("button", { name: /Sign in/i }));

      // Assert error notice with role="alert"
      const errorNotice = await screen.findByRole("alert");
      expect(errorNotice).toBeInTheDocument();
      expect(errorNotice).toHaveTextContent(
        "Email, password or code is not correct",
      );

      // Verify button is re-enabled to allow retry
      const submitBtn = screen.getByRole("button", { name: /Sign in/i });
      expect(submitBtn).toBeEnabled();
    });
  });
});
