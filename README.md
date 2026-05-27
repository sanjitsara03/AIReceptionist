# AI Receptionist

A multi-tenant AI receptionist for home-service businesses (plumbing, HVAC, electrical). Customers text or call a Twilio number; an LLM agent handles the conversation, books real appointments in the database, and updates the owner's dashboard in real time. One deployment serves many businesses, each with their own number, services, pricing, and personality prompt.

<img width="1920" height="988" alt="AIR - settings" src="https://github.com/user-attachments/assets/93502b75-28a2-42fc-8ae7-049ab1732e06" />
<img width="1920" height="986" alt="AIR - jobs" src="https://github.com/user-attachments/assets/ff0c05e7-1f6b-48b6-8fcf-4b6b8edb412f" />
<img width="1920" height="987" alt="AIR - Dashboard" src="https://github.com/user-attachments/assets/55daefce-a151-4a76-b65c-a65e63350fea" />
<img width="1920" height="986" alt="AIR - customer" src="https://github.com/user-attachments/assets/06d4e670-78e6-492e-9ac1-f22b2bf2f0d1" />
<img width="1920" height="986" alt="AIR - conversations" src="https://github.com/user-attachments/assets/8432a736-7e52-48df-bf79-d4d595fc9697" />



---

## What it does

- **Inbound SMS and voice booking.** A customer texts or calls the business's Twilio number. The agent checks availability, confirms a slot in plain language, and writes the job + tech assignment to Postgres.
- **Multi-tenant dashboard.** Owners log in (Auth0) and see today's KPIs, jobs, customers, conversations, and technicians for their business only.
- **Live updates.** Server-Sent Events push job/conversation changes to the dashboard, so when the agent books an appointment on a phone call, the owner sees the new card appear without refreshing.
- **Automated follow-ups.** APScheduler sends 24-hour reminder texts, flips genuine no shows, and logs a daily digest per business.

---

## Architecture

```
                  ┌──────────────┐
   SMS / Voice → │   Twilio     │ ──signed webhooks──┐
                  └──────────────┘                    │
                                                      ▼
   ┌──────────────────────────────────────────────────────────────────┐
   │                          FastAPI app                              │
   │  ┌─────────────┐   ┌──────────────────┐   ┌──────────────────┐   │
   │  │  /webhooks  │ → │  PydanticAI      │ → │  Postgres        │   │
   │  │  (SMS/Voice)│   │  agent + tools   │   │  (jobs, slots,   │   │
   │  └─────────────┘   │  - book_job      │   │   customers,     │   │
   │                    │  - reschedule    │   │   conversations) │   │
   │  ┌─────────────┐   │  - cancel_*      │   └──────────────────┘   │
   │  │  Dashboard  │   │  - list_appts    │            ▲             │
   │  │  REST API   │   └──────────────────┘            │             │
   │  │  + SSE      │            │                Auth0 JWT           │
   │  └─────────────┘            ▼                  validation        │
   │                    ┌──────────────────┐                          │
   │                    │  Claude API      │                          │
   │                    └──────────────────┘                          │
   │  ┌──────────────────────────────────────────────────────────┐    │
   │  │  APScheduler — reminders, no-shows, daily digest         │    │
   │  └──────────────────────────────────────────────────────────┘    │
   └──────────────────────────────────────────────────────────────────┘
            │                                              │
            ▼                                              ▼
       Sentry                                    React + Vite dashboard
                                                 (Auth0 SPA, SSE client)

   Hosted on Railway: backend container + Postgres + Redis + frontend static.
```

---

## Tech stack

| Layer | Choice |
|---|---|
| Backend | Python 3.12, FastAPI, async SQLAlchemy 2.0, Alembic |
| Database | PostgreSQL |
| Cache / queue | Redis |
| AI | Claude Sonnet 4.6 via PydanticAI|
| Telephony | Twilio SMS + Voice |
| Auth | Auth0 |
| Background | APScheduler |
| Real-time | Server-Sent Events with in-memory broker |
| Frontend | React 18, Vite, custom CSS with design tokens |
| Infra | Docker, Railway (backend + frontend + Postgres + Redis) |
| Observability | Sentry (FastAPI integration + tool-call breadcrumbs) |
| Testing | Pytest async + asgi-lifespan + httpx ASGI transport (67 tests) |

---

## Notable engineering details

- **Tenant isolation by JWT, not query param.** Every dashboard route depends on `get_current_business_id`, which validates the Auth0 token against cached JWKS and resolves the business from `owner_auth0_id`. Tests include cross tenant guards so a token for business A cannot read business B's data.
- **Signature-validated webhooks.** Every Twilio webhook is rejected unless the `X-Twilio-Signature` header matches the HMAC over the exact URL + form body. Strict mode locks the validator to `WEBHOOK_BASE_URL` to remove the X-Forwarded-Host forge-vector behind Railway's proxy.
- **Cost-controlled agent.** PydanticAI runs with `UsageLimits(request_limit=8, total_tokens_limit=15000)` per turn. A per-business daily message cap (PT-anchored) skips the LLM and replies with a polite limit message if exceeded.
- **Tool-call traceability.** Every agent run logs the actual tool calls + returns to Sentry breadcrumbs and Railway logs, so "the agent said it cancelled" can be verified vs. "the agent actually called `cancel_job`."
- **Hallucination-resistant prompt.** Operational rules explicitly forbid the agent from claiming a booking/cancellation/reschedule unless the corresponding tool was called in this turn and returned success.
- **Healthcheck-friendly migrations.** Alembic runs on every Railway deploy via `preDeployCommand`. The container only starts serving once migrations apply cleanly.

---

## Local setup

Requirements: Python 3.12, `uv`, Node 20+, Docker.

```bash
# 1. Postgres + Redis
docker compose up -d

# 2. Backend
uv sync
cp .env.example .env   # then fill in Twilio, Auth0, Anthropic keys
.venv/bin/alembic upgrade head
.venv/bin/python seed.py            # creates Joe's Plumbing demo data
.venv/bin/uvicorn app.main:app --reload

# 3. Frontend 
cd frontend
cp .env.local.example .env.local    # Auth0 SPA + API base URL
npm install
npm run dev

# 4. Tests
.venv/bin/pytest
```

Visit `http://localhost:5173`, log in via Auth0, and you'll see the seeded business's dashboard.

To test the Twilio webhooks locally, use `ngrok http 8000` and point your Twilio number's SMS + Voice webhooks at `https://<ngrok>.ngrok.io/webhooks/sms` and `/webhooks/voice`.

---

## Repo tour

```
app/
├── main.py                 # FastAPI entry, CORS, Sentry, lifespan
├── config.py               # Pydantic settings + PT timezone helpers (BUSINESS_TZ, fmt_pt, pt_today_bounds)
├── auth.py                 # Auth0 JWT validation, JWKS cache w/ first-fetch lock
├── database.py             # Async engine, session factory
├── models.py               # SQLAlchemy ORM (businesses, customers, jobs, slots, conversations, messages, invites)
├── schemas.py              # Pydantic request/response schemas
├── events.py               # In-memory SSE pub/sub broker (per-business queues)
├── scheduler.py            # APScheduler — reminders, no-shows, daily digest (PT cron)
├── agent/
│   ├── agent.py            # PydanticAI agent setup, system prompt, tool-call logging
│   └── tools.py            # check_availability, book_job, reschedule_job, cancel_job, cancel_all_jobs, list_my_appointments
├── routes/
│   ├── webhooks.py         # Twilio SMS + Voice handlers (signature validation, daily cap)
│   ├── auth.py             # /auth/me, /auth/claim (invite-token gated)
│   ├── invites.py          # admin-secret-gated invite creation
│   ├── businesses.py       # GET/PATCH /businesses/me
│   ├── jobs.py             # CRUD + reschedule + status
│   ├── timeslots.py        # CRUD + bulk recurring (PT-anchored)
│   ├── customers.py        # list + get + search
│   ├── technicians.py      # CRUD
│   ├── conversations.py    # list + get
│   ├── dashboard.py        # /summary + /feed
│   ├── events.py           # GET /events/stream (SSE)
│   └── admin.py            # admin-secret-gated business deletion
├── services/
│   └── conversation.py     # get_or_create_*, save_message, load_history (capped + 7-day staleness)
└── middleware/errors.py    # Global exception → envelope handler

frontend/
└── src/
    ├── App.jsx             # Auth0Provider + DataProvider + routing
    ├── DataContext.jsx     # Loads data, SSE subscription, PT formatters
    ├── api.js              # Fetch helpers (VITE_API_BASE)
    ├── components/         # LoginPage, Shell, TweaksPanel
    └── views/              # TodayView, JobsView, CustomersView, ConversationsView, SettingsView

tests/                      # 67 integration tests (isolated test DB)
alembic/                    # DB migrations (auto-run on Railway deploy)
```

---

