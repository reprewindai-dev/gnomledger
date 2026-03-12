# Build Scope & Implementation Assets

This document captures the deliverables required to ship a production-grade Project Genome Ledger release that investors can experience end-to-end.

## Backend Deliverables

1. **FastAPI Application (`backend/app`)**
   - `main.py`: ASGI bootstrap, middleware (auth, rate limiting, tracing), router registration.
   - `config.py`: Settings management (Pydantic BaseSettings) for database URLs, Stripe keys, auth providers, storage buckets.
   - `database.py`: SQLAlchemy 2.0 engine, session dependency, Alembic integration.
   - `models.py`: ORM definitions for accounts, users, agents, genomes, certificates, ledger events, lineage edges, billing usage, incidents, deployments, test results.
   - `schemas.py`: Pydantic response/request models with strict validation and field-level documentation.
   - `services/*`: Domain logic split into certificate, genome, ledger, lineage, billing, analytics modules with transactional guards and hash verifications.
   - `routes/*`: Public API endpoints with RBAC dependencies, idempotency enforcement, and request auditing.
   - `auth/`: JWT validation, API key verification, RBAC policies.

2. **Billing & Analytics Hooks**
   - Stripe webhook consumer storing invoice and payment events.
   - Usage metering job (Celery/Temporal/Lambda) that aggregates ledger bytes and lineage renders nightly.
   - Analytics event publisher (OpenTelemetry exporter + warehouse sink) capturing certificate issuance, incidents, and account upgrades.

3. **Seed Data & Demo Scripts**
   - `scripts/seed_demo.py`: Seeds Alpha/Beta agents, incidents, deployments, and lineage relationships mirroring the prototype narrative.
   - `scripts/demo_walkthrough.md`: Step-by-step console/API commands for investors to replay lifecycle events.

4. **Testing**
   - Pytest suite covering registry workflows, ledger immutability, lineage DAG generation, billing quota enforcement.
   - Contract tests for Stripe webhooks and Auth0 JWT parsing using recorded fixtures.

## Frontend Deliverables (Next.js App)

1. **Dashboard Shell**
   - Secure layout with role-aware navigation (Registry, Ledger, Lineage, Billing, Investor Mode).
   - Announcement banner for compliance updates.

2. **Create Agent / Issue Birth Certificate**
   - Wizard collecting genome fields, showing real-time hash preview, enforcing pricing tier constraints.
   - Generates PDF/JSON certificate with shareable link.

3. **Genome Update & Life Ledger**
   - Diff viewer between genome versions.
   - Timeline view of ledger events with filters (deployments, incidents, tests) and integrity badge.

4. **Lineage Explorer**
   - Interactive DAG using D3 or React Flow; supports fork annotations, ancestry playback, export to SVG/PDF.

5. **Billing & Upgrade Center**
   - Usage meters, quota warnings, plan comparison, one-click upgrade via Stripe portal.
   - Investor presentation toggle that highlights ARR, incident responsiveness, and compliance status.

6. **Investor Demo Mode**
   - Pre-scripted scenario loader (Alpha/Beta storyline) with auto-populated charts, ready for screen share.

## Infrastructure & Dev Experience

- Dockerfile + docker-compose for local dev (FastAPI, Postgres, Redis, MinIO for object storage emulator).
- Makefile / task runner (`justfile`) for lint, test, seed, runserver.
- GitHub Actions CI pipeline for linting, tests, security scans, Docker build.

## KPI & Analytics Assets

- Segment/Snowplow event catalog describing `AgentIssued`, `GenomeMutated`, `IncidentLogged`, `LineageRendered`.
- Grafana dashboard JSON exports for ledger throughput, certificate issuance rate, billing reconciliation depth.

## Delivery Checklist

- [ ] Backend skeleton committed with working health check.
- [ ] Database migrations for all core tables.
- [ ] Frontend scaffold with authenticated layout and placeholder pages wired to API.
- [ ] Seed script generating investor demo data.
- [ ] Stripe webhook endpoint reachable locally (ngrok) with signing secret.
- [ ] Documentation updated for every module (docstrings + `docs/` pages).

This scope ensures the first investor-facing build is feature-complete, monetizable, and extensible.
