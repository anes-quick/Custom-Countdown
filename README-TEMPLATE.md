# Tool template – copy this to start a new tool

Copy the **entire contents** of `tool-template` into a **new Cursor project** (or new folder). Then rename the app in the code and add your tool logic.

## What’s inside

- **Frontend:** `index.html` – single-page app, placeholder for your UI and a spot for a shared nav bar later.
- **Backend:** `backend/` – FastAPI app with health check and CORS for Vercel. Add your routes in `backend/app/api/`.
- **Deploy:** `Dockerfile` and `vercel.json` – same pattern as Competitor Upload Checker (Railway + Vercel).

## After copying

1. Rename the app in `index.html` (title, header) and `backend/app/main.py` (title).
2. Set `BACKEND_URL` in `index.html` to your backend URL once deployed (or use the same localhost vs production pattern as in the main tool).
3. Add your API routes in `backend/app/api/__init__.py` and your frontend logic in `index.html`.
4. Push to GitHub, connect to Vercel (frontend) and Railway (backend), deploy. See the main project’s `GITHUB-SETUP.md`, `VERCEL-SETUP.md`, `RAILWAY-SETUP.md` for steps.

## Hosting multiple tools (costs)

- **Vercel (frontend):** Free Hobby plan allows **many projects** (order of hundreds). You can host one frontend per tool at no extra cost.
- **Railway (backend):** Free tier is limited (e.g. 1 project after trial). Options:
  - **One Railway project, multiple services:** Create one project and add one “service” per tool backend. Each service has its own repo or subfolder. That keeps you within one project.
  - **Paid plan:** If you need separate projects per tool, Railway’s paid plan allows more projects; cost scales with usage.

So: multiple **frontends** on Vercel = free. Multiple **backends** = either multiple services in one Railway project (free tier) or multiple projects (paid). Start with one Railway project and one service per tool if possible.

## Later: homepage + navigation

When you’re ready, create a **homepage** (e.g. `yourdomain.com`) that links to each tool. Add a **shared nav bar** (same HTML/JS snippet or component) to every tool’s `index.html` so users can jump between tools and back to the hub. This template leaves a commented “nav placeholder” in the HTML for that.
