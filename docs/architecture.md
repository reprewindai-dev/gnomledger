# Project Genome Ledger — Current Architecture

> [!IMPORTANT]
> Cross-repo architecture/runtime truth lives in [`../00_VEKLOM_BIBLE.md`](../00_VEKLOM_BIBLE.md). This file describes Genome Ledger’s repository/domain architecture only.

## Product boundary

Project Genome Ledger is both:

1. a standalone product with its own Registry / Certificates / Ledger / Lineage / Billing experience; and
2. a reusable Veklom evidence, provenance, lineage, and verification capability domain.

Capability OS does not embed the standalone Genome Ledger UI wholesale. It consumes the underlying capabilities and presents them through Veklom-native surfaces.

## Repository stack

| Layer | Current repository role |
|---|---|
| Frontend | React/TypeScript product surface for registry, certificate, ledger, lineage, billing, and verification views |
| Backend | FastAPI + SQLAlchemy + Pydantic service boundary |
| Persistence | Database-backed agent, certificate, genome, ledger, lineage, and billing state |
| Auth | Server-side API-key/RBAC contracts |
| Evidence | Append-only/hash-linked ledger records with explicit verification endpoints |
| Deployment | Container and other packaging assets exist in source; **current production placement must be read from Coolify/runtime evidence, not inferred from packaging files** |

## Service domains

- **Registry** — agent/asset registration and certificate issuance.
- **Genome** — versioned genome/capability-state payloads.
- **Ledger** — event append, read, and chain verification.
- **Lineage** — parent/child ancestry and forks.
- **Billing** — usage/limit accounting and payment-webhook integration where configured.
- **Admin/Auth** — bootstrap, API keys, roles, and authorization.
- **Integration** — Veklom snapshot/evidence interfaces.

## Evidence semantics

A persisted event is not automatically the same thing as independently verified evidence.

- Hash-linked records provide **tamper evidence**.
- `/verify`-style checks establish chain integrity only to the extent the implementation actually validates it.
- External anchoring/finality must be separately proven against the authoritative external system.
- Demo or seeded events may never be mixed into production evidence without an explicit `DEMO` boundary.

## Runtime / deployment truth

Verified 2026-08-09 Coolify dynamic routing shows:

- `pgl.veklom.com` configured to Gnomledger internal port `8001`.
- `ledger.veklom.com` configured to Gnomledger internal port `8000`.

These are internal Docker service ports behind Traefik. **Host port `8000` is reserved by Coolify itself**, including the Coolify UI/API/MCP surface, and must not be allocated directly to the application.

Configured routing is not by itself a health guarantee. Verify the live endpoint before making a production-health claim.

## No investor-demo fallback

The old Investor Mode / investor replay fallback architecture is retired. If authoritative backend data is unavailable, the production UI must fail explicitly or display an unavailable/unverified state. It must not silently substitute bundled demo data.

## API contract

Use current route source and generated OpenAPI for detailed endpoint truth. Major families include:

- `/api/v1/admin/*`
- `/api/v1/agents*`
- `/api/v1/ledger/*`
- `/api/v1/lineage/*`
- `/api/v1/billing/*`
- `/api/v1/integrations/*`

Do not copy exact behavior from archived docs when it differs from current source.

## Historical architecture

The previous Vercel/demo-oriented architecture is `ARCHIVED`; see [`archive/2026-08-09/architecture.md`](./archive/2026-08-09/architecture.md).
