import { Check } from "lucide-react";
import styles from "./CollectWizardStepper.module.css";

export interface WizardStep {
  number: number;
  title: string;
}

export interface CollectWizardStepperProps {
  currentStep: number;
  steps?: WizardStep[];
  className?: string;
}

const DEFAULT_STEPS: WizardStep[] = [
  { number: 1, title: "Patient & invoice" },
  { number: 2, title: "Tests & collection" },
];

export function CollectWizardStepper({
  currentStep,
  steps = DEFAULT_STEPS,
  className,
}: CollectWizardStepperProps): JSX.Element {
  return (
    <nav
      aria-label="Collection Progress"
      className={[styles.stepperNav, className].filter(Boolean).join(" ")}
    >
      <ol className={styles.stepList}>
        {steps.map((step, idx) => {
          const isCompleted = step.number < currentStep;
          const isCurrent = step.number === currentStep;

          let circleClass = styles.circleUpcoming;
          if (isCompleted) circleClass = styles.circleCompleted;
          else if (isCurrent) circleClass = styles.circleCurrent;

          return (
            <li key={step.number} className={styles.stepItem}>
              {idx > 0 && (
                <div
                  aria-hidden="true"
                  className={[
                    styles.connector,
                    isCompleted || isCurrent ? styles.connectorCompleted : "",
                  ].join(" ")}
                />
              )}
              <div className={[styles.circle, circleClass].join(" ")}>
                {isCompleted ? (
                  <Check className="w-4 h-4 stroke-[2.5]" />
                ) : (
                  <span>{step.number}</span>
                )}
              </div>
              <div className={styles.stepText}>
                <span className={styles.stepNumber}>Step {step.number}</span>
                <span className={styles.stepTitle}>{step.title}</span>
              </div>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

export default CollectWizardStepper;
