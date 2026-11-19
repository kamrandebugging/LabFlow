import { FadeValue } from "../../../components/ui/FadeValue";
import styles from "./SampleKpiRow.module.css";

export interface SampleKpiItem {
  id: string;
  label: string;
  value: number | string;
  subtitle?: string;
}

export interface SampleKpiRowProps {
  items: SampleKpiItem[];
  className?: string;
}

export function SampleKpiRow({
  items,
  className,
}: SampleKpiRowProps): JSX.Element {
  return (
    <div className={[styles.kpiGrid, className].filter(Boolean).join(" ")}>
      {items.map((item) => (
        <div key={item.id} className={styles.kpiCard}>
          <span className={styles.kpiLabel}>{item.label}</span>
          <span className={styles.kpiValue}>
            <FadeValue value={item.value} />
          </span>
          {item.subtitle && (
            <span className={styles.kpiSub}>{item.subtitle}</span>
          )}
        </div>
      ))}
    </div>
  );
}

export default SampleKpiRow;
