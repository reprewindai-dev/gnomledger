# Deploying Genome Ledger on Coolify

`docker-compose.coolify.yml` runs the whole PGL product as one Coolify stack:

| Service | What it is | Internal address | Public |
|---|---|---|---|
| `postgres` | Ledger database (persistent volume `pgl-postgres`) | `postgres:5432` | no |
| `gnomledger` | Genome Ledger API (this repo) | `http://gnomledger:8001` | yes: the API Capability OS calls |
| `pgl-studio` | PGL Studio UI ([pgl-studioai](https://github.com/reprewindai-dev/pgl-studioai)), proxies `/api/v1` to `gnomledger` | `http://pgl-studio:3000` | yes: operator console |

Studio is built straight from GitHub (`pgl-studioai`, branch `PGL_STUDIO_REF`, default `main`), so
Coolify only needs this one repository.

## 1. Create the resource

1. Coolify → your project → **+ New** → **Resource** → **Private Repository (with GitHub App)**
   (or **Public Repository**) → `reprewindai-dev/gnomledger`, branch `main`.
2. **Build Pack: Docker Compose**. **Docker Compose Location:** `/docker-compose.coolify.yml`.
3. Save. Coolify reads the compose file and lists the three services.

## 2. Set the variables

Under **Environment Variables**, Coolify has already generated `SERVICE_USER_POSTGRES`,
`SERVICE_PASSWORD_POSTGRES`, `SERVICE_PASSWORD_64_APIKEYSECRET`, `SERVICE_PASSWORD_64_BOOTSTRAP`
and `SERVICE_PASSWORD_64_PGLLEDGER`. Leave them as they are.

You set:

| Variable | Value |
|---|---|
| `PGL_SIGNING_KEY_PEM` | **Required.** Ed25519 key that signs certificates and checkpoints. Generate once (below), store a backup outside Coolify, never rotate casually. |
| `PGL_STUDIO_API_KEY` | Leave empty for the first deploy; filled in step 4. |
| `CAPI_BACKEND_URL` | cAPI base URL, e.g. `https://capi.veklom.com`. Empty skips cAPI registration. |
| `CAPI_API_KEY` | Must equal cAPI's `CAPI_REGISTRY_TOKEN`. |
| `CORS_ORIGINS` | Only if a browser app on another origin calls the API directly, e.g. `["https://www.veklom.dev"]`. |
| `GEMINI_API_KEY` | Optional: Studio's "analyze genome" / chat helpers. |
| `PGL_STUDIO_REF` | Optional: Studio branch to build (default `main`). |

Generate the signing key on any machine with OpenSSL, as one line with literal `\n`:

```sh
openssl genpkey -algorithm ed25519 | awk '{printf "%s\\n", $0}'
```

## 3. Domains and first deploy

1. Open the `gnomledger` service → **Domains**: `https://pgl.veklom.com` (cAPI's dependency
   probe expects this host). Open `pgl-studio` → **Domains**: e.g. `https://pgl-studio.veklom.com`.
   Keep to one subdomain level so Cloudflare's universal certificate covers it.
2. In Cloudflare DNS, point both names at the Coolify server.
3. **Deploy**. Then check:

```sh
curl https://pgl.veklom.com/health/ready          # {"status":"ok","database":"ready",...}
curl https://pgl.veklom.com/api/v1/capabilities   # contract_version pgl-execution-v1
```

On first start gnomledger creates the **Veklom Capability OS** account and registers
`SERVICE_PASSWORD_64_PGLLEDGER` as its owner key. From then on the configured key must match
the database: gnomledger refuses to start if it changes. `POST /api/v1/admin/bootstrap` answers
409 by design.

## 4. Give Studio its own key

Studio has no login: its server adds `PGL_STUDIO_API_KEY` to every ledger request. Issue a
dedicated key so Studio's writes are attributed to `pgl-studio`, not to the Capability OS runtime:

```sh
curl -X POST https://pgl.veklom.com/api/v1/admin/accounts/1/keys \
  -H "x-api-key: <SERVICE_PASSWORD_64_PGLLEDGER>" \
  -H "content-type: application/json" \
  -d '{"name":"pgl-studio","role":"admin","scopes":["*"]}'
```

Put the returned `api_key` into `PGL_STUDIO_API_KEY` and redeploy. The key is shown once.

**Studio grants that key's access to anyone who can open the page.** Put the Studio domain behind
Cloudflare Access (or another login gate) before sharing the URL.

## 5. Connect Capability OS

All callers use the runtime key, `SERVICE_PASSWORD_64_PGLLEDGER`:

| Service | Variables |
|---|---|
| cAPI | `PGL_LEDGER_URL=https://pgl.veklom.com`, `PGL_LEDGER_API_KEY=<runtime key>` |
| CAPPO | `GNOMLEDGER_URL=https://pgl.veklom.com`, `GNOMLEDGER_API_KEY=<runtime key>`, `PGL_LEDGER_URL=https://pgl.veklom.com`, `PGL_LEDGER_API_KEY=<runtime key>` |

CAPPO needs **both** pairs: `GNOMLEDGER_*` carries certificates and pre/post execution
attestations; without it CAPPO falls back to the non-canonical BYOS ledger. `PGL_LEDGER_*`
mirrors governance events. CAPPO's old `PGL_ENDPOINT` variable is not read by its code.

If cAPI or CAPPO runs on the same Coolify server, `http://gnomledger:8001` works instead of the
public URL once their stacks share a Docker network.

## 6. Verify the connections

```sh
# Ledger accepts Capability OS evidence and the chain verifies:
curl -X POST https://pgl.veklom.com/api/v1/agents -H "x-api-key: <runtime key>" \
  -H "content-type: application/json" \
  -d '{"agent_name":"deploy-check","jurisdiction":"CA","genome":{"model_family":"llama","model_version":"3.1","intended_use":"deploy check","risk_category":"low"}}'
curl https://pgl.veklom.com/api/v1/ledger/agents/<agent_id>/verify -H "x-api-key: <runtime key>"

# cAPI registration (when CAPI_BACKEND_URL is set) shows in the gnomledger logs:
#   "Gnomledger registered with cAPI"
```

Until these pass against the live domain, label the deployment `CONFIGURED`, not `VERIFIED_LIVE`.
