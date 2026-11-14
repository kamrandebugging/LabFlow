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

describe("Owner dashboard neumorphism tokens", () => {
  it("keeps the touched CSS modules free of literal colours", () => {
    for (const file of [
      "../../features/dashboard/OwnerDashboardScreen.module.css",
      "../../features/layout/TenantLayout.module.css",
    ]) {
      const css = read(file);
      expect(css, `${file} hex`).not.toMatch(/#[0-9a-fA-F]{3,8}\b/);
      expect(css, `${file} rgb`).not.toMatch(/\brgba?\(/);
      expect(css, `${file} hsl`).not.toMatch(/\bhsla?\(/);
    }
  });

  it("ships status text at >= 4.5:1 on its tint in both themes", () => {
    const pairs = [
      // light
      ["#0e6b3a", "#e3f0e8"],
      ["#7a5a00", "#f7efd2"],
      ["#b42318", "#fdecea"],
      ["#175cd3", "#eaf1fe"],
      // dark: rgba tints composited over the dark card #12291d
      ["#52b788", composite("#52b788", 0.14, "#12291d")],
      ["#c9a227", composite("#c9a227", 0.14, "#12291d")],
      ["#f97066", composite("#f97066", 0.12, "#12291d")],
      ["#84adff", composite("#84adff", 0.12, "#12291d")],
    ] as const;
    for (const [text, background] of pairs) {
      expect(
        ratio(text, background),
        `${text} on ${background}`,
      ).toBeGreaterThanOrEqual(4.5);
    }
  });

  it("defines the approved status tokens in both themes", () => {
    const tokens = read("../../theme/tokens.css");
    for (const token of [
      "--color-success",
      "--color-success-tint",
      "--color-warning",
      "--color-warning-tint",
      "--color-danger",
      "--color-danger-tint",
      "--color-info",
      "--color-info-tint",
    ]) {
      expect(tokens).toContain(token);
    }
    expect(tokens).toContain('[data-theme="dark"]');
  });
});
