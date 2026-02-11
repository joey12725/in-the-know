# ITK Frontend

Next.js App Router frontend for `itk.so`.

## Scripts

```bash
npm run dev
npm run build
npm run start
npm run lint
```

## Environment

- `BACKEND_API_URL`: FastAPI origin (used by route-handler proxy)
- `NEXT_PUBLIC_APP_URL`: public app URL for links/callback flow

## Key routes

- `/`: SB7 landing page
- `/onboarding`: multi-step onboarding wizard
- `/api/*`: proxy to FastAPI backend
