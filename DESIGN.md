# Veyla Design Tokens & System Specification

> Single source of truth for the Veyla look-and-feel across LabFlow.
> Established in Batch 0 (Owner Dashboard & Tenant Shell pilot).

---

## 1. Design Principles

- **Soft Elevation over Hard Borders**: Containers and cards rely on subtle background contrast (`#FEFFFF` on `#EAECEC`) and soft ambient diffusion shadows rather than heavy border outlines.
- **Geometric Sans Typography**: Inter sans-serif throughout. Page titles are prominent and bold with a one-line muted subtitle.
- **Pill Geometry**: Fully rounded pills (`rounded-full`, 9999px) for buttons, status badges, chips, and quick-action triggers.
- **Cards & Containers**: Generous 12–16px border radiuses (`rounded-xl` / `rounded-2xl`).
- **Semantic Risk Flip in Dark Mode**: Dark mode is not a naive color inversion. In light mode, the highest-risk/worst-status convention uses near-black (`#121011`) with white text. In dark mode, this flips semantically to crisp white (`#FFFFFF`) with near-black text (`#121011`).
- **Flat Loading States**: Strictly flat gray skeleton blocks. No shimmer animations (banned per LabFlow core quality rules).

---

## 2. Core Palette

### 2.1 Light Mode (Primary)

| Token | CSS Variable | Hex / Value | Usage | WebAIM Contrast |
|---|---|---|---|---|
| Page Background | `--color-bg` / `--veyla-page` | `#EAECEC` | Page canvas & body surface | 13.8:1 with text |
| Card Surface | `--color-surface` / `--veyla-card` | `#FEFFFF` | Cards, panels, modals | 15.6:1 with text |
| Card Well / Elevated | `--color-well` / `--veyla-well` | `#F4F6F6` | Inner card sections, table headers, stat wells | 12.5:1 with text |
| Near-Black (Brand/Worst) | `--color-text` / `--veyla-black` | `#121011` | Primary headings, worst-state chip fill, "+ New" button | 15.6:1 on card |
| Body Text | `--color-body` / `--veyla-body` | `#242626` | Normal body copy, table cells | 14.8:1 on card |
| Muted Text | `--color-text-muted` / `--veyla-muted` | `#596060` | Subtitles, labels, secondary metadata | 5.7:1 on card (≥ 4.5:1) |
| Subtle Border | `--color-border` / `--veyla-border` | `rgba(18, 16, 17, 0.08)` | Hairline dividers, soft card outline | Non-text boundary |
| Teal Accent | `--color-accent` / `--veyla-teal` | `#CAE2E0` | Active nav indicator, secondary pills, brand accents | 13.5:1 with black text |
| Teal Accent Dark Text | `--color-accent-text` | `#133835` | Text placed on teal accent tint | 6.8:1 on `#CAE2E0` |

### 2.2 Dark Mode

Applied via `data-theme="dark"` on `<html>`. Activated via circular-reveal view transition.

| Token | CSS Variable | Hex / Value | Usage | WebAIM Contrast |
|---|---|---|---|---|
| Page Background | `--color-bg` | `#111213` | Dark body background | 13.2:1 with text |
| Card Surface | `--color-surface` | `#191B1C` | Cards, panels, sidebar | 12.8:1 with text |
| Card Well / Elevated | `--color-well` | `#222526` | Inner sections, chip backgrounds | 11.0:1 with text |
| Semantic Worst Flip | `--color-veyla-worst-bg` | `#FFFFFF` | Worst-state chip fill (flips black to white) | 16.5:1 with black text |
| Semantic Worst Text | `--color-veyla-worst-text` | `#121011` | Text on worst-state chip in dark | 16.5:1 |
| Text Primary | `--color-text` | `#F1F2F2` | Headings, primary values | 13.2:1 on card |
| Text Body | `--color-body` | `#E1E4E4` | Standard copy | 11.8:1 on card |
| Text Muted | `--color-text-muted` | `#9EA3A3` | Subtitles, labels | 5.4:1 on card (≥ 4.5:1) |
| Subtle Border | `--color-border` | `rgba(255, 255, 255, 0.08)` | Hairlines, card borders | Non-text boundary |
| Teal Accent Surface | `--color-accent` | `#233B39` | Dark teal container | 4.8:1 with dark surface |
| Teal Accent Text | `--color-accent-text` | `#A4DFDA` | Teal label / icon in dark | 7.4:1 on dark surface |

### 2.3 Status Colors (LabFlow Specific)

| Status Category | Light Fill | Light Text | Dark Fill | Dark Text | Semantic Purpose |
|---|---|---|---|---|---|
| **Ready / Approved** | `#E6F4EA` | `#0E6B3A` | `rgba(82, 183, 136, 0.16)` | `#7CD3A2` | Ready for dispatch / approved |
| **In Process / Review** | `#FEF3D6` | `#8C5800` | `rgba(232, 163, 61, 0.16)` | `#F6C776` | Bench testing / pending approval |
| **Received / Transit** | `#E0F2FE` | `#0369A1` | `rgba(56, 189, 248, 0.16)` | `#7DD3FC` | Received at central accessioning |
| **Collected / Draft** | `#EAECEC` | `#374151` | `rgba(156, 163, 175, 0.18)` | `#D1D5DB` | Sample drawn / draft status |
| **Critical / Rejected** | `#FEE2E2` | `#B91C1C` | `rgba(239, 68, 68, 0.18)` | `#FCA5A5` | Critical value / sample rejected |
| **Worst State / Immediate** | `#121011` | `#FFFFFF` | `#FFFFFF` | `#121011` | Veyla signature semantic flip |

---

## 3. Typography

- **Font Family**: Inter, system-ui, sans-serif
- **Font Mono**: Tabular numeric values (`font-variant-numeric: tabular-nums`)
- **Page Titles**: `font-bold` (700) or `font-extrabold` (800), `clamp(24px, 2.5vw, 32px)`, `tracking-tight`
- **Section Headings**: `font-bold` (700), `18px–20px`
- **Card Subtitles**: `font-medium` (500), `14px`, `color: var(--color-text-muted)`
- **Data Figures (KPI)**: `font-bold` (700), `32px–40px`, tabular lining figures

---

## 4. Radiuses & Geometry

```css
--radius-card: 16px;       /* 1rem / rounded-2xl */
--radius-panel: 14px;      /* 0.875rem */
--radius-pill: 9999px;     /* rounded-full */
--radius-button: 9999px;   /* buttons are always pill-shaped */
--radius-chip: 9999px;     /* status chips are always pill-shaped */
--radius-sm: 8px;          /* inner tiles, waffle squares */
```

---

## 5. Shadows & Elevation

```css
/* Ambient, multi-stop diffusion shadows */
--shadow-veyla-card: 0 1px 3px rgba(18, 16, 17, 0.04), 0 6px 16px rgba(18, 16, 17, 0.04);
--shadow-veyla-hover: 0 4px 12px rgba(18, 16, 17, 0.08), 0 12px 28px rgba(18, 16, 17, 0.06);
--shadow-veyla-dropdown: 0 8px 24px rgba(18, 16, 17, 0.12), 0 2px 6px rgba(18, 16, 17, 0.06);
--shadow-veyla-pill: 0 1px 2px rgba(18, 16, 17, 0.08);

/* Dark theme elevations */
[data-theme="dark"] {
  --shadow-veyla-card: 0 1px 3px rgba(0, 0, 0, 0.35), 0 6px 20px rgba(0, 0, 0, 0.25);
  --shadow-veyla-hover: 0 4px 16px rgba(0, 0, 0, 0.45);
  --shadow-veyla-dropdown: 0 8px 32px rgba(0, 0, 0, 0.55);
}
```

---

## 6. Icons & Stroke

- Outlined stroke icons only (`material-symbols-outlined` or crisp SVG strokes).
- Standard sizing: 16px–20px (`text-[18px]` to `text-[20px]`).
- Bounded inside circular or rounded-lg soft containers when standalone.

---

## 7. Skeleton / Loading States

- Plain solid flat gray blocks:
  - Light: `bg-[#E2E5E5]`
  - Dark: `bg-[#282B2C]`
- **Strictly NO shimmer or moving gradient**.
- `animation: none;` per LabFlow core performance and motion guidelines.

---

## 8. Motion

Motion is CSS + the View Transitions API only. No motion library is used.

### 8.1 Tokens

```css
--motion-fast: 150ms;      /* value cross-fades, row hover */
--motion-base: 200ms;      /* modals, backdrops, drawer exit, toasts */
--motion-drawer: 280ms;    /* drawer entry */
--motion-theme: 500ms;     /* circular theme reveal */
--ease-out: cubic-bezier(0.22, 1, 0.36, 1);
--ease-in-out: cubic-bezier(0.65, 0, 0.35, 1);
```

Component CSS must not hard-code a duration or curve; it resolves these
tokens. Tokens are durations and easings only — never colour.

### 8.2 Shared implementations

- Theme reveal: `src/lib/motion.ts` → `revealThemeChange`. One helper for
  every trigger. Falls back to an instant swap when
  `document.startViewTransition` is unavailable.
- Drawer, modal and backdrop transitions: the `.veyla-drawer-*`,
  `.veyla-modal-*` utilities in `index.css`. No component module duplicates
  the keyframes.
- Value cross-fade: `src/components/ui/FadeValue.tsx` (150ms opacity).

### 8.3 Reduced motion

`@media (prefers-reduced-motion: reduce)` removes every animation and
transition globally, including the theme reveal. Nothing is shortened to a
near-zero duration: reveals, staggers and blurs do not run at all.

### 8.4 Banned in this system

- Count-up numbers, bounce / elastic / back easings.
- Shimmer, blur-to-sharp transitions and whole-page cross-fades.
- Duplicate animation implementations per screen.
