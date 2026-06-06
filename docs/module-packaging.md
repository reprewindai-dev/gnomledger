# Module Packaging Guide

## Objective

Package Project Genome Ledger as a clean VEKLM module/add-on with explicit boundaries, operating instructions, and repository governance.

## System Components

- React/Vite frontend
- FastAPI backend
- Vercel deployment entrypoint
- Database-backed domain services
- Documentation set
- Proprietary license

## Execution Flow

VEKLM should consume this repository as a bounded module:

1. Deploy the module.
2. Configure environment variables.
3. Bootstrap the first owner account.
4. Issue agent certificates through UI or API.
5. Pull ledger, lineage, and compliance exports into the larger control plane as needed.

## Interfaces / APIs

Integration surface:

- UI entrypoint: `/`
- Health check: `/health`
- API root: `/api/v1`

Primary integration routes:

- `/api/v1/agents`
- `/api/v1/ledger/agents/{agent_id}`
- `/api/v1/lineage/tree/{agent_id}`
- `/api/v1/billing/usage`

## State & Data Handling

- Browser-local operator session state
- Database-backed persistent records for accounts, agents, certificates, ledger events, lineage, and billing usage
- Exportable JSON artifacts for compliance and replay packaging

## Failure & Degradation Rules

- Live API failure falls back to investor replay mode in the UI.
- Missing or invalid API key fails closed.
- Billing/quota failures block certificate issuance.

## Constraints

- This repository is proprietary.
- It is intended for controlled deployment into VEKLM workflows.
- The current certificate artifact is a data record plus exportable JSON evidence, not a signed PDF workflow.

## Deployment Notes

- Current free-tier host target: Vercel
- Backend runtime: Vercel Python functions
- Persistent production use requires a managed database or equivalent configured connection

## Packaging Checklist

- `README.md` documents local run, deployment, and API surface
- `docs/operator-manual.md` documents operator usage
- `docs/module-packaging.md` documents module boundaries
- `docs/deployment-operations.md` documents deployment mechanics
- `docs/security-compliance.md` documents controls and posture
- `LICENSE` defines repository usage rights
- `.env.example` defines the required environment contract
