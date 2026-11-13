/**
 * Resolve a tenant's real primary domain.
 *
 * Prefer the `domain` returned by the platform tenant API. Only fall back to
 * the configured platform base domain when the API has not supplied one; the
 * product domain is never hardcoded in the client.
 */
export function tenantDomain(
  slug: string,
  domain?: string | null,
): string | null {
  if (domain) return domain;
  const base = import.meta.env.VITE_PLATFORM_BASE_DOMAIN;
  if (base && slug) return `${slug}.${base}`;
  return null;
}
