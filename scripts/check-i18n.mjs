/**
 * Build-time i18n gate (Doc 07 §9.1/§10).
 *
 * Fails when:
 *  - a key exists in one locale but not the other (per namespace);
 *  - a value is empty in either locale;
 *  - an API error code maps to a key that is missing in either locale;
 *  - a Doc 02 status value has no translated display word;
 *  - any Urdu string contains Eastern Arabic / Persian digits (must be 0-9).
 */
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const here = path.dirname(fileURLToPath(import.meta.url));
const root = path.resolve(here, "..");
const localesDir = path.join(root, "frontend", "src", "locales");

const NAMESPACES = [
  "common",
  "auth",
  "patients",
  "billing",
  "samples",
  "results",
  "reports",
  "partners",
  "settlements",
  "settings",
];

const problems = [];
const read = (lang, ns) =>
  JSON.parse(fs.readFileSync(path.join(localesDir, lang, `${ns}.json`), "utf8"));

function flatten(value, prefix = "", out = new Map()) {
  if (value !== null && typeof value === "object" && !Array.isArray(value)) {
    for (const [key, child] of Object.entries(value)) {
      flatten(child, prefix ? `${prefix}.${key}` : key, out);
    }
  } else {
    out.set(prefix, value);
  }
  return out;
}

const en = {};
const ur = {};
for (const ns of NAMESPACES) {
  en[ns] = flatten(read("en", ns));
  ur[ns] = flatten(read("ur", ns));

  for (const key of en[ns].keys()) {
    if (!ur[ns].has(key)) problems.push(`missing ur ${ns}:${key}`);
  }
  for (const key of ur[ns].keys()) {
    if (!en[ns].has(key)) problems.push(`missing en ${ns}:${key}`);
  }
}

// No raw-key rendering and no empty strings.
for (const [ns, map] of Object.entries(en)) {
  for (const [key, value] of map) {
    if (typeof value !== "string" || !value.trim()) {
      problems.push(`empty en ${ns}:${key}`);
    }
  }
}
for (const [ns, map] of Object.entries(ur)) {
  for (const [key, value] of map) {
    if (typeof value !== "string" || !value.trim()) {
      problems.push(`empty ur ${ns}:${key}`);
    }
  }
}

// Every server error code must have a key in both locales.
const errorCodes = JSON.parse(
  fs.readFileSync(path.join(root, "frontend", "src", "lib", "errorCodes.json"), "utf8"),
);
const hasKey = (lang, namespaced) => {
  const [maybeNs, ...rest] = namespaced.split(":");
  const ns = rest.length ? maybeNs : "common";
  const key = rest.length ? rest.join(":") : namespaced;
  return lang[ns]?.has(key) ?? false;
};
for (const [code, key] of Object.entries(errorCodes)) {
  if (!hasKey(en, key)) problems.push(`error code ${code} -> missing en key ${key}`);
  if (!hasKey(ur, key)) problems.push(`error code ${code} -> missing ur key ${key}`);
}

// Every Doc 02 status value needs a display word.
const statusValues = JSON.parse(
  fs.readFileSync(path.join(root, "frontend", "src", "lib", "statusValues.json"), "utf8"),
);
for (const [domain, values] of Object.entries(statusValues)) {
  for (const value of values) {
    const key = `status.${domain}.${value}`;
    if (!en.common.has(key)) problems.push(`status ${domain}.${value} -> missing en key`);
    if (!ur.common.has(key)) problems.push(`status ${domain}.${value} -> missing ur key`);
  }
}

// Latin digits only, everywhere (Doc 07 §10).
const EASTERN_DIGITS = /[\u0660-\u0669\u06F0-\u06F9]/;
for (const ns of NAMESPACES) {
  const raw = fs.readFileSync(path.join(localesDir, "ur", `${ns}.json`), "utf8");
  if (EASTERN_DIGITS.test(raw)) problems.push(`ur/${ns}.json contains non-Latin digits`);
}

if (problems.length) {
  console.error(`i18n check failed (${problems.length}):`);
  for (const problem of problems) console.error(`  - ${problem}`);
  process.exit(1);
}

const keyCount = Object.values(en).reduce((sum, map) => sum + map.size, 0);
console.log(`i18n check passed: ${keyCount} keys x 2 locales, ${NAMESPACES.length} namespaces.`);
