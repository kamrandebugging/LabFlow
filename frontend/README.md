# LabFlow — Frontend

React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui SPA.

See [`docs/07-frontend-architecture.md`](../docs/07-frontend-architecture.md) for frontend specifications and guidelines.

---

## Security Invariants

> [!CAUTION]
> **ADR-005 / Doc 07 FP-2 & FP-3 — Access Token Storage Rule**
>
> Access tokens **MUST** live in memory only. They must **NEVER** be written to:
> - `localStorage`
> - `sessionStorage`
> - Any client-accessible cookie (only `HttpOnly`, `Secure`, `SameSite=Strict` cookies are permitted for the refresh token, set by the server)
>
> Violating this rule exposes tokens to XSS attacks. No exceptions.

---

## Tech Stack

| Tool | Version | Purpose |
|---|---|---|
| React | 18.x | UI library |
| TypeScript | 5.x (strict) | Type safety (`strict: true`, `noUncheckedIndexedAccess: true`) |
| Vite | 5.x | Build tool & dev server |
| Tailwind CSS | 3.x | Utility-first styling |
| shadcn/ui | CSS-variables | Headless UI component primitives |
| i18next | 23.x | Internationalisation (English LTR + Urdu RTL) |

---

## TypeScript Strictness

`tsconfig.json` enforces:
- `"strict": true` — enables all strict type-checking flags
- `"noUncheckedIndexedAccess": true` — array/object index access returns `T | undefined`

**Neither flag may be disabled or weakened** at any point in the project lifecycle.

---

## Internationalisation (i18n)

The app supports two locales per Doc 07 §9:

| Locale | Language | Direction |
|---|---|---|
| `en` | English | LTR |
| `ur` | Urdu | RTL |

Translation resource files are bootstrapped as stubs in `src/i18n.ts`.
Real translation strings are added in LAB-38.

---

## Design Tokens

Defined as Tailwind CSS custom properties in `src/index.css`:

| Token | Value | Usage |
|---|---|---|
| Primary | `#0d9488` (teal-600) | Brand colour, buttons, links |
| Accent | `#e8a33d` (amber) | Highlights, CTAs |
| Neutrals | Slate scale | Backgrounds, text, borders |

---

## Available Scripts

```bash
npm run dev       # Start Vite dev server
npm run build     # Type-check + production build → dist/
npm run lint      # ESLint — zero warnings gate
npm run preview   # Preview production build locally
```

---

## Money Display Rule

Per Doc 01 ADR-010: monetary values are `Decimal` / `numeric(12,2)` on the server.
The frontend **must display server-provided strings verbatim** — no float arithmetic,
no client-side currency formatting libraries that convert to float internally.
