# PGL Operator Manual — Current

> [!IMPORTANT]
> Read [`../00_VEKLOM_BIBLE.md`](../00_VEKLOM_BIBLE.md) first. The Bible controls cross-repo architecture, runtime truth, deployment ownership, host-port reservations, and evidence language.

## Product boundary

Project Genome Ledger is a standalone product and a reusable Veklom evidence/provenance/lineage capability domain. Its standalone Registry/Certificates/Ledger/Lineage UI is not embedded wholesale into Capability OS; Capability OS consumes the underlying capabilities and renders a Veklom-native experience.

## Runtime rule

There is **no silent Investor Demo fallback** in the current operating doctrine. If the live registry/API is unreachable, surface the failure explicitly. Demo fixtures may exist only when isolated and unmistakably labeled `DEMO`.

Current configured Coolify routing verified 2026-08-09 includes:

- `pgl.veklom.com` → Gnomledger service internal port `8001`
- `ledger.veklom.com` → Gnomledger service internal port `8000`

These are **internal Docker ports behind Traefik**. Host port `8000` belongs to Coolify itself and must not be allocated directly to an application.

`CONFIGURED` routing is not a health claim. Re-check the live endpoints before saying the service is healthy.

## Core operator flow

1. Bootstrap a fresh registry only when bootstrap is actually required and authorized.
2. Use an authorized API key for protected calls.
3. Create/issue the asset through the current `POST /api/v1/agents` contract.
4. Read the persisted asset back through the current agent, ledger, verification, and lineage routes.
5. Verify the ledger chain instead of assuming a successful write equals cryptographic verification.
6. Export only data returned from the authoritative runtime. Do not add demo data to a production export.

## Primary API families

Current repository API surface includes:

- admin bootstrap/key management
- agent issue/read/certificate/genome update
- ledger event append/read/verification
- lineage fork/tree
- billing usage/limits/webhook
- Veklom integration snapshot

Use current route code and generated OpenAPI as the detailed contract; do not copy endpoint behavior from archived docs when source has changed.

## Evidence language

Distinguish persisted records from verified cryptographic evidence. Hash chaining is tamper-evident. Stronger claims such as external finality, physical immutability, or on-chain anchoring require independent verification of the exact record/anchor.

## Failure rules

- Authentication failure stays a failure.
- Validation failure stays a failure.
- Quota/payment failure stays a failure.
- Backend unavailability stays an explicit unavailable/error state.
- Never replace any of those states with bundled investor/demo content.

## Deployment operations

Coolify is deployment/runtime configuration truth for the verified Veklom environment. Use Coolify UI/API/MCP for Coolify resource management. Reserve SSH for direct host/container verification or operations that cannot be performed safely through Coolify.

Do not document a Vercel URL as production truth unless it has been independently reverified as the active deployment.

## Historical manual

The previous demo/Vercel-oriented manual is `ARCHIVED`; see [`archive/2026-08-09/operator-manual.md`](./archive/2026-08-09/operator-manual.md).
