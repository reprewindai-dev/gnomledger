# PGL Operator Manual

## Objective

Operate Project Genome Ledger as a deployable module that issues AI agent birth certificates, records lifecycle evidence, exposes lineage, and exports compliance artifacts.

This manual documents the system as it exists in this repository today.

## System Components

- Frontend control plane: React + Vite app in `src/`
- API service: FastAPI app in `backend/app/`
- Deployment entrypoint: `api/index.py`
- Database-backed service modules:
  - admin bootstrap and API keys
  - agent registration and certificate issuance
  - genome versioning
  - append-only ledger history
  - lineage trees and forks
  - billing usage and quota checks

## Execution Flow

### 1. Bootstrap the registry

This is the one-time initialization step for a fresh deployment.

1. Submit the bootstrap token, account name, and owner identity.
2. `POST /api/v1/admin/bootstrap` validates the bootstrap token.
3. The API creates the first account.
4. The API creates the first owner user.
5. The API issues the first owner API key.
6. The frontend stores that key in browser local storage and uses it for protected calls.

Result:

- The registry is initialized.
- The operator session becomes authenticated.
- Birth certificate issuance is unlocked.

### 2. Issue an agent birth certificate

This is the core "bring an agent to life" flow.

Inputs:

- `agent_name`
- `creator`
- `jurisdiction`
- `genome`
  - model family
  - model version
  - architecture
  - tools
  - permissions
  - safety rules
  - runtime config
  - intended use
  - risk category
- `parent_agent_ids` if the agent descends from other agents

System behavior:

1. The frontend sends `POST /api/v1/agents`.
2. The backend validates the payload with `AgentCreateRequest`.
3. The billing service checks whether issuance quota still exists.
4. The certificate service creates:
   - the agent record
   - the initial genome version
   - the certificate record
   - the birth ledger event
5. The API returns the new `agent_id`, `certificate_id`, and live state.

Result:

- The agent now exists as a first-class asset in the registry.
- Its history is part of the append-only ledger.
- Its ancestry is available in lineage views.

### 3. Review the issued asset

After issuance, the console reads back the asset through:

- `GET /api/v1/agents`
- `GET /api/v1/ledger/agents/{agent_id}`
- `GET /api/v1/ledger/agents/{agent_id}/verify`
- `GET /api/v1/lineage/tree/{agent_id}`
- `GET /api/v1/billing/usage`
- `GET /api/v1/billing/usage/{metric}/limit`

UI meaning:

- `Registry`: issued agents for the active account
- `Certificates`: identity and genome details
- `Ledger`: append-only event stream
- `Lineage`: parent-child ancestry tree
- `Billing`: usage and quota state
- `Investor Mode`: replay/export surface

### 4. Export artifacts

The frontend supports two export actions.

#### Export compliance packet

Downloads a JSON packet containing:

- export timestamp
- live vs replay mode
- selected agent
- ledger events
- lineage tree
- chain verification status
- usage limit snapshot

#### Generate investor replay

Downloads a JSON replay bundle containing:

- export timestamp
- selected agent ID
- demo bundle
- current selected agent
- current ledger view
- current lineage view

## How an Agent Gets Its Birth Certificate

### Through the app

1. Open the production control plane.
2. If the registry is new, complete bootstrap first.
3. Fill in the agent identity and genome fields.
4. Click `Issue Birth Certificate`.
5. The frontend submits `POST /api/v1/agents`.
6. The backend persists the agent, genome, certificate, and birth ledger event.
7. The new agent appears in the registry and becomes selectable for ledger and lineage inspection.

### Through the API

Use an owner, admin, or operator API key in the `x-api-key` header.

```bash
curl -X POST https://pgl-dksummers-projects.vercel.app/api/v1/agents \
  -H "Content-Type: application/json" \
  -H "x-api-key: YOUR_OWNER_OR_OPERATOR_KEY" \
  -d '{
    "agent_name": "Sentinel-Prime",
    "creator": "VEKLM Operations",
    "jurisdiction": "CA-ON",
    "genome": {
      "model_family": "gpt",
      "model_version": "5",
      "architecture": "tool-using-agent",
      "tools": ["crm", "browser", "email"],
      "permissions": ["read:crm", "write:tasks"],
      "safety_rules": ["human-review-for-payments", "no-unapproved-data-export"],
      "runtime_config": {
        "temperature": 0.2,
        "max_steps": 12
      },
      "intended_use": "Customer operations and task execution",
      "risk_category": "medium"
    },
    "parent_agent_ids": []
  }'
```

Verify creation:

```bash
curl -H "x-api-key: YOUR_OWNER_OR_OPERATOR_KEY" \
  https://pgl-dksummers-projects.vercel.app/api/v1/agents
```

Verify chain integrity:

```bash
curl -H "x-api-key: YOUR_OWNER_OR_OPERATOR_KEY" \
  https://pgl-dksummers-projects.vercel.app/api/v1/ledger/agents/AGENT_ID/verify
```

## Interfaces / APIs

- Auth header: `x-api-key`
- Roles that can issue agents: `operator`, `admin`, `owner`

Primary routes:

- `POST /api/v1/admin/bootstrap`
- `POST /api/v1/agents`
- `GET /api/v1/agents`
- `GET /api/v1/agents/{agent_id}`
- `GET /api/v1/agents/{agent_id}/certificate`
- `PATCH /api/v1/agents/{agent_id}/genome`
- `POST /api/v1/ledger/events`
- `GET /api/v1/ledger/agents/{agent_id}`
- `GET /api/v1/ledger/agents/{agent_id}/verify`
- `POST /api/v1/lineage/fork`
- `GET /api/v1/lineage/tree/{agent_id}`
- `GET /api/v1/billing/usage`
- `GET /api/v1/billing/usage/{metric}/limit`

## State & Data Handling

- Session key is stored in browser local storage under `pgl-session`.
- Live mode uses the stored API key for backend requests.
- Investor demo mode falls back to bundled local data when the live registry is unreachable.
- Export artifacts are generated client-side as JSON downloads.

## Failure & Degradation Rules

- Invalid bootstrap token: `403`
- Bootstrap already completed: `409`
- Missing API key: protected routes reject the request
- Invalid payload: `400`
- Issuance quota exhausted: `402`
- Live backend unreachable: UI falls back to local investor replay data

## Constraints

- Protected routes require a valid API key.
- The current UI does not expose API key creation and revocation controls.
- The current UI exports JSON evidence, not signed PDF certificates.
- The current deployment is protected by Vercel authentication in front of the app.

## Deployment Notes

- Production app: `https://pgl-dksummers-projects.vercel.app`
- Health endpoint: `https://pgl-dksummers-projects.vercel.app/health`
- Frontend and backend are deployed together on Vercel.
- Persistent production state depends on the configured database connection.
