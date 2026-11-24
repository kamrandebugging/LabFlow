import { useTranslation } from "react-i18next";
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

export function CollectWizardStepper({
  currentStep,
  steps,
  className,
}: CollectWizardStepperProps): JSX.Element {
  const { t } = useTranslation("samples");
  const resolvedSteps: WizardStep[] = steps ?? [
    { number: 1, title: t("samples:stepper.patient_invoice") },
    { number: 2, title: t("samples:stepper.tests_collection") },
  ];

  return (
    <nav
      aria-label={t("samples:stepper.aria")}
      className={[styles.stepperNav, className].filter(Boolean).join(" ")}
    >
      <ol className={styles.stepList}>
        {resolvedSteps.map((step, idx) => {
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
                <span className={styles.stepNumber}>
                  {t("samples:stepper.step", { n: step.number })}
                </span>
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
