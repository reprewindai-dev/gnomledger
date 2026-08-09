# Project Genome Ledger — Deployment & Operations

> [!IMPORTANT]
> Read [`../00_VEKLOM_BIBLE.md`](../00_VEKLOM_BIBLE.md) first. Coolify/runtime evidence overrides historical deployment plans.

## Current verified deployment model

For the Veklom production environment verified 2026-08-09:

- deployment/runtime configuration authority: **Coolify**;
- public ingress: **Traefik** on host ports `80/443`;
- `pgl.veklom.com` is configured to the Gnomledger service on internal Docker port `8001`;
- `ledger.veklom.com` is configured to the Gnomledger service on internal Docker port `8000`;
- host port `8000` belongs to Coolify itself and is **not** an application port;
- GitHub default branch is source truth; a source change is not complete until deployed and live-verified.

`CONFIGURED` routing does not prove application health. Verify the public endpoint after deployment.

## Coolify operations

Use Coolify UI/API for deployment and resource mutations. Coolify also exposes an MCP endpoint for AI-assisted infrastructure inspection when enabled and authorized; do not assume a particular MCP mutation capability without checking the current Coolify version/tool permissions.

Reserve SSH for direct host/container verification or operations that cannot be performed safely through Coolify. Any emergency host-side patch must be reconciled back into GitHub.

## Port ownership

Do not choose host-published ports from memory.

- host `80/443` — Traefik ingress;
- host `8000` — Coolify web/API/MCP listener;
- internal Docker `8000` — allowed for Gnomledger because it is not the host binding;
- internal Docker `3000` — used by several services behind Traefik; this does not establish host `3000` as free.

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
