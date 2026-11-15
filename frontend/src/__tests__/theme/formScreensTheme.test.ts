import { readFileSync } from "node:fs";
import { fileURLToPath } from "node:url";

import { describe, expect, it } from "vitest";

const read = (relative: string): string =>
  readFileSync(fileURLToPath(new URL(relative, import.meta.url)), "utf8");

function luminance(hex: string): number {
  const value = hex.replace("#", "");
  const rgb = [0, 2, 4].map((offset) => {
    const channel = Number.parseInt(value.slice(offset, offset + 2), 16) / 255;
    return channel <= 0.03928
      ? channel / 12.92
      : ((channel + 0.055) / 1.055) ** 2.4;
  });
  return (
    0.2126 * (rgb[0] ?? 0) + 0.7152 * (rgb[1] ?? 0) + 0.0722 * (rgb[2] ?? 0)
  );
}

function ratio(a: string, b: string): number {
  const sorted = [luminance(a), luminance(b)].sort((x, y) => y - x);
  const high = sorted[0] ?? 0;
  const low = sorted[1] ?? 0;
  return (high + 0.05) / (low + 0.05);
}

function composite(
  foreground: string,
  alpha: number,
  background: string,
): string {
  const parse = (hex: string): number[] => {
    const value = hex.replace("#", "");
    return [0, 2, 4].map((offset) =>
      Number.parseInt(value.slice(offset, offset + 2), 16),
    );
  };
  const fg = parse(foreground);
  const bg = parse(background);
  return `#${fg
    .map((channel, index) =>
      Math.round(channel * alpha + (bg[index] ?? 0) * (1 - alpha))
        .toString(16)
        .padStart(2, "0"),
    )
    .join("")}`;
}

const TOUCHED_CSS = [
  "../../features/patients/PatientForm.module.css",
  "../../features/patients/PatientRecord.module.css",
  "../../features/billing/NewInvoiceScreen.module.css",
  "../../features/billing/InvoiceDetailScreen.module.css",
] as const;

describe("Patient + invoice form/details neumorphism tokens", () => {
  it("keeps the touched CSS modules free of literal colours", () => {
    for (const file of TOUCHED_CSS) {
      const css = read(file);
      expect(css, `${file} hex`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(css, `${file} rgb`).not.toMatch(/\brgba?\(/);
      expect(css, `${file} hsl`).not.toMatch(/\bhsla?\(/);
    }
  });

  it("routes every surface, border and status colour through theme tokens", () => {
    const required = [
      "var(--color-surface)",
      "var(--color-well)",
      "var(--color-card-border)",
      "var(--color-border)",
      "var(--shadow-neu-raised)",
      "var(--ring-color)",
    ];

    for (const file of TOUCHED_CSS) {
      const css = read(file);
      for (const token of required) {
        expect(css, `${file} uses ${token}`).toContain(token);
      }
    }

    // Controls are pressed wells: forms, detail forms and the modal all inset.
    for (const file of [
      "../../features/patients/PatientForm.module.css",
      "../../features/billing/NewInvoiceScreen.module.css",
      "../../features/billing/InvoiceDetailScreen.module.css",
    ] as const) {
      expect(read(file), `${file} inset control`).toContain(
        "var(--shadow-neu-inset)",
      );
    }
  });

  it("gives every interactive control a 44px hit target and a 2px focus ring", () => {
    for (const file of TOUCHED_CSS) {
      const css = read(file);
      expect(css, `${file} control height`).toContain("min-height: 44px");
      const minHeights = css.match(/min-height: (\d+)px/g) ?? [];
      expect(minHeights.length, `${file} hit targets`).toBeGreaterThan(0);
      for (const rule of minHeights) {
        const value = Number.parseInt(rule.replace(/\D/g, ""), 10);
        expect(value, `${file} ${rule}`).toBeGreaterThanOrEqual(32);
      }
      expect(css, `${file} focus ring`).toMatch(
        /:focus-visible\s*\{[^}]*outline: 2px solid var\(--ring-color\)/,
      );
      expect(css, `${file} focus offset`).toMatch(/outline-offset: [3-4]px/);
    }
  });

  it("keeps the raised card blur at or below the 12px ceiling", () => {
    for (const file of TOUCHED_CSS) {
      const css = read(file);
      // Cards only reference the shared token; no bespoke blur is allowed.
      expect(css, `${file} card shadow`).toContain("var(--shadow-neu-raised)");
      expect(css, `${file} raw blur`).not.toMatch(
        /box-shadow:[^;]*\d+px \d+px \d+px/,
      );
    }
  });

  it("keeps every shipped text pair at >= 4.5:1 in both themes", () => {
    const textPairs = [
      // Light — page, card, well.
      ["#081c15", "#faf9f6"], // ink on page
      ["#35473d", "#faf9f6"], // muted on page
      ["#45564c", "#faf9f6"], // subtle on page
      ["#0e6b3a", "#faf9f6"], // brand link on page
      ["#ffffff", "#0e6b3a"], // primary CTA label
      ["#0e6b3a", "#f1efea"], // brand link on well
      ["#081c15", "#f1efea"], // value on well (item rows, chips)
      ["#35473d", "#f1efea"], // hint on well
      // Light — status pills, tinted banners, solid fills.
      ["#0e6b3a", "#e3f0e8"], // success pill
      ["#7a5a00", "#f7efd2"], // warning banner
      ["#b42318", "#fdecea"], // danger alert
      ["#175cd3", "#eaf1fe"], // info notice
      ["#b42318", "#f1efea"], // danger label on well
      ["#faf9f6", "#7a5a00"], // duplicate-confirm button label
      ["#faf9f6", "#b42318"], // destructive confirm label
      ["#faf9f6", "#081c15"], // toast label on ink
      // Dark — page, card, well.
      ["#f2f7f3", "#12291d"], // ink on card
      ["#c3d6c9", "#12291d"], // muted on card
      ["#a8bfb1", "#12291d"], // subtle on card
      ["#f2f7f3", "#0b1f14"], // ink on well
      ["#c3d6c9", "#0b1f14"], // muted on well
      ["#a8bfb1", "#0b1f14"], // subtle on well
      ["#52b788", "#12291d"], // brand link on card
      ["#0b1f14", "#52b788"], // CTA label on leaf
      // Dark — status pills composited over the card.
      ["#52b788", composite("#52b788", 0.14, "#12291d")], // success
      ["#c9a227", composite("#c9a227", 0.14, "#12291d")], // warning
      ["#f97066", composite("#f97066", 0.12, "#12291d")], // danger
      ["#84adff", composite("#84adff", 0.12, "#12291d")], // info
      ["#f97066", "#12291d"], // danger label on card
      ["#c9a227", "#12291d"], // warning label on card
      ["#081c15", "#c9a227"], // duplicate-confirm button label
      ["#081c15", "#f97066"], // destructive confirm label
    ] as const;

    for (const [text, background] of textPairs) {
      expect(
        ratio(text, background),
        `${text} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("keeps shipped control borders at >= 3:1 against their surface", () => {
    const borderPairs = [
      // Light: input border on paper, strong rule on card.
      ["#7c8a82", "#faf9f6"],
      ["#5a6a61", "#faf9f6"],
      ["#7c8a82", "#f1efea"],
      // Dark: input border on page, strong rule on card.
      ["#6e8a79", "#081c15"],
      ["#8fae9c", "#12291d"],
      ["#6e8a79", "#0b1f14"],
    ] as const;

    for (const [line, surface] of borderPairs) {
      expect(
        ratio(line, surface),
        `${line} on ${surface}`,
      ).toBeGreaterThanOrEqual(3);
    }
  });
});
