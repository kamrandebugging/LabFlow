# LabFlow — Frontend

React 18 + TypeScript + Vite + Tailwind CSS + shadcn/ui Single-Page Application (Doc 07).

## Architectural & Security Invariants

1. **Access Tokens in Memory Only (Doc 01 ADR-005, Doc 07 FP-2, FP-3)**:
   - Access tokens must exist **strictly in runtime memory** (e.g., Zustand in-memory store).
   - **NEVER** write or persist tokens to `localStorage`, `sessionStorage`, or client-accessible cookies.
   - Refresh tokens are handled exclusively via an `httpOnly, Secure, SameSite=Lax` cookie scoped to `/api/v1/auth/`.
   - No token-handling code is included in this scaffold.

2. **Form & Data Layer Conventions (Doc 07 §7, Doc 09 §6)**:
   - **Zod Validation**: All forms must validate inputs using Zod schemas mirroring the backend API shapes.
   - **Server State via TanStack Query**: All server state is managed via React Query (configured with `staleTime: 30s` default, `gcTime: 5m`, `mutation retry: 0`). No parallel manual state in `useState` or Zustand.
   - **User-Friendly Error Mapping**: API errors (problem+json) are mapped to localized, user-friendly copy; raw error codes are never shown directly to users.
   - **Client-Side Validation is UX Only**: Client validation provides immediate user feedback; server-side validation is the authoritative security boundary.

3. **TypeScript Strictness (Doc 09 §6.1)**:
   - `"strict": true` and `"noUncheckedIndexedAccess": true` are enforced.
   - Do NOT disable or weaken these flags.

4. **Internationalization & RTL (Doc 07 §9)**:
   - i18next initialized with `en` (English LTR) and `ur` (Urdu RTL) placeholders.

## Tooling & Quality Scripts

- `npm run dev`: Start Vite local development server (`http://localhost:5173`)
- `npm run build`: Compile TypeScript (`tsc`) and bundle for production (`vite build`)
- `npm run typecheck`: Run strict TypeScript check without emitting files (`tsc --noEmit`)
- `npm run lint`: Run ESLint with zero-warnings gate (`--max-warnings 0`)
- `npm run format:check`: Check code formatting against `.prettierrc`
- `npm run format`: Auto-format source files with Prettier
- `npm run preview`: Preview production build locally
