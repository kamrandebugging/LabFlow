import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ClipboardEvent,
  type CSSProperties,
  type KeyboardEvent,
  type ReactElement,
} from "react";

import { ThemeToggle } from "./ThemeToggle";
import styles from "./VerifyCodeCard.module.css";

export interface VerifyCodeCardProps {
  mode: "totp" | "email";
  maskedContact?: string;
  error: string | null;
  verifying: boolean;
  onSubmit: (code: string) => Promise<void>;
  onSuccess: () => void;
  onSecondary: () => void;
  secondaryLabel: string;
}

const CODE_LENGTH = 6;
const SUCCESS_HOLD_MS = 1100;
const CARD_WIDTH = 660;
const CARD_HEIGHT = 330;

const emptyCells = (): string[] => Array<string>(CODE_LENGTH).fill("");

/** Real 30-second TOTP step, per the locked design. */
const secondsLeftInStep = (): number =>
  30 - (Math.floor(Date.now() / 1000) % 30);

const currentStep = (): number => Math.floor(Date.now() / 1000 / 30);

function prefersReducedMotion(): boolean {
  return (
    typeof window !== "undefined" &&
    typeof window.matchMedia === "function" &&
    window.matchMedia("(prefers-reduced-motion: reduce)").matches
  );
}

/**
 * The one Verify Code card used by tenant 2FA and Platform 2FA.
 *
 * The component owns no auth logic: the host screen supplies `onSubmit` and
 * keeps its existing verify call. Success is signalled by the promise
 * resolving; failure by it rejecting.
 */
export function VerifyCodeCard({
  mode,
  maskedContact,
  error,
  verifying,
  onSubmit,
  onSuccess,
  onSecondary,
  secondaryLabel,
}: VerifyCodeCardProps): ReactElement {
  const [digits, setDigits] = useState<string[]>(emptyCells);
  const [activeIndex, setActiveIndex] = useState(0);
  const [secondsLeft, setSecondsLeft] = useState<number>(secondsLeftInStep);
  const [expiredNotice, setExpiredNotice] = useState(false);
  const [success, setSuccess] = useState(false);
  const [scale, setScale] = useState(1);

  const inputRefs = useRef<Array<HTMLInputElement | null>>([]);
  const digitsRef = useRef<string[]>(digits);
  const stepRef = useRef<number>(currentStep());
  const submittedCodeRef = useRef<string | null>(null);
  const successTimerRef = useRef<number | null>(null);
  const mountedRef = useRef(true);

  const commitDigits = useCallback((next: string[]) => {
    digitsRef.current = next;
    setDigits(next);
  }, []);

  const focusCell = useCallback((index: number) => {
    inputRefs.current[index]?.focus();
  }, []);

  // First paint: focus starts in cell 1.
  useEffect(() => {
    // StrictMode runs mount -> cleanup -> mount in development. Reset the
    // guard on every mount, otherwise the success path is disabled forever.
    mountedRef.current = true;
    inputRefs.current[0]?.focus();
    return () => {
      mountedRef.current = false;
      if (successTimerRef.current !== null) {
        window.clearTimeout(successTimerRef.current);
      }
    };
  }, []);

  // Scale the 660x330 card below 720px so it fits with 24px margins.
  useEffect(() => {
    const update = (): void => {
      const available = window.innerWidth - 48;
      setScale(Math.min(1, Math.max(0.3, available / CARD_WIDTH)));
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, []);

  // Real countdown. A new 30-second step clears any half-typed code.
  useEffect(() => {
    const tick = (): void => {
      setSecondsLeft(secondsLeftInStep());
      const step = currentStep();
      if (step === stepRef.current) return;
      stepRef.current = step;
      if (digitsRef.current.some((digit) => digit !== "")) {
        commitDigits(emptyCells());
        setActiveIndex(0);
        focusCell(0);
        setExpiredNotice(true);
      }
    };
    const timer = window.setInterval(tick, 250);
    return () => window.clearInterval(timer);
  }, [commitDigits, focusCell]);

  const submit = useCallback(
    async (code: string): Promise<void> => {
      try {
        await onSubmit(code);
      } catch {
        submittedCodeRef.current = null;
        commitDigits(emptyCells());
        setActiveIndex(0);
        focusCell(0);
        return;
      }
      if (!mountedRef.current) return;
      setSuccess(true);
      const hold = prefersReducedMotion() ? 0 : SUCCESS_HOLD_MS;
      successTimerRef.current = window.setTimeout(() => {
        onSuccess();
      }, hold);
    },
    [commitDigits, focusCell, onSubmit, onSuccess],
  );

  // Auto-submit fires once, when the 6th digit lands.
  useEffect(() => {
    const code = digits.join("");
    if (success) return;
    if (code.length !== CODE_LENGTH) {
      submittedCodeRef.current = null;
      return;
    }
    if (submittedCodeRef.current === code) return;
    submittedCodeRef.current = code;
    void submit(code);
  }, [digits, submit, success]);

  const handleChange = (index: number, value: string): void => {
    if (success) return;
    setExpiredNotice(false);
    const onlyDigits = value.replace(/\D/g, "");
    const next = [...digitsRef.current];

    if (!onlyDigits) {
      next[index] = "";
      commitDigits(next);
      return;
    }

    const characters = onlyDigits.slice(0, CODE_LENGTH - index).split("");
    characters.forEach((character, offset) => {
      const position = index + offset;
      if (position < CODE_LENGTH) next[position] = character;
    });
    commitDigits(next);

    const nextFocus = Math.min(index + characters.length, CODE_LENGTH - 1);
    setActiveIndex(nextFocus);
    focusCell(nextFocus);
  };

  const handleKeyDown = (
    index: number,
    event: KeyboardEvent<HTMLInputElement>,
  ): void => {
    if (success) return;
    if (event.key === "Backspace") {
      event.preventDefault();
      setExpiredNotice(false);
      const next = [...digitsRef.current];
      if (next[index]) {
        next[index] = "";
        commitDigits(next);
        setActiveIndex(index);
        focusCell(index);
        return;
      }
      if (index > 0) {
        next[index - 1] = "";
        commitDigits(next);
        setActiveIndex(index - 1);
        focusCell(index - 1);
      }
      return;
    }
    if (event.key === "ArrowLeft" && index > 0) {
      setActiveIndex(index - 1);
      focusCell(index - 1);
    }
    if (event.key === "ArrowRight" && index < CODE_LENGTH - 1) {
      setActiveIndex(index + 1);
      focusCell(index + 1);
    }
  };

  const handlePaste = (event: ClipboardEvent<HTMLInputElement>): void => {
    if (success) return;
    event.preventDefault();
    setExpiredNotice(false);
    const pasted = event.clipboardData
      .getData("text")
      .replace(/\D/g, "")
      .slice(0, CODE_LENGTH);
    if (!pasted) return;

    const next = emptyCells();
    for (let i = 0; i < pasted.length; i += 1) next[i] = pasted[i] ?? "";
    commitDigits(next);

    const focusIndex = Math.min(pasted.length, CODE_LENGTH - 1);
    setActiveIndex(focusIndex);
    focusCell(focusIndex);
  };

  const subline =
    mode === "totp"
      ? "· open your authenticator app"
      : `· code sent to ${maskedContact ?? ""}`.trimEnd();

  const statusText = success
    ? "Session secured"
    : expiredNotice
      ? "Code expired — enter the new code"
      : `Code expires in 0:${String(secondsLeft).padStart(2, "0")}`;

  const renderCell = (index: number): ReactElement => {
    const digit = digits[index] ?? "";
    const isActive = activeIndex === index;
    const cellClass = [
      styles.cell,
      digit ? styles.cellLit : "",
      isActive ? styles.cellActive : "",
      success ? styles.cellChecked : "",
    ]
      .filter(Boolean)
      .join(" ");

    return (
      <div
        key={index}
        className={styles.cellWrap}
        style={{ "--cell-index": index } as CSSProperties}
      >
        <input
          ref={(element) => {
            inputRefs.current[index] = element;
          }}
          aria-label={`Digit ${index + 1}`}
          type="text"
          inputMode="numeric"
          autoComplete={index === 0 ? "one-time-code" : "off"}
          maxLength={1}
          value={digit}
          disabled={success || verifying}
          dir="ltr"
          onChange={(event) => handleChange(index, event.target.value)}
          onKeyDown={(event) => handleKeyDown(index, event)}
          onPaste={handlePaste}
          onFocus={() => setActiveIndex(index)}
          className={cellClass}
        />
        {isActive && !digit && !success && (
          <span className={styles.caret} aria-hidden="true" />
        )}
      </div>
    );
  };

  return (
    <div className={styles.stage} style={{ height: CARD_HEIGHT * scale }}>
      <div className={styles.shrink} style={{ transform: `scale(${scale})` }}>
        <section
          className={styles.card}
          aria-label="Verify it's you"
          data-success={success ? "true" : "false"}
        >
          <span className={styles.ring} aria-hidden="true" />
          <div className={styles.face}>
            <header className={styles.header}>
              <div className={styles.titles}>
                <h1 className={styles.title}>Verify it&#39;s you</h1>
                <p className={styles.subline}>{subline}</p>
              </div>
              <ThemeToggle />
            </header>

            <div className={styles.statusRow}>
              <span className={styles.barTitle}>Security check</span>
              <span
                className={`${styles.status} ${expiredNotice && !success ? styles.statusExpired : ""}`}
                role="status"
              >
                {statusText}
              </span>
            </div>

            {success ? (
              <div className={styles.codeArea}>
                <div
                  className={`${styles.cells} ${styles.cellsChecked}`}
                  aria-hidden="true"
                >
                  <div className={styles.cellGroup}>
                    {[0, 1, 2].map(renderCell)}
                  </div>
                  <span className={styles.dash} aria-hidden="true" />
                  <div className={styles.cellGroup}>
                    {[3, 4, 5].map(renderCell)}
                  </div>
                </div>
                <div className={styles.verified}>
                  <span className={styles.verifiedRing} aria-hidden="true">
                    <svg viewBox="0 0 24 24" width="22" height="22">
                      <path
                        d="M4 12.5l5 5L20 6.5"
                        fill="none"
                        stroke="currentColor"
                        strokeWidth="2.4"
                        strokeLinecap="round"
                        strokeLinejoin="round"
                      />
                    </svg>
                  </span>
                  <span className={styles.verifiedLabel}>Verified</span>
                </div>
              </div>
            ) : (
              <div className={styles.codeArea}>
                <div className={styles.cells}>
                  <div className={styles.cellGroup}>
                    {[0, 1, 2].map(renderCell)}
                  </div>
                  <span className={styles.dash} aria-hidden="true" />
                  <div className={styles.cellGroup}>
                    {[3, 4, 5].map(renderCell)}
                  </div>
                </div>
              </div>
            )}

            {error && (
              <p className={styles.error} role="alert">
                {error}
              </p>
            )}

            <div className={styles.actions}>
              <button
                type="button"
                className={styles.primary}
                disabled={verifying || success}
                onClick={() => {
                  const code = digits.join("");
                  if (code.length === CODE_LENGTH) void submit(code);
                }}
              >
                {success ? "Done" : "Verify"}
              </button>
              <button
                type="button"
                className={styles.secondary}
                disabled={verifying || success}
                onClick={onSecondary}
              >
                {secondaryLabel}
              </button>
            </div>
          </div>
        </section>
      </div>
    </div>
  );
}
