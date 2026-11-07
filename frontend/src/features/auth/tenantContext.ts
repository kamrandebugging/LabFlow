/**
 * Tenant resolution service for multi-tenant portal branding.
 * Resolves tenant details from active host/subdomain and backend auth tenant endpoint.
 */

export interface TenantContextInfo {
  id?: string;
  name: string;
  slug: string;
  city?: string;
  nodeId?: string;
  terminalId?: string;
}

const CITY_CODE_MAP: Record<string, string> = {
  islamabad: "PK-ISB-01",
  lahore: "PK-LHE-01",
  karachi: "PK-KHI-01",
  rawalpindi: "PK-RWP-01",
  peshawar: "PK-PEW-01",
  multan: "PK-MUX-01",
  faisalabad: "PK-FSD-01",
  gujranwala: "PK-GUJ-01",
  quetta: "PK-UET-01",
};

export function resolveNodeId(city?: string, slug?: string): string {
  if (city && CITY_CODE_MAP[city.toLowerCase()]) {
    return CITY_CODE_MAP[city.toLowerCase()] ?? "PK-ISB-01";
  }
  const cleanSlug = (slug || "").toLowerCase();
  if (cleanSlug.includes("isb")) return "PK-ISB-01";
  if (cleanSlug.includes("lhr") || cleanSlug.includes("lhe")) return "PK-LHE-01";
  if (cleanSlug.includes("khi")) return "PK-KHI-01";
  if (cleanSlug.length >= 3) {
    return `PK-${cleanSlug.slice(0, 3).toUpperCase()}-01`;
  }
  return "PK-ISB-01";
}

export function getSubdomainTenant(): TenantContextInfo | null {
  if (typeof window === "undefined" || !window.location) return null;
  const host = window.location.hostname;
  const parts = host.split(".");
  const firstPart = parts[0];
  // Must be a subdomain (e.g. randex.localhost or demo-isb.localhost)
  if (
    parts.length >= 2 &&
    firstPart &&
    firstPart !== "localhost" &&
    firstPart !== "127" &&
    firstPart !== "platform" &&
    firstPart !== "admin" &&
    firstPart !== "www"
  ) {
    const slug = firstPart.toLowerCase();
    // Known seed tenants fast resolution
    if (slug === "randex") {
      return {
        name: "Randex",
        slug: "randex",
        city: "",
        nodeId: "PK-RAN-01",
        terminalId: "PK-RAN-04",
      };
    }
    if (slug === "demo-isb") {
      return {
        name: "Capital Diagnostic Centre",
        slug: "demo-isb",
        city: "Islamabad",
        nodeId: "PK-ISB-01",
        terminalId: "PK-ISB-04",
      };
    }
    if (slug === "demo-lhr") {
      return {
        name: "Punjab Clinical Labs",
        slug: "demo-lhr",
        city: "Lahore",
        nodeId: "PK-LHE-01",
        terminalId: "PK-LHE-04",
      };
    }
    const derivedName = slug
      .split("-")
      .map((w) => w.charAt(0).toUpperCase() + w.slice(1))
      .join(" ");
    const node = resolveNodeId(undefined, slug);
    return {
      name: derivedName,
      slug,
      nodeId: node,
      terminalId: node.replace("-01", "-04"),
    };
  }
  return null;
}

export async function fetchTenantContext(): Promise<TenantContextInfo | null> {
  try {
    const res = await fetch("/api/v1/auth/tenant");
    if (res.ok) {
      const data = await res.json();
      if (data?.tenant) {
        return {
          id: data.tenant.id,
          name: data.tenant.name,
          slug: data.tenant.slug,
          city: data.tenant.city,
          nodeId: data.tenant.node_id,
          terminalId: data.tenant.terminal_id,
        };
      }
    }
  } catch {
    // If backend endpoint is unavailable, fall back to subdomain resolver
  }
  return getSubdomainTenant();
}
