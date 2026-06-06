# System Architecture Blueprint

## Stack Overview

| Layer | Technology | Notes |
|-------|------------|-------|
| Frontend | React 18, TypeScript, Vite, custom CSS, lucide-react | Control plane, certificate viewer, lineage explorer, investor replay mode |
| Backend | Python 3.12, FastAPI, SQLAlchemy 2.0, Pydantic v2 | Modular services for registry, ledger, lineage, billing, and admin |
| Persistence | PostgreSQL or SQLite (dev), SQLAlchemy 2.0 | Persistent agent, certificate, ledger, lineage, and billing state |
| Billing | Stripe Webhooks + internal usage accounting | Enforces issuance and metered usage policies |
| Auth | API keys validated server-side | RBAC enforced at route and service layer |
| Observability | Python logging, request IDs, processing time headers | Operational traceability for deployed API calls |
| Infra | Vercel, Docker, docker-compose | Free-tier deploy target plus container option |

## Service Modules

1. **Registry Service**
   - Endpoints: `/agents`
   - Responsible for birth certificate issuance, genome storage, and parent linkage.
2. **Ledger Service**
   - Endpoints: `/ledger/events`, `/ledger/agents/{agent_id}`, `/ledger/agents/{agent_id}/verify`
   - Writes append-only events with hash chaining and exposes chain verification.
3. **Lineage Service**
   - Endpoints: `/lineage/tree/{agent_id}`, `/lineage/fork`
   - Builds ancestry trees from parent-child relationships.
4. **Billing Service**
   - Endpoints: `/billing/usage`, `/billing/usage/{metric}/limit`, `/billing/stripe/webhook`
   - Tracks usage, plan limits, and Stripe webhook ingestion.
5. **Analytics Service**
   - Aggregates usage and investor/demo-facing summary views.
6. **Admin Service**
   - Provides bootstrap and API key management.

All services run inside the FastAPI application and share common authentication, database, logging, and request-ID middleware.

## Data Model

- `accounts`: organizations and plan tier
- `users`: account users with role assignments
- `api_keys`: scoped access keys for authenticated access
- `agents`: core identity records
- `genome_versions`: versioned genome payloads hashed for integrity
- `certificates`: birth certificate metadata
- `ledger_events`: append-only events with `prev_event_hash` and `event_hash`
- `lineage_edges`: parent-child links for ancestry reconstruction
- `billing_usage`: metered usage records and period windows

## API Surface

### Registry

- `POST /api/v1/agents`: Create agent and issue birth certificate
- `GET /api/v1/agents`: List account agents
- `GET /api/v1/agents/{agent_id}`: Fetch certificate and genome snapshot
- `GET /api/v1/agents/{agent_id}/certificate`: Read certificate artifact metadata
- `PATCH /api/v1/agents/{agent_id}/genome`: Submit a genome update

### Ledger

- `POST /api/v1/ledger/events`: Append deployment, audit, incident, or custom events
- `GET /api/v1/ledger/agents/{agent_id}`: Read event history
- `GET /api/v1/ledger/agents/{agent_id}/verify`: Validate chain integrity

### Lineage

- `POST /api/v1/lineage/fork`: Fork an agent and inherit genome ancestry
- `GET /api/v1/lineage/tree/{agent_id}`: Read the ancestry tree

### Billing

- `GET /api/v1/billing/usage`: Read current usage
- `GET /api/v1/billing/usage/{metric}/limit`: Read quota and remaining allowance
- `POST /api/v1/billing/stripe/webhook`: Receive Stripe webhook events

### Admin

- `POST /api/v1/admin/bootstrap`: Initialize the first account and owner key
- `POST /api/v1/admin/accounts/{account_id}/keys`: Create API keys
- `GET /api/v1/admin/accounts/{account_id}/keys`: List API keys
- `DELETE /api/v1/admin/accounts/{account_id}/keys/{api_key_id}`: Revoke API keys

## Auth & RBAC

- API key authentication is the active contract for protected routes.
- Active roles: `owner`, `admin`, `operator`, `viewer`
- Route-level dependencies enforce read/write privileges.
- Agent issuance requires `operator`, `admin`, or `owner`.

## Observability & Logging

- Logging is configured centrally in the FastAPI app.
- Each request receives an `x-request-id`.
- Responses include `x-processing-ms`.
- Ledger verification and billing usage provide the main operational integrity signals.

## Infrastructure & Reliability

- **Environments:** local, preview, and production deployments are supported.
- **CI/CD:** git push to Vercel is the active hosted deployment path.
- **Backups:** production durability depends on the configured backing database provider.
- **Secrets Management:** environment variables drive deployment-time configuration.
- **Rate Limiting:** not yet implemented as a dedicated middleware layer.

## Scaling Considerations

- Service logic is already separated into modules for later extraction if the system is split.
- The API contract is stable enough to serve as a VEKLM module boundary.
- Export artifacts provide a clean bridge into other control-plane systems.
