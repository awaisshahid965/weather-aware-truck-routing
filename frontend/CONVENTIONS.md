# Frontend conventions

Rules for code in `frontend/`. Tools enforce most of them. Reviews enforce the rest.

## Structure

```text
src/
├── app/                        Routes only. Thin: compose shared components.
├── context/<name>/             Shared state, one folder per context
│   ├── <name>.interface.ts     The <Name>ContextValue interface
│   ├── <name>.context.ts       createContext + use<Name>Context hook
│   └── <name>.container.tsx    Owns the state, calls services, renders the provider
└── shared/
    ├── components/<name>/      Composed, product-aware components
    ├── ui/<name>/              Generic controls with no product knowledge (button, input, select)
    ├── services/               API access: http-client.ts + one service per resource
    ├── types/                  Shared types and API data shapes
    ├── utils/                  Pure helpers
    └── config/                 app-config.ts: the only reader of process.env
tests/                          Shared test setup, fixtures, factories
```

## Component folders

One component per folder, named after the component. Its files sit together:

| File | Holds |
|---|---|
| `route-card.tsx` | The component (default export) |
| `route-card.types.ts` | Props interface and closed sets |
| `route-card.styles.ts` | Tailwind class maps for variants |
| `route-card.utils.ts` | Pure helpers used only here |
| `route-card.test.tsx` | Tests |
| `hooks/use-route-card.ts` | The component's own logic, as a hook (default export) |
| `route-card-header/` | A sub-component, in its own folder |

## Naming

| Thing | Style | Example |
|---|---|---|
| File, folder | `kebab-case` | `route-card.tsx`, `use-trip-planner.ts` |
| Component | `PascalCase` | `RouteCard` |
| Hook | `use` + `PascalCase` | `useTripPlanner` |
| Function, variable | `camelCase` | `formatEta` |
| Constant | `UPPER_SNAKE_CASE` | `API_BASE_URL` |
| Type, interface | `PascalCase`, no `I` prefix | `RoutePlan` |
| Props | `<Component>Props` | `RouteCardProps` |
| Context value | `<Name>ContextValue` | `TripContextValue` |
| Service class | `<Resource>Service` | `TripService` |

## Components

- Write components as typed arrow functions, then export them as the default:

  ```tsx
  const RouteCard: FC<RouteCardProps> = ({ route }) => {
      return <article>{route.label}</article>
  }

  export default RouteCard
  ```

- Route files in `app/` use `export default function Page()`, as Next.js expects.
- Components are Server Components by default. Add `'use client'` only to the component that needs state, effects, or browser APIs, as deep in the tree as possible. Never add it to `layout.tsx`.
- Components that use browser-only libraries, such as MapLibre, load on the client only.
- Keep components mostly markup. Move logic into `hooks/use-<name>.ts`.

## Exports and imports

- Default export: components, hooks, service classes.
- Named exports: types, constants, context objects with their `use<Name>Context` hooks, utilities.
- Use `@/` for anything outside the current component folder: `import TripService from '@/shared/services/trip-service'`.
- Use relative imports only inside the same component folder: `import { routeCardClasses } from './route-card.styles'`.
- Use `import type` for type-only imports. ESLint enforces it.

## Types

- `interface` for object shapes. `type` for unions and aliases.
- Closed sets are string-literal unions. When the values are needed at runtime, derive the type from an `as const` array:

  ```ts
  export const BUTTON_VARIANTS = ['primary', 'secondary'] as const
  export type ButtonVariant = (typeof BUTTON_VARIANTS)[number]
  ```

- No TypeScript `enum`. Unions are erased at build time and match the strings the API sends.
- No `any`. Use `unknown` and narrow it.
- TypeScript is strict, plus `noUncheckedIndexedAccess` and `exactOptionalPropertyTypes`.

## State

- Keep state local until two distant components need it. Then lift it into a context.
- A context lives in `context/<name>/`, split into three files:
  - `<name>.interface.ts`: the `<Name>ContextValue` interface.
  - `<name>.context.ts`: `createContext<<Name>ContextValue | null>(null)`, plus a `use<Name>Context()` hook. The hook throws a clear error when used outside the provider.
  - `<name>.container.tsx`: a client component that owns the state, calls services, and renders the provider.

## Services and data

- Components never call `fetch`. Services do.
- `shared/services/http-client.ts` is a base class with protected static request helpers. Each resource gets a service class that extends it, with static methods: `TripService.createPlan(request)`.
- Each service keeps its endpoint paths in one constant object.
- Services turn API responses into the app's types and throw typed errors. Components never parse raw JSON.
- Configuration comes from `shared/config/app-config.ts` only.

## Styling

- Use Tailwind utility classes in JSX.
- Variants live in `<name>.styles.ts`, as maps keyed by a union type:

  ```ts
  export const buttonVariantClasses: Record<ButtonVariant, string> = {
      primary: 'bg-sky-600 text-white hover:bg-sky-700',
      secondary: 'bg-neutral-200 text-neutral-900 hover:bg-neutral-300',
  }
  ```

- Never build class names from fragments such as `` `bg-${color}-500` ``. Tailwind ships only classes it finds written out in full.
- Use rem-based sizes. Keep the browser's default root font size, so user font settings still work.

## Errors

- Show the user what went wrong and what to do next. Never swallow an error silently.
- Use only `console.warn` and `console.error`. ESLint blocks `console.log`.

## Tests

- Vitest, React Testing Library, and user-event. Test files sit next to the code: `route-card.test.tsx`.
- Query the way a user would: by role, label, or text. Use test IDs only when nothing else works.
- Tests never touch the network. Mock the service, not `fetch`.
- `tests/` holds shared setup, fixtures, and factories.

## Comments

Explain why, never what. No commented-out code.

## Formatting

Prettier formats all code and config: 4-space indents (2 for JSON and YAML), single quotes, no semicolons, trailing commas, 120 columns, LF. Markdown is left as written. Run `npm run format`. ESLint covers correctness: `npm run lint:fix`.
