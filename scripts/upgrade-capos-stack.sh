#!/usr/bin/env bash
# Upgrades Genome Ledger (gnomledger) and CAPPO inside a running Veklom Compose stack on the
# Docker Desktop host, then verifies the links. Run it from WSL (or any shell with docker,
# git, curl and python3) on the machine that runs the stack:
#
#   scripts/upgrade-capos-stack.sh veklom-staging                 # plan, ask, upgrade, verify
#   scripts/upgrade-capos-stack.sh veklom-capability-os-rc1 \
#     --pgl-url https://pgl.veklom.com --capi-url https://capi.veklom.com \
#     --cappo-url https://cappo.veklom.com
#
# Options:
#   --services gnomledger,cappo   which services to upgrade (default: both)
#   --dry-run                     print the plan and stop
#   --yes                         do not ask for confirmation
#   --pgl-url/--capi-url/--cappo-url  public URLs for the final link check
#
# For each service it: finds the container by Compose labels, reads its build context (a git
# checkout), refuses to touch a dirty checkout or a branch other than main, backs up the
# container's data volumes, fast-forwards main, rebuilds only that service and waits for it to
# be healthy. If it is not healthy in time, it resets main to the previous commit, restores the
# env file, rebuilds, and exits non-zero.
#
# gnomledger rules (docs/docker-desktop-deploy.md): API_KEY_SECRET and PGL_LEDGER_API_KEY are
# kept as they are; in prod a missing PGL_SIGNING_KEY_PEM is generated once, saved under
# ~/.veklom-secrets, and appended to the service's env_file.
set -euo pipefail

PROJECT=${1:-}
[ -n "$PROJECT" ] && shift || { sed -n '2,25p' "$0"; exit 2; }
SERVICES=gnomledger,cappo
DRY_RUN=0
ASSUME_YES=0
PGL_URL="" CAPI_URL="" CAPPO_URL=""
while [ $# -gt 0 ]; do
  case "$1" in
    --services) SERVICES=$2; shift 2;;
    --dry-run) DRY_RUN=1; shift;;
    --yes) ASSUME_YES=1; shift;;
    --pgl-url) PGL_URL=$2; shift 2;;
    --capi-url) CAPI_URL=$2; shift 2;;
    --cappo-url) CAPPO_URL=$2; shift 2;;
    *) echo "unknown option: $1" >&2; exit 2;;
  esac
done

# Commits that must be on main before upgrading (the merged Capability OS link fixes).
declare -A REQUIRED_COMMIT=([gnomledger]=97652cef61883b5a9c27e22db21f45c64889c385 [cappo]=c0341b2305a17a8aa8a8bd6a77ce6a361b981908)
declare -A SERVICE_PATTERN=([gnomledger]='gnomledger|pgl' [cappo]='cappo')
declare -A HEALTH_CHECK=([gnomledger]='8001/health/ready' [cappo]='8002/health')

umask 077  # backups and generated keys are readable by this user only
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=${BACKUP_DIR:-$HOME/veklom-backups/$PROJECT-$STAMP}
SECRETS_DIR=${SECRETS_DIR:-$HOME/.veklom-secrets}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
for tool in docker git curl python3; do command -v "$tool" >/dev/null || die "$tool is required"; done

# json_get FILE EXPR: evaluates a Python expression against the JSON in FILE (bound to d).
json_get() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"; }

find_container() { # PATTERN -> "name<TAB>service" of the first matching container in the project
  docker ps -a --filter "label=com.docker.compose.project=$PROJECT" \
    --format '{{.Names}}	{{.Label "com.docker.compose.service"}}' | grep -E "	($1)" | head -1
}

health_ok() { # CONTAINER PORT/PATH -> 0 when the service answers 2xx from inside its container
  docker exec "$1" python3 -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$2', timeout=5)" >/dev/null 2>&1 \
    || docker exec "$1" python -c "import urllib.request,sys; urllib.request.urlopen('http://127.0.0.1:$2', timeout=5)" >/dev/null 2>&1
}

wait_healthy() { # SERVICE COMPOSE_ARGS... -> waits up to 150 s
  local svc=$1; shift
  local name
  for _ in $(seq 1 75); do
    name=$(docker compose "$@" ps -q "$svc" 2>/dev/null | head -1)
    if [ -n "$name" ] && health_ok "$name" "${HEALTH_CHECK[$CURRENT]}"; then return 0; fi
    sleep 2
  done
  return 1
}

declare -a PLAN_LINES=()
declare -A CTX OLD_SHA COMPOSE_ARGS SVC_NAME CONTAINER ENV_FILE NEEDS_KEY

log "Inspecting Compose project '$PROJECT'"
IFS=, read -ra WANTED <<< "$SERVICES"
for CURRENT in "${WANTED[@]}"; do
  line=$(find_container "${SERVICE_PATTERN[$CURRENT]}") || die "no $CURRENT container in project $PROJECT"
  CONTAINER[$CURRENT]=${line%%	*}
  SVC_NAME[$CURRENT]=${line##*	}
  wd=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${CONTAINER[$CURRENT]}")
  files=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "${CONTAINER[$CURRENT]}")
  args=(-p "$PROJECT" --project-directory "$wd")
  IFS=, read -ra cfgs <<< "$files"
  for f in "${cfgs[@]}"; do args+=(-f "$f"); done
  COMPOSE_ARGS[$CURRENT]="${args[*]@Q}"

  cfg_json=$(mktemp)
  # --no-env-resolution keeps env_file paths in the output (older Compose lacks it and inlines them).
  docker compose "${args[@]}" config --no-env-resolution --format json > "$cfg_json" 2>/dev/null \
    || docker compose "${args[@]}" config --format json > "$cfg_json"
  svc=${SVC_NAME[$CURRENT]}
  ctx=$(json_get "$cfg_json" "(d['services']['$svc'].get('build') or {}).get('context','')")
  [ -n "$ctx" ] || die "$svc has no build context in its compose file; it runs a prebuilt image, so rebuild its image from main first"
  git -C "$ctx" rev-parse --git-dir >/dev/null 2>&1 || die "$svc build context $ctx is not a git checkout"
  [ -z "$(git -C "$ctx" status --porcelain --untracked-files=no)" ] || die "$ctx has uncommitted changes; commit or stash them first"
  branch=$(git -C "$ctx" rev-parse --abbrev-ref HEAD)
  [ "$branch" = main ] || die "$ctx is on '$branch', not main; check out main there and rerun"
  CTX[$CURRENT]=$ctx
  OLD_SHA[$CURRENT]=$(git -C "$ctx" rev-parse HEAD)
  ENV_FILE[$CURRENT]=$(json_get "$cfg_json" "(lambda e: (e[0]['path'] if isinstance(e[0], dict) else e[0]) if e else '')(d['services']['$svc'].get('env_file') or [])")

  NEEDS_KEY[$CURRENT]=0
  if [ "$CURRENT" = gnomledger ]; then
    env_now=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${CONTAINER[$CURRENT]}")
    grep -q '^API_KEY_SECRET=' <<< "$env_now" || die "$svc has no API_KEY_SECRET; refusing to upgrade (every API key is an HMAC under it)"
    grep -q '^PGL_LEDGER_API_KEY=.\+' <<< "$env_now" || echo "  warning: $svc has no PGL_LEDGER_API_KEY; the new build refuses an initialized ledger without it"
    if grep -qiE '^ENVIRONMENT=prod' <<< "$env_now" && ! grep -qE '^PGL_SIGNING_KEY_(PEM|PATH)=.+' <<< "$env_now"; then
      [ -n "${ENV_FILE[$CURRENT]}" ] || die "$svc runs ENVIRONMENT=prod without PGL_SIGNING_KEY_PEM and has no env_file to add it to; add it to the compose file, then rerun"
      NEEDS_KEY[$CURRENT]=1
    fi
  fi
  rm -f "$cfg_json"
  note=""
  [ "${NEEDS_KEY[$CURRENT]}" = 1 ] && note="; will generate PGL_SIGNING_KEY_PEM into ${ENV_FILE[$CURRENT]}"
  PLAN_LINES+=("$CURRENT: service '$svc' (container ${CONTAINER[$CURRENT]}), source $ctx @ ${OLD_SHA[$CURRENT]:0:7} -> origin/main$note")
done

log "Plan (backups go to $BACKUP_DIR)"
printf '  %s\n' "${PLAN_LINES[@]}"
[ "$DRY_RUN" = 1 ] && { echo; echo "Dry run: nothing changed."; exit 0; }
if [ "$ASSUME_YES" != 1 ]; then
  read -r -p "Proceed? [y/N] " answer
  [ "$answer" = y ] || [ "$answer" = Y ] || { echo "Aborted."; exit 1; }
fi
mkdir -p "$BACKUP_DIR"

rollback() {
  local svc=${SVC_NAME[$CURRENT]}
  eval "local args=(${COMPOSE_ARGS[$CURRENT]})"
  log "ROLLBACK $CURRENT: logs from the failed start"
  docker compose "${args[@]}" logs --tail 40 "$svc" || true
  git -C "${CTX[$CURRENT]}" checkout -q -B main "${OLD_SHA[$CURRENT]}"
  if [ -f "$BACKUP_DIR/$CURRENT.env_file" ]; then cp "$BACKUP_DIR/$CURRENT.env_file" "${ENV_FILE[$CURRENT]}"; fi
  docker compose "${args[@]}" up -d --build "$svc"
  if wait_healthy "$svc" "${args[@]}"; then
    echo "  $CURRENT restored to ${OLD_SHA[$CURRENT]:0:7} (main reset there, env file restored) and healthy."
  else
    echo "  $CURRENT did not come back after rollback either. Data backup: $BACKUP_DIR" >&2
  fi
  exit 1
}

for CURRENT in "${WANTED[@]}"; do
  svc=${SVC_NAME[$CURRENT]}
  ctx=${CTX[$CURRENT]}
  eval "args=(${COMPOSE_ARGS[$CURRENT]})"

  log "$CURRENT: backing up data"
  docker inspect -f '{{range .Mounts}}{{.Type}}	{{if .Name}}{{.Name}}{{else}}{{.Source}}{{end}}	{{.Destination}}{{println}}{{end}}' "${CONTAINER[$CURRENT]}" |
  while IFS='	' read -r type src dest; do
    [ -n "$type" ] || continue
    out="$CURRENT$(echo "$dest" | tr '/' '_').tgz"
    if [ "$type" = volume ]; then
      docker run --rm -v "$src":/data:ro -v "$BACKUP_DIR":/backup alpine sh -c "tar czf '/backup/$out' -C /data . && chmod 600 '/backup/$out'"
    elif [ "$type" = bind ] && [ -d "$src" ]; then
      tar czf "$BACKUP_DIR/$out" -C "$src" .
    fi
    echo "  $dest -> $BACKUP_DIR/$out"
  done
  [ -n "${ENV_FILE[$CURRENT]}" ] && [ -f "${ENV_FILE[$CURRENT]}" ] && cp "${ENV_FILE[$CURRENT]}" "$BACKUP_DIR/$CURRENT.env_file" && chmod 600 "$BACKUP_DIR/$CURRENT.env_file"

  log "$CURRENT: updating $ctx to origin/main"
  git -C "$ctx" fetch -q origin main
  git -C "$ctx" merge-base --is-ancestor "${REQUIRED_COMMIT[$CURRENT]}" origin/main || die "origin/main in $ctx does not contain ${REQUIRED_COMMIT[$CURRENT]:0:7}"
  git -C "$ctx" merge -q --ff-only origin/main || die "main in $ctx cannot fast-forward to origin/main; reconcile it first"
  echo "  ${OLD_SHA[$CURRENT]:0:7} -> $(git -C "$ctx" rev-parse --short HEAD)"

  if [ "${NEEDS_KEY[$CURRENT]}" = 1 ]; then
    log "$CURRENT: generating the ledger signing key"
    mkdir -p "$SECRETS_DIR" && chmod 700 "$SECRETS_DIR"
    key_file="$SECRETS_DIR/$PROJECT-pgl-signing-key.pem"
    [ -f "$key_file" ] || { openssl genpkey -algorithm ed25519 -out "$key_file" 2>/dev/null || docker run --rm alpine/openssl genpkey -algorithm ed25519 > "$key_file"; }
    chmod 600 "$key_file"
    printf "\nPGL_SIGNING_KEY_PEM='%s'\n" "$(awk '{printf "%s\\n", $0}' "$key_file")" >> "${ENV_FILE[$CURRENT]}"
    echo "  key saved to $key_file (back it up off this machine) and added to ${ENV_FILE[$CURRENT]}"
  fi

  log "$CURRENT: rebuilding '$svc'"
  docker compose "${args[@]}" up -d --build "$svc" || rollback
  if wait_healthy "$svc" "${args[@]}"; then
    echo "  $CURRENT healthy on $(git -C "$ctx" rev-parse --short HEAD)"
  else
    rollback
  fi
done

if [ -n "$PGL_URL" ]; then
  log "Verifying the Capability OS links"
  PGL_URL=$PGL_URL CAPI_URL=$CAPI_URL CAPPO_URL=$CAPPO_URL "$SCRIPT_DIR/verify-capos-link.sh"
fi
log "Done. Backups: $BACKUP_DIR"
