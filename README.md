# Project Genome Ledger (PGL)

Project Genome Ledger is a production-ready control plane for:

- issuing AI agent birth certificates
- versioning agent genomes
- storing append-only ledger events with hash-chain integrity checks
- tracking ancestry lineage
- enforcing plan-based usage and billing controls

The repository is structured as a deployable module that can be integrated into a larger operating stack such as VEKLM.

## Documentation

- [Docs Index](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\README.md)
- [Operator Manual](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\operator-manual.md)
- [Module Packaging Guide](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\module-packaging.md)
- [Architecture](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\architecture.md)
- [Deployment Operations](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\deployment-operations.md)
- [Security Compliance](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\security-compliance.md)

## Repository Contents

- `backend/` service source
  - `backend/app/main.py` FastAPI app factory and health check
  - `backend/app/routes/*` public APIs
  - `backend/app/services/*` domain services
  - `backend/app/models.py` SQLAlchemy models
  - `backend/app/schemas.py` request and response contracts
  - `backend/tests/` pytest coverage
- `src/` React frontend control plane
- `api/index.py` Vercel entrypoint exporting `app`
- `vercel.json` Vercel routing and build config
- `Dockerfile` and `docker-compose.yml` for container deploys
- `requirements.txt` production dependency set
- `docs/` operating and packaging documentation
- `LICENSE` repository license terms

## Local Runbook

1. Copy the environment template:

```bash
cp .env.example .env
```

2. Install Python dependencies:

```bash
python -m pip install -r requirements.txt
```

3. Install frontend dependencies:

```bash
npm install
```

4. Start the API:

```bash
uvicorn backend.app.main:app --reload
```

5. Start the frontend in a second shell:

```bash
npm run dev
```

6. Verify health:

```bash
curl http://127.0.0.1:8000/health
```

7. Bootstrap the first account:

```bash
curl -X POST http://127.0.0.1:8000/api/v1/admin/bootstrap \
  -H "Content-Type: application/json" \
  -d '{"bootstrap_token":"dev-bootstrap-token","account_name":"Demo","admin_name":"admin@demo.com"}'
```

The bootstrap response contains `api_key`. Pass it in the `x-api-key` header for protected routes.

## Operator Flow

1. Bootstrap the registry with `POST /api/v1/admin/bootstrap`.
2. Store the returned owner `api_key`.
3. Use that key in the `x-api-key` header for protected API routes.
4. Issue an agent through the UI or `POST /api/v1/agents`.
5. Verify the issued asset through:
   - `GET /api/v1/agents`
   - `GET /api/v1/ledger/agents/{agent_id}`
   - `GET /api/v1/ledger/agents/{agent_id}/verify`
   - `GET /api/v1/lineage/tree/{agent_id}`
6. Export compliance and replay artifacts from the frontend rail actions.

The full operator flow is documented in [docs/operator-manual.md](C:\Users\antho\OneDrive\Desktop\Documents\pgl\docs\operator-manual.md).

## Environment Variables

Copy `.env.example` and set at least:

- `API_KEY_SECRET`
- `BOOTSTRAP_ADMIN_TOKEN`
- `DATABASE_URL`
- `STRIPE_WEBHOOK_SECRET` if webhook ingestion is enabled

## API Surface

All API endpoints are rooted at `/api/v1`.

- `POST /admin/bootstrap`
- `POST /admin/accounts/{account_id}/keys`
- `GET /admin/accounts/{account_id}/keys`
- `DELETE /admin/accounts/{account_id}/keys/{api_key_id}`
- `POST /agents`
- `GET /agents`
- `GET /agents/{agent_id}`
- `GET /agents/{agent_id}/certificate`
- `PATCH /agents/{agent_id}/genome`
- `POST /ledger/events`
- `GET /ledger/agents/{agent_id}`
- `GET /ledger/agents/{agent_id}/verify`
- `POST /lineage/fork`
- `GET /lineage/tree/{agent_id}`
- `GET /billing/usage`
- `GET /billing/usage/{metric}/limit`
- `POST /billing/stripe/webhook`

## Deploy on Vercel

Repository already includes:

- `api/index.py` ASGI import for the Vercel Python runtime
- `vercel.json` route and build config

Typical flow:

1. Push to GitHub.
2. Import the project in Vercel.
3. Configure environment variables from `.env.example`.
4. Deploy.

Vercel functions are ephemeral. Production persistence therefore depends on the configured database connection.

## Deployment by Container

From the repository root:

```bash
docker compose up --build
```

This exposes the API on `http://localhost:8000`.

## Tests

Run the backend suite:

```bash
cd backend
python -m pytest -q
```

Build the frontend:

```bash
npm run build
```

## License

See [LICENSE](C:\Users\antho\OneDrive\Desktop\Documents\pgl\LICENSE). This repository is proprietary and may not be reused or redistributed without written authorization.
