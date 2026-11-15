# ServiceConnect

ServiceConnect is a local service booking platform built with FastAPI, SQLAlchemy, MySQL and a responsive HTML/CSS/vanilla JavaScript frontend. Customers can find and book local professionals, providers manage service listings and requests, and administrators oversee approval and platform activity.

## Features

- Customer, provider and administrator roles with JWT sessions and role checks.
- Bcrypt password hashing; authentication tokens are returned as short lived JWTs and set in an HttpOnly cookie. The frontend keeps its bearer token in `sessionStorage` for the browser session.
- Search services by name, category and city; provider profiles show average review scores.
- Provider approval, service management, weekly availability, booking request decisions and status updates.
- Server-side price/duration calculation, future date checks, provider availability checks, overlap prevention, booking cancellation rules and completed-booking-only reviews.
- Admin overview, Chart.js status analytics, user/provider management, bookings, categories and review moderation.
- Historical booking rows preserve the service name, quoted price and address; deactivating a user/service does not erase booking history.

## Stack and layout

```text
backend/
  app/main.py                 FastAPI routes, SQLAlchemy models, validation and booking rules
  app/__main__.py             Optional Python entry point
  tests/test_api.py           API smoke and authorization tests
  requirements.txt
  schema.sql                  MySQL Workbench schema
  .env.example
frontend/
  index.html, login.html, register.html, services.html, service-details.html
  customer/ provider/ admin/  Role workspaces
  css/style.css
  js/api.js, auth.js, booking.js, dashboard.js
postman/ServiceConnect.postman_collection.json
```

## Run locally

Python 3.10+ is recommended. The backend defaults to a local SQLite file so the app can be tried without installing MySQL. For MySQL, create the database with `backend/schema.sql`, then set `DATABASE_URL` as shown below.

1. Create and activate a virtual environment, then install dependencies:

   ```powershell
   cd backend
   py -m venv .venv
   .\.venv\Scripts\Activate.ps1
   pip install -r requirements.txt
   Copy-Item .env.example .env
   ```

2. Edit `.env`. Use a unique random `JWT_SECRET`, valid database credentials and a strong `ADMIN_PASSWORD`. `COOKIE_SECURE=false` is for local HTTP only; enable it behind HTTPS.

   ```dotenv
   DATABASE_URL=mysql+pymysql://serviceconnect:your-password@localhost:3306/serviceconnect_db
   JWT_SECRET=put-a-long-random-secret-here
   JWT_EXPIRE_MINUTES=60
   CORS_ORIGINS=http://localhost:5500,http://127.0.0.1:5500
   COOKIE_SECURE=false
   COOKIE_SAMESITE=lax
   ADMIN_EMAIL=admin@example.com
   ADMIN_PASSWORD=replace-with-a-strong-password
   ```

3. Start the API. On first start SQLAlchemy creates tables and the six service categories. It creates the configured admin account only if that email is not already registered.

   ```powershell
   uvicorn app.main:app --reload
   ```

   Interactive API docs are at `http://127.0.0.1:8000/docs`.

4. Serve the static frontend from the repository root in a second terminal (avoid opening HTML through `file://`):

   ```powershell
   py -m http.server 5500 --directory frontend
   ```

   Open `http://127.0.0.1:5500`. To point a deployed frontend at another API host, define `window.API_BASE` before `js/api.js` on each page (or configure a same-origin proxy). Keep the frontend origin in `CORS_ORIGINS`.

5. Create a customer account from the UI. Register providers from “Join as a provider”; an administrator must approve the provider before they can list bookable services. Sign in at `ADMIN_EMAIL` with the configured `ADMIN_PASSWORD` to use admin pages.

## Database and API

The SQLAlchemy schema is initialized on application startup. `backend/schema.sql` is provided for MySQL Workbench and documents all tables, keys, indexes and historical foreign-key behavior. Configure a managed MySQL service with a private connection URL for deployment.

Key endpoints are under `/api`: `/auth/register`, `/auth/login`, `/auth/me`, `/users/me`, `/categories/`, `/services/`, `/providers/`, `/providers/profile`, `/providers/availability`, `/bookings/`, `/bookings/my`, `/provider/bookings`, `/reviews/`, and `/admin/*`. Use Swagger at `/docs` for request schemas and the full endpoint list. List endpoints accept pagination and relevant search/status filters.

### Booking flow

Register provider → admin approves provider → provider adds service and optional weekly hours → customer books an available future slot → provider accepts/rejects → accepted booking can move to in progress and completed → customer reviews the completed booking. Provider overlap is rechecked at creation and acceptance. MySQL uses a provider row lock during booking insertion; all booking writes are committed in a database transaction.

## Tests

From `backend/` with dependencies installed:

```powershell
pytest -q
```

The suite covers API health, registration/login, current-user identity, admin role protection, provider pending approval visibility and protected endpoints. The SQLite database used by the default configuration is `backend/serviceconnect.db`.

## Deployment

- **Backend (Render):** deploy the `backend` directory as a Python web service. Build command: `pip install -r requirements.txt`; start command: `uvicorn app.main:app --host 0.0.0.0 --port $PORT`. Add production `DATABASE_URL`, `JWT_SECRET`, `JWT_EXPIRE_MINUTES`, `ADMIN_EMAIL`, `ADMIN_PASSWORD`, `COOKIE_SECURE=true`, and the frontend origin in `CORS_ORIGINS`.
- **Frontend:** publish `frontend/` to a static host. Configure `window.API_BASE` to the deployed API base plus `/api`, or put the API behind a same-origin `/api` reverse proxy. Allow the static host's exact HTTPS origin in backend CORS.
- **Database:** use a managed MySQL instance reachable by the backend. Restrict network access, use a least-privileged application account and retain backups. Do not commit `.env`.

Set `COOKIE_SECURE=true` only over HTTPS. Cookie sessions are same-site by default. For cross-site frontend/API hosting, set `COOKIE_SAMESITE=none` and `COOKIE_SECURE=true`, add the exact frontend origin to `CORS_ORIGINS`, and protect cookie-authenticated writes against CSRF. The short lived bearer token in `sessionStorage` also supports authenticated API requests.

## Screenshots

No screenshots are included yet. Run the application and capture the landing page and each role dashboard here when preparing a demo.

## Current implementation notes

This is a runnable starter application with REST API docs and basic workflow tests. For a production launch, add schema migrations (Alembic), rate limiting, audit logs, email verification/password reset, CSRF protection for cross-site cookies, and operational monitoring. No online payments are implemented.
