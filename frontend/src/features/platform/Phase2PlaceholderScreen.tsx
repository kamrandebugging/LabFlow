import { Link } from "react-router-dom";

export function Phase2PlaceholderScreen({
  title,
}: {
  title: string;
}): JSX.Element {
  return (
    <div className="flex flex-col gap-space-lg w-full max-w-5xl mx-auto py-space-xl">
      <div className="bg-surface-container-lowest p-space-2xl rounded-lg border border-outline-variant/40 shadow-sm flex flex-col items-center justify-center text-center">
        <div className="w-16 h-16 rounded-full bg-surface-container-low flex items-center justify-center text-primary mb-space-md">
          <span className="material-symbols-outlined text-[36px]">
            hourglass_top
          </span>
        </div>
        <h1 className="font-headline-md text-headline-md text-on-surface mb-space-xs">
          {title}
        </h1>
        <p className="font-body-md text-body-md text-outline max-w-md mb-space-lg">
          Available in Phase 2. This module is currently planned and will be
          unlocked in the next release cycle.
        </p>
        <div className="flex items-center gap-space-sm">
          <Link
            to="/platform/overview"
            className="px-space-md py-space-xs bg-primary hover:bg-primary-container text-on-primary font-label-sm text-label-sm rounded transition-colors"
          >
            Return to Overview
          </Link>
          <Link
            to="/platform/tenants"
            className="px-space-md py-space-xs bg-surface-container-low hover:bg-surface-container text-on-surface font-label-sm text-label-sm rounded transition-colors"
          >
            View Active Labs
          </Link>
        </div>
      </div>
    </div>
  );
}
