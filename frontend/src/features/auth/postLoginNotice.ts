/**
 * Dismissal memory for the two post-login notices.
 *
 * "Remind me later" hides the notice for the rest of THIS login only: the
 * dismissal lives in sessionStorage (so a page reload keeps it hidden) and is
 * cleared on every successful sign-in (so the next login shows it again).
 */
export type PostLoginNoticeKind = "password" | "totp";

const PREFIX = "labflow.notice.dismissed:";

function storage(): Storage | null {
  if (typeof window === "undefined") return null;
  try {
    return window.sessionStorage;
  } catch {
    return null;
  }
}

function key(kind: PostLoginNoticeKind, userId: string): string {
  return `${PREFIX}${kind}:${userId}`;
}

export function isNoticeDismissed(
  kind: PostLoginNoticeKind,
  userId: string,
): boolean {
  return storage()?.getItem(key(kind, userId)) === "1";
}

export function dismissNotice(kind: PostLoginNoticeKind, userId: string): void {
  storage()?.setItem(key(kind, userId), "1");
}

/** Called once per successful login, before the shell renders. */
export function clearNoticeDismissals(): void {
  const store = storage();
  if (!store) return;
  const stale: string[] = [];
  for (let index = 0; index < store.length; index += 1) {
    const item = store.key(index);
    if (item?.startsWith(PREFIX)) stale.push(item);
  }
  stale.forEach((item) => store.removeItem(item));
}
