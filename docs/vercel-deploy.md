# Deploying Genome Ledger on Vercel

This repository deploys to Vercel as one project:

| Part | Served from | Paths |
|---|---|---|
| Genome Ledger API (FastAPI) | Python Vercel Function `api/index.py` | `/api/*`, `/health`, `/health/*`, `/.well-known/pgl-signing-key`, `/.well-known/x402.json` |
| Standalone PGL page (Vite) | Static build (`npm run build` → `dist/`) | everything else |

PGL Studio (the operator console) is the separate repository
[pgl-studioai](https://github.com/reprewindai-dev/pgl-studioai) and its own Vercel project. Its
README covers its variables.

## 1. Database

Vercel Functions only have an ephemeral `/tmp`. In production the ledger must use Postgres.
Gnomledger refuses to start on Vercel with `ENVIRONMENT=prod` and the SQLite default.

Add a Postgres database: Vercel → the project → **Storage** → **Create Database** → Neon
(or any Postgres). Connect it to the project so it sets `DATABASE_URL`. `postgres://` and
`postgresql://` URLs both work.

## 2. Environment variables (Production)

Vercel → the project → **Settings → Environment Variables**, scoped to **Production**:

| Variable | Value |
|---|---|
| `ENVIRONMENT` | `prod` |
| `DATABASE_URL` | From step 1 |
| `API_KEY_SECRET` | Random, at least 32 characters: `openssl rand -hex 32` |
| `BOOTSTRAP_ADMIN_TOKEN` | Random: `openssl rand -hex 32` |
| `PGL_LEDGER_API_KEY` | The Capability OS runtime key, at least 32 characters: `openssl rand -hex 32`. cAPI and CAPPO send this same value. Never change it once the database holds data: gnomledger refuses to start when it no longer matches. |
| `PGL_SIGNING_KEY_PEM` | Ed25519 key that signs certificates and checkpoints (command below). Keep a backup outside Vercel. |
| `CAPI_BACKEND_URL` | cAPI base URL, or empty to skip cAPI registration |
| `CAPI_API_KEY` | Must equal cAPI's `CAPI_REGISTRY_TOKEN` |
| `CORS_ORIGINS` | Only for browser apps on other origins calling the API directly, e.g. `["https://www.veklom.dev"]` |

Generate the signing key as one line with literal `\n`:

```sh
openssl genpkey -algorithm ed25519 | awk '{printf "%s\\n", $0}'
```

Preview deployments without these variables run in `dev` mode on a throwaway SQLite file.
That is fine for checking a branch, but nothing written there persists.

## 3. Deploy and check

Push to `main` (or redeploy from the Vercel dashboard), then:

```sh
curl https://pgl.veklom.com/health/ready          # {"status":"ok","database":"ready",...}
curl https://pgl.veklom.com/api/v1/capabilities   # contract_version pgl-execution-v1
curl https://pgl.veklom.com/.well-known/pgl-signing-key
```

On first start gnomledger creates the **Veklom Capability OS** account and registers
`PGL_LEDGER_API_KEY` as its owner key. `POST /api/v1/admin/bootstrap` then answers 409 by design.

## 4. Issue PGL Studio its key

Studio has no login: its server adds `PGL_STUDIO_API_KEY` to every ledger request. Give it its
own key so its writes are attributed to `pgl-studio`, not to the Capability OS runtime:

```sh
curl -X POST https://pgl.veklom.com/api/v1/admin/accounts/1/keys \
  -H "x-api-key: <PGL_LEDGER_API_KEY>" \
  -H "content-type: application/json" \
  -d '{"name":"pgl-studio","role":"admin","scopes":["*"]}'
```

In the Studio Vercel project, set `PGL_STUDIO_API_KEY` to the returned `api_key` (shown once)
and `PGL_BACKEND_URL=https://pgl.veklom.com`, then redeploy Studio. Turn on Vercel Deployment
Protection (or put Cloudflare Access in front) for Studio: anyone who can open it acts with
that key.

## 5. Connect Capability OS

All callers use the runtime key, `PGL_LEDGER_API_KEY`:

| Service | Variables |
|---|---|
| cAPI | `PGL_LEDGER_URL=https://pgl.veklom.com`, `PGL_LEDGER_API_KEY=<runtime key>` |
| CAPPO | `GNOMLEDGER_URL=https://pgl.veklom.com`, `GNOMLEDGER_API_KEY=<runtime key>`, `PGL_LEDGER_URL=https://pgl.veklom.com`, `PGL_LEDGER_API_KEY=<runtime key>` |

CAPPO needs **both** pairs. `GNOMLEDGER_*` carries certificates and pre/post execution
attestations; without it CAPPO falls back to the non-canonical BYOS ledger. `PGL_LEDGER_*`
mirrors governance events. CAPPO's old `PGL_ENDPOINT` variable is not read by its code.

cAPI registration runs from gnomledger's startup hook, so on Vercel it renews only while a
function instance is alive. cAPI and CAPPO send evidence straight to `PGL_LEDGER_URL` /
`GNOMLEDGER_URL`, so evidence does not depend on the registry entry.

## 6. Verify the connection

```sh
curl -X POST https://pgl.veklom.com/api/v1/agents -H "x-api-key: <runtime key>" \
  -H "content-type: application/json" \
  -d '{"agent_name":"deploy-check","jurisdiction":"CA","genome":{"model_family":"llama","model_version":"3.1","intended_use":"deploy check","risk_category":"low"}}'
curl https://pgl.veklom.com/api/v1/ledger/agents/<agent_id>/verify -H "x-api-key: <runtime key>"
```

Until these pass against the live domain, label the deployment `CONFIGURED`, not `VERIFIED_LIVE`.
