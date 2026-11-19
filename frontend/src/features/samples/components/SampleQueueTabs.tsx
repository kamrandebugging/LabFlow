import styles from "./SampleQueueTabs.module.css";

export interface QueueTabItem {
  id: string;
  label: string;
  count?: number;
}

export interface SampleQueueTabsProps {
  tabs: QueueTabItem[];
  activeTab: string;
  onSelectTab: (tabId: string) => void;
  className?: string;
}

export function SampleQueueTabs({
  tabs,
  activeTab,
  onSelectTab,
  className,
}: SampleQueueTabsProps): JSX.Element {
  return (
    <nav
      role="tablist"
      aria-label="Sample Queues"
      className={[styles.tabsContainer, className].filter(Boolean).join(" ")}
    >
      {tabs.map((tab) => {
        const isActive = tab.id === activeTab;
        return (
          <button
            key={tab.id}
            role="tab"
            type="button"
            aria-selected={isActive}
            onClick={() => onSelectTab(tab.id)}
            className={[
              styles.tabButton,
              isActive ? styles.tabButtonActive : "",
            ]
              .filter(Boolean)
              .join(" ")}
          >
            <span>{tab.label}</span>
            {typeof tab.count === "number" && (
              <span className={styles.countBadge}>{tab.count}</span>
            )}
          </button>
        );
      })}
    </nav>
  );
}

export default SampleQueueTabs;
