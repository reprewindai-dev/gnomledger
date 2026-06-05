# Project Genome Ledger (PGL)

Project Genome Ledger is a production-ready FastAPI control plane for:

- issuing AI agent birth certificates,
- versioning genomes,
- storing append-only ledger events with hash-chain integrity checks,
- tracking ancestry lineage, and
- enforcing plan-based usage/billing controls.

The system is ready to run locally and deploy on Vercel-like free tiers.

## Repository Contents

- `backend/` service source:
  - `backend/app/main.py` FastAPI app factory and health check
  - `backend/app/routes/*` public APIs
  - `backend/app/services/*` domain services
  - `backend/app/models.py` SQLAlchemy schemas
  - `backend/app/schemas.py` request/response contracts
  - `backend/tests/` pytest coverage
- `api/index.py` Vercel entrypoint that exports `app`
- `vercel.json` Vercel routing/build config
- `Dockerfile` and `docker-compose.yml` for container deploys
- `requirements.txt` production dependency set
- `docs/` architecture and operating notes

## Local Runbook

1. Copy environment template:

```bash
cp .env.example .env
```

2. Install dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Start the API:

```bash
uvicorn backend.app.main:app --reload
```

4. Verify service health:

```bash
curl http://127.0.0.1:8000/health
```

5. Bootstrap the first account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"bootstrap_token":"dev-bootstrap-token","account_name":"Demo","admin_name":"admin@demo.com"}'
```

The response contains `api_key`. Pass this as `x-api-key` for protected routes.

## Environment Variables

Copy `.env.example` and set at least:

- `API_KEY_SECRET`
- `BOOTSTRAP_ADMIN_TOKEN`
- `DATABASE_URL`
- `STRIPE_WEBHOOK_SECRET` (if webhook ingestion is enabled)

## API Surface

All API endpoints are rooted at `/api/v1`.

- `POST /admin/bootstrap` one-time bootstrap flow
- `POST /admin/accounts/{account_id}/keys` issue API key
- `GET /admin/accounts/{account_id}/keys` list API keys
- `DELETE /admin/accounts/{account_id}/keys/{api_key_id}` revoke API key
- `POST /agents` register agents and issue certificate
- `GET /agents` list agents
- `GET /agents/{agent_id}` read agent detail
- `GET /agents/{agent_id}/certificate` read certificate artifact path
- `PATCH /agents/{agent_id}/genome` mutate genome version
- `POST /ledger/events` append ledger event (idempotent by key)
- `GET /ledger/agents/{agent_id}` fetch event stream
- `GET /ledger/agents/{agent_id}/verify` validate chain integrity
- `POST /lineage/fork` create derived agent lineage
- `GET /lineage/tree/{agent_id}` render lineage (billed by metric)
- `GET /billing/usage` read usage records
- `GET /billing/usage/{metric}/limit` read quota limits
- `POST /billing/stripe/webhook` Stripe webhook consumer

## Deploy on Vercel

Repository already includes:

- `api/index.py` ASGI import for Vercel Python runtime.
- `vercel.json` route + build config.

Typical flow:

1. Push to GitHub.
2. Import project in Vercel.
3. Configure environment values from `.env.example`.
4. Deploy.

Vercel functions have ephemeral storage; this build expects either managed database backing or SQLite for dev.

## Deployment by Container

From root:

```bash
docker compose up --build
```

This exposes the API on `http://localhost:8000`.

## Tests

Run the full backend suite:

```bash
cd backend
pytest -q
```

## License

Proprietary – all rights reserved.
