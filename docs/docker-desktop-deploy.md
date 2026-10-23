# Deploying Genome Ledger on the Veklom Docker Desktop stack

Veklom runs on Docker Desktop (WSL2) on the owner's Windows host and is published through a
Cloudflare tunnel (owner decision 2026-10-07; Coolify, Hetzner and Vercel are not part of
Veklom). Genome Ledger is the `gnomledger-api` service of the `veklom-capability-os-rc1`
Compose project (staging: `veklom-staging`). Other services reach it at
`http://gnomledger-api:8001`; the tunnel publishes it as `https://pgl.veklom.com`.

Observed live on 2026-10-12, read-only:

| | |
|---|---|
| Running build | `e1ce7a7` (2026-10-06): no `/api/v1/agents/...` or `/admin/...` routes, no signing key |
| cAPI registry | gnomledger, cappo, lockerphycer registered and authenticated |
| cAPI dependency probe | reaches `gnomledger-api:8001`, `cappo-backend:8002`, `lockerphycer-api:8092`; the ledger answered in 1.7 s against a 2 s probe timeout, so it flaps between healthy and unavailable |

CAPPO looks agents up at `GET /api/v1/agents/{id}` and PGL Studio calls the `/api/v1/agents`,
`/admin` and `/billing` paths, so neither works against `e1ce7a7`. Upgrading `gnomledger-api`
is what connects them.

## Upgrade rules (rehearsed)

The upgrade was rehearsed on a SQLite database written by `e1ce7a7` itself: existing agents
and evidence stayed readable, the old chain verified unchanged, new evidence linked onto the
old chain head, old certificates read `unsigned_legacy` and new ones `signed`. New tables
(`agent_handles`, `certificate_signatures`) are created at startup; no existing table changes.

1. **Keep `API_KEY_SECRET` exactly as it is.** API keys are stored as an HMAC under this
   secret; a new value invalidates every key, including the one cAPI and CAPPO send.
2. **Set `PGL_LEDGER_API_KEY` to the key cAPI and CAPPO already send** (their
   `PGL_LEDGER_API_KEY` / `GNOMLEDGER_API_KEY`). The new build verifies that key against the
   database at startup and stays "database unavailable" if it does not match.
3. **Add `PGL_SIGNING_KEY_PEM`** if `ENVIRONMENT=prod`. Without it the new build refuses to
   start. Generate once and keep a backup outside the host:
   ```sh
   openssl genpkey -algorithm ed25519 | awk '{printf "%s\\n", $0}'
   ```
4. **Keep the data volume** (`veklom-capability-os-rc1_gnomledger-data`).

## One click (Windows)

Download `Upgrade-Veklom.cmd` from the repo root and double-click it. It fetches these scripts
into `%USERPROFILE%\veklom-upgrade\gnomledger` with your Git login and runs
`scripts/veklom-upgrade.sh` in WSL. That first writes a read-only report of the running stack
(containers, where each Compose project was started from, and a dry run of every upgrade) to
`%USERPROFILE%\veklom-upgrade\stack-report-*.txt`. Then it asks, one step at a time: Genome
Ledger + CAPPO on `veklom-staging`, the same on `veklom-capability-os-rc1` (only after staging
succeeded), then cAPI on each. Nothing changes until you answer `y`.

## One command

`scripts/upgrade-capos-stack.sh` does the steps below for `gnomledger-api` and `cappo-backend`
(and, with `--services capi`, for cAPI) and applies the rules above. It works whether the stack
was started from Windows or WSL, whether a service builds from a checkout or runs a prebuilt
image (it then rebuilds that tag from `main` and keeps the old one as `veklom-rollback/...`), and
it stashes local edits or leaves a side branch only after listing that in its plan. From WSL on
the Docker Desktop host, in a checkout of this repo:

```sh
scripts/upgrade-capos-stack.sh veklom-staging --dry-run      # shows what it will do
scripts/upgrade-capos-stack.sh veklom-staging                # asks, then upgrades
scripts/upgrade-capos-stack.sh veklom-capability-os-rc1 \
  --pgl-url https://pgl.veklom.com --capi-url https://capi.veklom.com --cappo-url https://cappo.veklom.com
```

It finds each service by its Compose labels and refuses to run if the service's build context
has uncommitted changes or is not on `main`, or if `API_KEY_SECRET` is missing. It backs up the
data volumes and env file to `~/veklom-backups/`, fast-forwards `main`, and in prod generates
`PGL_SIGNING_KEY_PEM` once (kept in `~/.veklom-secrets/`; copy it off the host). It then
rebuilds that one service and waits for it to report healthy. If the service is not healthy,
it resets `main` to the previous commit, restores the env file, rebuilds, and exits non-zero.

Rehearsed on a copy of the stack built from `e1ce7a7` with existing ledger data:

- **Upgrade:** the old agent and events were still readable and verified, and a new event linked onto the old chain head.
- **Broken release on `main`:** the script rolled back to `e1ce7a7`, healthy, with the data unchanged.
- **Second run:** no-op, and no duplicate key was generated.

## Steps

The manual equivalent. Do `veklom-staging` first, run the check in step 5 against it, then
repeat for `veklom-capability-os-rc1`.

1. **Find the stack's compose file and service name** (PowerShell or WSL):
   ```sh
   docker ps --filter name=gnomledger --format "{{.Names}}"
   docker inspect <container> --format "{{index .Config.Labels \"com.docker.compose.project.working_dir\"}} {{index .Config.Labels \"com.docker.compose.project.config_files\"}} {{index .Config.Labels \"com.docker.compose.service\"}}"
   ```
2. **Back up the ledger data:**
   ```sh
   docker run --rm -v veklom-capability-os-rc1_gnomledger-data:/data -v "$PWD":/backup alpine tar czf /backup/gnomledger-data-$(date +%Y%m%d%H%M).tgz -C /data .
   ```
3. **Update the source** the service builds from (its `build:` context) to `main` after this
   PR merges, and add `PGL_SIGNING_KEY_PEM` to that service's environment / `.env`. Leave
   `API_KEY_SECRET` and `PGL_LEDGER_API_KEY` untouched.
4. **Rebuild and restart only this service**, from the compose working directory found in step 1:
   ```sh
   docker compose -p veklom-capability-os-rc1 -f <config_files> up -d --build <service>
   docker compose -p veklom-capability-os-rc1 -f <config_files> logs --tail 50 <service>
   ```
   Expect `PGL database schema is ready` and `Gnomledger registered with cAPI`.
5. **Verify every link** (from WSL, or any shell with curl and python3):
   ```sh
   PGL_URL=https://pgl.veklom.com CAPI_URL=https://capi.veklom.com CAPPO_URL=https://cappo.veklom.com \
     scripts/verify-capos-link.sh
   ```
   Add `PGL_RUNTIME_KEY=<runtime key> ... --write` to also append one test evidence event and
   verify the chain. The ledger is append-only, so run the write check on staging.

Rollback: restore the previous image or source, then `up -d --build <service>`. If anything
was written in between, restore the tarball from step 2 into the volume first.

## Connections

| From | Setting | Value |
|---|---|---|
| cAPI | `PGL_LEDGER_URL`, `PGL_LEDGER_API_KEY` | `http://gnomledger-api:8001`, the runtime key |
| CAPPO | `GNOMLEDGER_URL`, `GNOMLEDGER_API_KEY` | same; carries pre/post execution attestations (without it CAPPO falls back to the non-canonical BYOS ledger) |
| CAPPO | `PGL_LEDGER_URL`, `PGL_LEDGER_API_KEY`, `PGL_LEDGER_AGENT_ID` | same, plus a gnomledger agent id for capability-mount events |
| CAPPO | `CAPPO_REQUIRE_PERSISTENT_PGL` | `true`, or mount events stay local-only |
| gnomledger | `CAPI_BACKEND_URL`, `CAPI_API_KEY` | cAPI's internal URL, and cAPI's `CAPI_REGISTRY_TOKEN` |
| PGL Studio | `PGL_BACKEND_URL`, `PGL_STUDIO_API_KEY` | `http://gnomledger-api:8001`, a key issued to Studio (pgl-studioai README) |

**Agent ids are shared.** gnomledger refuses evidence for agents it does not know. Every agent
cAPI executes for, and CAPPO's `PGL_LEDGER_AGENT_ID`, must be a gnomledger agent id
(`agent_…`), registered in gnomledger first.

CAPPO before reprewindai-dev/cappo-backend#113 rejects every gnomledger agent (it required
status `active`; gnomledger agents are `registered`) and crashes signed `/v1/exec` calls, so
upgrade `cappo-backend` from that fix as well.

## Verified end to end (local, 2026-10-12)

gnomledger (this branch, prod mode, Postgres), cAPI `main`, CAPPO with #113 and PGL Studio
were run together and exercised over HTTP:

- gnomledger registers itself with cAPI (`authenticated: true`) and re-registers after a cAPI restart.
- A cAPI covenant call seals Ed25519-signed evidence and forwards it to gnomledger (`sealed`, event id returned); cAPI reads it back through `/api/capi/v1/evidence/{id}`; cAPI's dependency probe reports the ledger healthy.
- CAPPO writes `pre_execution_authorization` and `post_execution_attestation` (the post event references the pre event), and anchors capability mount, action decision, consequence and terminate events as `confirmed`.
- A request signed by cAPI's `signCappoExecutionRequest` verifies in CAPPO; tampering with a covered header is rejected.
- PGL Studio, through its server key, shows the agent and every event above; the hash chain verifies.
