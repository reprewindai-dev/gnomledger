# Project Genome Ledger — Deployment & Operations

> [!IMPORTANT]
> Read [`../00_VEKLOM_BIBLE.md`](../00_VEKLOM_BIBLE.md) first. Coolify/runtime evidence overrides historical deployment plans.

## Current deployment model

For the Veklom production environment, the repository records the following **reported** deployment contract:

- deployment/runtime configuration authority: **Coolify**;
- public ingress is expected through Traefik;
- Gnomledger/PGL canonical service port: **8001**;
- ports **3000** and **8000** are forbidden as Gnomledger application listeners, Docker/Compose defaults, health-check targets, examples, or Traefik service targets;
- GitHub default branch is source truth for the intended application contract, but a source change is not runtime verification.

`reported_runtime_state` is not `verified_runtime_state`. Do not describe `pgl.veklom.com`, `ledger.veklom.com`, or any other public route as correctly routed merely because configuration or historical deployment notes say so.

Runtime port `8001` remains `NOT_VERIFIED` until the deployed commit SHA, HTTP/protocol identity, container listener, and Traefik routing all agree. cAPI registration must be verified separately after cAPI itself is verified.

## Coolify operations

Use Coolify UI/API for deployment and resource mutations. Coolify also exposes an MCP endpoint for AI-assisted infrastructure inspection when enabled and authorized; do not assume a particular MCP mutation capability without checking the current Coolify version/tool permissions.

Reserve SSH for direct host/container verification or operations that cannot be performed safely through Coolify. Any emergency host-side patch must be reconciled back into GitHub.

## Port ownership

Do not choose application ports from memory or from historical host/container mappings.

- Gnomledger canonical application port — `8001`;
- forbidden Gnomledger application ports — `3000`, `8000`;
- any infrastructure/control-plane listener outside the Gnomledger application contract must not be reused as evidence that Gnomledger is allowed to listen on a forbidden port.

A public route is not verified until its Traefik service target resolves to the canonical Gnomledger listener on `8001` and the returned HTTP/protocol identity matches the deployed Gnomledger commit.

## Deployment completion

A release is complete only after:

`repo change → pushed commit → Coolify deployment → live HTTPS/API verification → evidence/report`

Record the repository, branch, commit SHA, changed files, tests, deployment result, live verification, and rollback path.

## Persistence

Production durability depends on the actual configured database. Do not infer RDS, S3, Redis, EKS, object-lock, multi-region, or backup properties from old design documents. Verify each backing resource in current Coolify/runtime state before documenting it as live.

## Evidence / failure behavior

- No silent demo fallback.
- No seeded investor data in production evidence.
- A chain write is not the same as chain verification.
- A hash chain is tamper-evident; external finality must be independently proven.
- If a dependency or database is unavailable, expose the failure honestly rather than substituting a demo state.

## Historical deployment plan

The old AWS/EKS/investor-demo playbook is `ARCHIVED`; see [`archive/2026-08-09/deployment-operations.md`](./archive/2026-08-09/deployment-operations.md).
