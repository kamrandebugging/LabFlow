/**
 * App — root application component (scaffold placeholder).
 *
 * Scope: Single placeholder heading only.
 * Do NOT add routing, API calls, auth handlers, or UI components here.
 * Those are introduced in subsequent subtasks (LAB-38+).
 */
import { useTranslation } from "react-i18next";

function App(): JSX.Element {
  const { t } = useTranslation();

  return (
    <main className="flex min-h-screen items-center justify-center bg-background">
      <h1 className="text-4xl font-bold text-primary">{t("welcome")}</h1>
    </main>
  );
}

export default App;

