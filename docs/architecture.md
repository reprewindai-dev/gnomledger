# System Architecture Blueprint

## Stack Overview

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | Next.js 15 (App Router), TypeScript, Tailwind, Zustand, Recharts | Premium dashboard, certificate viewer, lineage explorer, investor presentation mode |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2 | Modular services (registry, ledger, lineage, billing, analytics) |
| Persistence | PostgreSQL 16 (primary), TimescaleDB extension for ledger metrics, Redis for caching + rate limiting | Hot ledger storage + cold archive (S3 + Glacier) |
| Messaging | AWS SQS (event fan-out), SNS (webhook notifications) | Ensures append-only semantics and downstream audit feeds |
| Billing | Stripe Billing + Customer Portal + Webhooks | Enforces per-agent certificate fees and metered usage |
| Auth | Auth0 / Okta Enterprise SSO, API keys signed with HMAC, service-to-service mTLS | RBAC enforced at route + service layer |
| Observability | OpenTelemetry, Loki, Tempo, Prometheus, Grafana Cloud | Audit logging, business KPIs, anomaly alerts |
| Infra | Docker, Kubernetes (EKS/GKE), Terraform IaC, ArgoCD | Multi-env (dev/stage/prod) with blue/green deployments |

## Service Modules

1. **Registry Service**
   - Endpoints: `/agents`, `/certificates`, `/genomes`
   - Responsible for birth certificate issuance, genome storage, and parent linkage.
2. **Ledger Service**
   - Endpoints: `/ledger/events`, `/ledger/streams`
   - Writes append-only events with hash chaining, exposes filtered queries, supports cold-storage export jobs.
3. **Lineage Service**
   - Endpoints: `/lineage/tree/{agent_id}`, `/lineage/forks`
   - Builds DAG from parent-child relationships, caches computed trees, exposes mermaid/JSON for frontend.
4. **Billing Service**
   - Endpoints: `/billing/usage`, `/billing/webhooks`
   - Reconciles certificate issuance fees, storage usage, lineage renders; integrates with Stripe webhooks.
5. **Analytics Service**
   - Streams events to warehouse, powers dashboards for investors and compliance KPIs.
6. **Admin Service**
   - Provides RBAC management, audit logs, policy templates, and investor demo controls.

All services run within the FastAPI application as modules backed by SQLAlchemy sessions and shared middleware (auth, tracing, rate limiting).

## Data Model (simplified)

- `accounts`: organizations, plan tier, Stripe customer id, feature flags.
- `users`: belonging to accounts with roles (Owner, Auditor, Operator, InvestorViewer).
- `agents`: core identity (agent_id, name, owner, jurisdiction, status).
- `genomes`: versioned config blobs hashed for integrity.
- `certificates`: birth certificate metadata, pdf link, signature.
- `ledger_events`: append-only events with `prev_hash`, `event_hash`, tamper-proof chain.
- `lineage_edges`: records parent-child relationships for DAG reconstruction.
- `billing_usage`: metered metrics for certificates, storage, lineage renders.
- `incident_reports`, `deployments`, `test_results`: specialized event tables for fast queries.

## API Surface (selected endpoints)

### Registry
- `POST /api/v1/agents`: Create agent + issue birth certificate (requires billing quota check).
- `GET /api/v1/agents/{agent_id}`: Fetch certificate, genome snapshot, and lineage summary.
- `PATCH /api/v1/agents/{agent_id}/genome`: Submit mutation; records ledger event and new genome hash.

### Ledger
- `POST /api/v1/ledger/events`: Add deployment/test/incident events (idempotency key required).
- `GET /api/v1/ledger/agents/{agent_id}`: Paginated event history with integrity proofs.
- `GET /api/v1/ledger/verify`: Runs chain validation job and returns latest hash root.

### Lineage
- `POST /api/v1/lineage/fork`: Fork agent, inherit genome, record ancestry.
- `GET /api/v1/lineage/tree/{agent_id}`: Return DAG nodes/edges for visualization.

### Billing
- `GET /api/v1/billing/usage`: Current usage vs quota.
- `POST /api/v1/billing/stripe/webhook`: Handles invoice.paid, payment_failed, usage_record.summary.

### Admin
- `POST /api/v1/admin/rbac/policies`: Define custom policies.
- `GET /api/v1/admin/audit-log`: Export signed audit trail for regulators.

## Auth & RBAC

- Auth0/OIDC for user sessions; service-issued JWTs for API clients with HMAC signature.
- RBAC roles: `owner`, `admin`, `auditor`, `operator`, `viewer`, `investor_demo`.
- Route-level dependencies enforce scopes; ledger writes require `operator` or higher, audit exports require `auditor`.
- API keys scoped per environment with IP allowlists; optional customer-managed keys for Enterprise.

## Observability & Logging

- OpenTelemetry instrumentation on FastAPI routes and SQL queries.
- Structured logs (JSON) shipped to Loki; audit-specific logs stored immutably in S3 with Glacier backup.
- Metrics: latency, error rate, ledger throughput, certificate issuance, billing reconciliation lag.
- Alerts: chain verification failure, quota exhaustion, webhook errors, abnormal incident volume.

## Infrastructure & Reliability

- **Environments:** dev, staging, prod with separate AWS accounts, network segmentation, and secret stores.
- **CI/CD:** GitHub Actions → container build → security scan → ArgoCD deploy; migrations run via Alembic jobs.
- **Backups:** Point-in-time recovery for Postgres, hourly snapshots; ledger events mirrored to S3 with object lock (WORM).
- **Rate Limiting:** Redis-based leaky bucket per API key + global circuit breaker.
- **Secrets Management:** AWS Secrets Manager; rotated via Lambda automation.

## Scaling Considerations

- Horizontal scaling of FastAPI via ASGI workers on Kubernetes.
- Ledger writes batched via SQS to reduce contention; read replicas handle analytics queries.
- Cold storage lifecycle policies to offload historical ledger events while keeping proofs accessible.
- Precomputed lineage trees cached and invalidated on forks/mutations.

This architecture enables the Project Genome Ledger to meet SecEd standards while remaining modular for future feature growth and investor demonstrations.
