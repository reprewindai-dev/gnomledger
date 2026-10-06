> [!IMPORTANT]
> **VEKLOM BIBLE — READ FIRST:** [`00_VEKLOM_BIBLE.md`](./00_VEKLOM_BIBLE.md)
> Project Genome Ledger is both a standalone product and a reusable Veklom evidence/provenance capability domain. The Bible controls cross-repo/runtime truth.

# Project Genome Ledger (PGL)

Project Genome Ledger is a pre-production control plane for:

- issuing AI agent birth certificates
- versioning agent genomes
- storing append-only ledger events with hash-chain integrity checks
- tracking ancestry lineage
- enforcing plan-based usage and billing controls

The repository is structured as a deployable module that can be integrated into a larger operating stack such as VEKLM.

## Documentation

- [Docs Index](docs/README.md)
- [Operator Manual](docs/operator-manual.md)
- [Module Packaging Guide](docs/module-packaging.md)
- [Architecture](docs/architecture.md)
- [Deployment Operations](docs/deployment-operations.md)
- [Security Compliance](docs/security-compliance.md)
- [Audit Readiness](docs/AUDIT_READINESS.md)

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
uvicorn backend.app.main:app --reload --port 8001
```

5. Start the frontend in a second shell:

```bash
npm run dev
```

6. Verify health:

```bash
curl http://127.0.0.1:8001/health
```

7. Bootstrap the first account:

```bash
curl -X POST http://127.0.0.1:8001/api/v1/admin/bootstrap \
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
   - `GET /api/v1/agents/{agent_id}`
   - `GET /api/v1/ledger/agents/{agent_id}`
   - `GET /api/v1/ledger/agents/{agent_id}/verify`
   - `GET /api/v1/lineage/tree/{agent_id}`
6. Export compliance and replay artifacts from the frontend rail actions.

The full operator flow is documented in [docs/operator-manual.md](docs/operator-manual.md).

## Environment Variables

Copy `.env.example` and set at least:

- `API_KEY_SECRET`
- `BOOTSTRAP_ADMIN_TOKEN`
- `DATABASE_URL`
- `STRIPE_WEBHOOK_SECRET` if webhook ingestion is enabled
- `PGL_SIGNING_KEY_PEM` (PKCS#8 Ed25519 PEM; `\n` escapes accepted) or `PGL_SIGNING_KEY_PATH`
  (path to that PEM). Required when `ENVIRONMENT=prod`: the service refuses to start without
  a loadable Ed25519 key. In dev/staging a key is generated once under the data directory
  (`data/keys/pgl-signing-key.pem`). Generate one with
  `openssl genpkey -algorithm ed25519 -out pgl-signing-key.pem`. Never commit it.

## API Surface

All API endpoints are rooted at `/api/v1` unless shown with a leading `/.well-known`.

- `POST /admin/bootstrap` (optional `admin_full_name`: the operator's real name, used for agent handles)
- `POST /admin/accounts/{account_id}/keys`
- `GET /admin/accounts/{account_id}/keys`
- `DELETE /admin/accounts/{account_id}/keys/{api_key_id}`
- `POST /agents` registers a kind of agent (see "Agent registration" below)
- `GET /agents`
- `GET /agents/{agent_id}`
- `GET /agents/{agent_id}/certificate` returns the signed birth certificate
- `PATCH /agents/{agent_id}/genome` (requires `reason`)
- `POST /agents/{agent_id}/decommission` (requires `reason`; keeps every record)
- `POST /agents/execution/validate` (optional `model_used`, must be a declared model)
- `POST /ledger/events`
- `GET /ledger/agents/{agent_id}`
- `GET /ledger/agents/{agent_id}/verify`
- `GET /ledger/agents/{agent_id}/checkpoint` returns a signed chain checkpoint
- `POST /ledger/checkpoints/verify` (public) checks a held checkpoint for truncation or rewrite
- `GET /ledger/agents/{agent_id}/audit-bundle` returns the signed audit bundle
- `GET /ledger/signing-key` and `GET /.well-known/pgl-signing-key` (public) publish the
  Ed25519 public key (PEM + JWK + key id)
- `POST /lineage/fork`
- `GET /lineage/tree/{agent_id}`
- `GET /billing/usage`
- `GET /billing/usage/{metric}/limit`
- `POST /billing/stripe/webhook`
- `GET /integrations/vekml/agents/{agent_id}/snapshot`

The `/admin`, `/agents` and `/billing` routers were historically also mounted without their
prefix (for example `GET /api/v1/{agent_id}` and `GET /api/v1/usage`). Those legacy paths are
still served for existing callers but are not in the OpenAPI schema; new integrations should
use the prefixed paths above.

### Agent registration

`POST /api/v1/agents` registers the identity of a *kind* of agent once; each task is an
ephemeral execution that cites it. Every field added for audit readiness is optional, so the
original request shape still works; the signed certificate lists what was left out in
`missing_accountability_fields` and `missing_integrity_fields`. Field-by-field meaning is in
[docs/AUDIT_READINESS.md](docs/AUDIT_READINESS.md).

```json
{
  "agent_name": "optional; defaults to the server handle, e.g. AM-133f1339-17",
  "creator": "optional; defaults to the authenticated operator",
  "jurisdiction": "EU",
  "parent_agent_ids": [],
  "genome": {
    "intended_use": "Triage inbound insurance claims",
    "risk_category": "medium",
    "industry": "insurance",
    "run_mode": "human_in_the_loop",
    "accountable_owner": {"name": "...", "role": "...", "email": "...", "organization": "..."},
    "incident_contact": "security@example.com or https://...",
    "deployer": "Example Insurance Ltd",
    "provider": "Example Insurance Ltd",
    "capability_refs": ["veklom.governed-counter@v1"],
    "permissions": ["declarative only"],
    "tools": ["browser"],
    "safety_rules": [],
    "out_of_scope_uses": ["..."],
    "known_limitations": ["..."],
    "data_categories": ["personal", "financial"],
    "log_retention_days": 180,
    "regulatory_risk_class": "high_risk",
    "risk_rationale": "...",
    "oversight": {"stop_mechanism": "CAPPO terminate", "oversight_contact": "...", "escalation_path": "..."},
    "declared_models": [{"provider": "Anthropic", "identifier": "claude-opus-5-5", "role": "planner"}],
    "system_prompt_sha256": "<64 hex>",
    "code_commit": "<7-64 hex>",
    "image_digest": "repo@sha256:<64 hex>",
    "tool_versions": {"browser": "1.4.2"},
    "runtime_config": {}
  }
}
```

The single-model fields `model_family` + `model_version` (+ `architecture`, `model_provider`,
`model_identifier`) are still accepted and read as one declared model; one of the two forms
is required. `log_retention_days` below 180 is refused. `system_prompt` text is refused; send
its SHA-256. The response adds `agent_handle` and `certificate` (`signature_status`,
`certificate`, `signature {algorithm, key_id, value}`, `key_id`,
`missing_accountability_fields`, `missing_integrity_fields`, `current_genome_hash`).

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

This exposes the API on `http://localhost:8001`.

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

See [LICENSE](LICENSE). This repository is proprietary and may not be reused or redistributed without written authorization.
