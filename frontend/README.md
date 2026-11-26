# Renze AI Monitoring — frontend

Next.js (App Router, Turbopack) + TypeScript + Tailwind CSS. Frontend only for now:
auth and data are mocked on the client; nothing calls the backend yet.

## Run

```bash
cd frontend
npm install
npm run dev          # http://localhost:3000
```

`/` redirects to `/login`. Any non-empty username and password sign in and go to `/diagram`.

## Layout

```
app/
  page.tsx             redirect / → /login
  login/page.tsx       centered login card
  diagram/page.tsx     interactive plant diagram
components/
  LoginForm.tsx        controlled form, inline validation, mock login → /diagram
  DiagramView.tsx      header, route guard, selection state
  InteractiveDiagram.tsx  inline SVG; hover = red glow, click/tap/Enter = select
  ComponentInfoPanel.tsx  shows the selected component's name
data/
  diagramComponents.ts typed registry (id, name, category, notes)
lib/
  auth.ts              mock login/logout + useSession (sessionStorage)
  api.ts               mocked data functions → future FastAPI calls
  config.ts            API_BASE_URL (NEXT_PUBLIC_API_BASE_URL)
```

## Wiring the backend later

- `lib/auth.ts` → `login()` has the `POST /api/login` call as a TODO.
- `lib/api.ts` → `GET /api/components` and `GET /api/components/{id}` TODOs.
- Copy `.env.example` to `.env.local` and set `NEXT_PUBLIC_API_BASE_URL`.
- The route guard is client-side (`DiagramView.tsx`); with cookie auth it can move to
  `proxy.ts` (Next 16's name for middleware).

## Diagram

`components/InteractiveDiagram.tsx` redraws `Renze_site_layout.pdf` as inline SVG
(coordinates match the PDF rendered at 1334 × 750 px), with the settling pond
(沉澱池) drawn as the pressurized buffer vessel. Labels are bilingual.

- Each component in `SHAPES` is keyed by its id in `data/diagramComponents.ts`;
  TypeScript flags any id without a shape.
- Hover/focus glow, selection outline and animations are in `app/globals.css`
  (`.diagram-part`, `.plant-diagram`). Animations stop under
  `prefers-reduced-motion`.
