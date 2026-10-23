#!/usr/bin/env bash
# Upgrades Genome Ledger (gnomledger) and CAPPO inside a running Veklom Compose stack on the
# Docker Desktop host, then verifies the links. On Windows, double-click Upgrade-Veklom.cmd,
# which runs scripts/veklom-upgrade.sh (staging first, then production). Direct use, from WSL
# or any shell with docker, git, curl, python3 and openssl:
#
#   scripts/upgrade-capos-stack.sh veklom-staging --dry-run       # print the plan, change nothing
#   scripts/upgrade-capos-stack.sh veklom-staging                 # plan, ask, upgrade
#   scripts/upgrade-capos-stack.sh veklom-capability-os-rc1 \
#     --pgl-url https://pgl.veklom.com --capi-url https://capi.veklom.com \
#     --cappo-url https://cappo.veklom.com
#
# Options:
#   --services gnomledger,cappo   which services to upgrade (default: both; capi is also known and
#                                 is upgraded on its own: --services capi)
#   --dry-run                     print the plan and stop
#   --yes                         do not ask for confirmation
#   --pgl-url/--capi-url/--cappo-url  public URLs for the final link check
#
# For each service it finds the container by its Compose labels (Windows paths in the labels are
# translated for WSL) and backs up the container's data volumes and env file. Then:
#   - a service built from source (`build:`) has its checkout moved to origin/main; uncommitted
#     changes are stashed and another branch is left for main, both listed in the plan first;
#   - a service that runs a prebuilt image (`image:` only) gets that image tag rebuilt from a
#     clean clone of origin/main.
# Only that service is recreated (--no-deps), and the script waits for it to be healthy. If it is
# not, everything is put back as it was (checkout, branch, stash, image, env file), the service
# is recreated from the previous version, and the script exits non-zero.
#
# gnomledger rules (docs/docker-desktop-deploy.md): API_KEY_SECRET and PGL_LEDGER_API_KEY are
# kept as they are; in prod a missing PGL_SIGNING_KEY_PEM is generated once, saved under
# ~/.veklom-secrets, and appended to the service's env_file.
set -euo pipefail

PROJECT=${1:-}
[ -n "$PROJECT" ] && shift || { sed -n '2,31p' "$0"; exit 2; }
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
declare -A REQUIRED_COMMIT=(
  [gnomledger]=97652cef61883b5a9c27e22db21f45c64889c385
  [cappo]=c0341b2305a17a8aa8a8bd6a77ce6a361b981908
  [capi]=084a5041b6d4c67fd63fe22600d9fb3aafeb776c
)
# Compose service names each component may have (full match). Override with e.g. GNOMLEDGER_SERVICE=api.
declare -A SERVICE_PATTERN=(
  [gnomledger]=${GNOMLEDGER_SERVICE:-'(gnomledger|pgl)([-_](api|backend|server))?'}
  [cappo]=${CAPPO_SERVICE:-'cappo([-_](api|backend|server))?'}
  [capi]=${CAPI_SERVICE:-'c-?api([-_](api|app|web|backend|server))?'}
)
declare -A HEALTH_CHECK=([gnomledger]='8001/health/ready' [cappo]='8002/health' [capi]='3003/health')
declare -A REPO_URL=(
  [gnomledger]=${GNOMLEDGER_REPO_URL:-https://github.com/reprewindai-dev/gnomledger.git}
  [cappo]=${CAPPO_REPO_URL:-https://github.com/reprewindai-dev/cappo-backend.git}
  [capi]=${CAPI_REPO_URL:-https://github.com/reprewindai-dev/cAPI.git}
)
HEALTH_TIMEOUT=${HEALTH_TIMEOUT:-240}
read -ra BUILD_FLAGS <<< "${VEKLOM_BUILD_FLAGS:-}"

umask 077  # backups and generated keys are readable by this user only
STAMP=$(date +%Y%m%d-%H%M%S)
BACKUP_DIR=${BACKUP_DIR:-$HOME/veklom-backups/$PROJECT-$STAMP}
SECRETS_DIR=${SECRETS_DIR:-$HOME/.veklom-secrets}
SCRIPT_DIR=$(cd "$(dirname "$0")" && pwd)

log() { printf '\n==> %s\n' "$*"; }
die() { printf '\nERROR: %s\n' "$*" >&2; exit 1; }
for tool in docker curl python3 openssl; do command -v "$tool" >/dev/null || die "$tool is required"; done
command -v git >/dev/null || command -v git.exe >/dev/null || die "git is required"

# Compose labels hold the paths Compose was started with. A stack started from Windows has
# C:\... paths; translate them when running in WSL.
to_local() {
  if [[ $1 =~ ^[A-Za-z]:[\\/] || $1 == \\\\* ]] && command -v wslpath >/dev/null; then wslpath -u "$1"; else printf '%s\n' "$1"; fi
}
# Checkouts on the Windows drive are driven with Windows git (its credentials and line endings).
use_win_git() { [[ $1 == /mnt/[a-zA-Z]/* ]] && command -v git.exe >/dev/null && command -v wslpath >/dev/null; }
gitc() {
  local dir=$1; shift
  if use_win_git "$dir"; then git.exe -C "$(wslpath -w "$dir")" "$@" | tr -d '\r'; else git -C "$dir" "$@"; fi
}
git_clone() { # URL DIR
  mkdir -p "$2"
  if use_win_git "$2"; then
    git.exe clone -q -c core.autocrlf=false "$1" "$(wslpath -w "$2")"
  else
    git clone -q -c core.autocrlf=false "$1" "$2"
  fi
}
src_root() { # where clean clones for image-only services live (the Windows profile under WSL)
  local winhome=""
  if command -v git.exe >/dev/null && command -v cmd.exe >/dev/null && command -v wslpath >/dev/null; then
    winhome=$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r') || true
  fi
  if [ -n "$winhome" ]; then echo "$(wslpath -u "$winhome")/veklom-upgrade/src"; else echo "$HOME/veklom-upgrade/src"; fi
}

# json_get FILE EXPR: evaluates a Python expression against the JSON in FILE (bound to d).
json_get() { python3 -c "import json,sys; d=json.load(open(sys.argv[1])); print($2)" "$1"; }

find_container() { # COMPONENT -> "name<TAB>service" of its one container in the project
  local found
  found=$(docker ps -a --filter "label=com.docker.compose.project=$PROJECT" \
    --format '{{.Names}}	{{.Label "com.docker.compose.service"}}' | grep -E "	(${SERVICE_PATTERN[$1]})\$" | sort -u -t '	' -k2,2)
  if [ -z "$found" ]; then
    echo "  no $1 service in $PROJECT; its services are: $(docker ps -a --filter "label=com.docker.compose.project=$PROJECT" --format '{{.Label "com.docker.compose.service"}}' | sort -u | tr '\n' ' ')" >&2
    return 1
  fi
  if [ "$(wc -l <<< "$found")" -gt 1 ]; then
    echo "  more than one $1 service in $PROJECT: $(cut -f2 <<< "$found" | tr '\n' ' ')" >&2
    return 1
  fi
  printf '%s\n' "$found"
}

health_ok() { # CONTAINER PORT/PATH -> 0 when the service answers 2xx from inside its container
  local url="http://127.0.0.1:$2"
  local py="import urllib.request; urllib.request.urlopen('$url', timeout=5)"
  local js="fetch('$url').then(r=>process.exit(r.ok?0:1),()=>process.exit(1))"
  docker exec "$1" python3 -c "$py" >/dev/null 2>&1 || docker exec "$1" python -c "$py" >/dev/null 2>&1 \
    || docker exec "$1" node -e "$js" >/dev/null 2>&1 || docker exec "$1" wget -qO /dev/null -T 5 "$url" >/dev/null 2>&1
}

wait_healthy() { # SERVICE COMPOSE_ARGS...
  local svc=$1; shift
  local name deadline=$((SECONDS + HEALTH_TIMEOUT))
  while [ $SECONDS -lt $deadline ]; do
    name=$(docker compose "$@" ps -q "$svc" 2>/dev/null | head -1)
    if [ -n "$name" ] && health_ok "$name" "${HEALTH_CHECK[$CURRENT]}"; then return 0; fi
    sleep 3
  done
  return 1
}

compose_up() { # SERVICE COMPOSE_ARGS... -> recreate only this service, never pulling over a local image
  local svc=$1; shift
  if [ "${MODE[$CURRENT]}" = build ]; then
    docker compose "$@" up -d --no-deps --build "$svc"
  else
    docker compose "$@" up -d --no-deps --pull never "$svc" || docker compose "$@" up -d --no-deps "$svc"
  fi
}

declare -a PLAN_LINES=()
declare -A CTX OLD_SHA COMPOSE_ARGS SVC_NAME CONTAINER ENV_FILE NEEDS_KEY MODE IMAGE OLD_IMAGE
declare -A ORIG_REF MAIN_BEFORE NEEDS_STASH STASHED

log "Inspecting Compose project '$PROJECT'"
docker info >/dev/null 2>&1 || die "cannot reach Docker. Start Docker Desktop, and turn on Settings > Resources > WSL integration for this distro"
IFS=, read -ra WANTED <<< "$SERVICES"
for CURRENT in "${WANTED[@]}"; do
  [ -n "${REQUIRED_COMMIT[$CURRENT]:-}" ] || die "unknown service '$CURRENT' (known: gnomledger, cappo, capi)"
  line=$(find_container "$CURRENT") || die "cannot tell which container is $CURRENT in $PROJECT; name its service with ${CURRENT^^}_SERVICE=<service> and rerun"
  CONTAINER[$CURRENT]=${line%%	*}
  SVC_NAME[$CURRENT]=${line##*	}
  svc=${SVC_NAME[$CURRENT]}
  wd=$(to_local "$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}' "${CONTAINER[$CURRENT]}")")
  files=$(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.config_files"}}' "${CONTAINER[$CURRENT]}")
  [ -d "$wd" ] || die "$svc was started from $wd, which this shell cannot see"
  args=(-p "$PROJECT" --project-directory "$wd")
  IFS=, read -ra cfgs <<< "$files"
  for f in "${cfgs[@]}"; do args+=(-f "$(to_local "$f")"); done
  COMPOSE_ARGS[$CURRENT]="${args[*]@Q}"

  cfg_json=$(mktemp)
  # --no-env-resolution keeps env_file paths in the output (older Compose lacks it and inlines them).
  docker compose "${args[@]}" config --no-env-resolution --format json > "$cfg_json" 2>/dev/null \
    || docker compose "${args[@]}" config --format json > "$cfg_json"
  ctx=$(json_get "$cfg_json" "(d['services']['$svc'].get('build') or {}).get('context','')")
  IMAGE[$CURRENT]=$(json_get "$cfg_json" "d['services']['$svc'].get('image','')")
  ENV_FILE[$CURRENT]=$(to_local "$(json_get "$cfg_json" "(lambda e: (e[0]['path'] if isinstance(e[0], dict) else e[0]) if e else '')(d['services']['$svc'].get('env_file') or [])")")
  rm -f "$cfg_json"
  OLD_IMAGE[$CURRENT]=$(docker inspect -f '{{.Image}}' "${CONTAINER[$CURRENT]}")
  NEEDS_STASH[$CURRENT]=0
  STASHED[$CURRENT]=0

  if [ -n "$ctx" ]; then
    MODE[$CURRENT]=build
    ctx=$(to_local "$ctx")
    gitc "$ctx" rev-parse --git-dir >/dev/null 2>&1 || die "$svc builds from $ctx, which is not a git checkout"
    gitc "$ctx" fetch -q origin main || die "cannot fetch origin main in $ctx (check git access to ${REPO_URL[$CURRENT]})"
    gitc "$ctx" merge-base --is-ancestor "${REQUIRED_COMMIT[$CURRENT]}" origin/main \
      || die "origin/main in $ctx does not contain ${REQUIRED_COMMIT[$CURRENT]:0:7}; is its origin ${REPO_URL[$CURRENT]}?"
    ORIG_REF[$CURRENT]=$(gitc "$ctx" rev-parse --abbrev-ref HEAD)
    OLD_SHA[$CURRENT]=$(gitc "$ctx" rev-parse HEAD)
    [ "${ORIG_REF[$CURRENT]}" = HEAD ] && ORIG_REF[$CURRENT]=${OLD_SHA[$CURRENT]}
    MAIN_BEFORE[$CURRENT]=$(gitc "$ctx" rev-parse -q --verify refs/heads/main || true)
    if [ -n "${MAIN_BEFORE[$CURRENT]}" ]; then
      gitc "$ctx" merge-base --is-ancestor "${MAIN_BEFORE[$CURRENT]}" origin/main \
        || die "local main in $ctx has commits that are not on origin/main; push or move them, then rerun"
    fi
    [ -z "$(gitc "$ctx" status --porcelain --untracked-files=no)" ] || NEEDS_STASH[$CURRENT]=1
    CTX[$CURRENT]=$ctx
    what="builds from $ctx (${ORIG_REF[$CURRENT]:0:12} @ ${OLD_SHA[$CURRENT]:0:7}); will move it to main @ $(gitc "$ctx" rev-parse --short origin/main)"
    [ "${NEEDS_STASH[$CURRENT]}" = 1 ] && what+="; will stash its uncommitted changes (get them back with: git stash pop)"
    [ "${ORIG_REF[$CURRENT]}" != main ] && what+="; will switch it from '${ORIG_REF[$CURRENT]:0:12}' to main"
  else
    MODE[$CURRENT]=image
    [ -n "${IMAGE[$CURRENT]}" ] || die "$svc has neither build: nor image: in its compose file"
    ctx="$(src_root)/$(basename "${REPO_URL[$CURRENT]}" .git)"
    if gitc "$ctx" rev-parse --git-dir >/dev/null 2>&1; then
      gitc "$ctx" fetch -q origin main || die "cannot fetch ${REPO_URL[$CURRENT]} into $ctx"
    else
      git_clone "${REPO_URL[$CURRENT]}" "$ctx" || die "cannot clone ${REPO_URL[$CURRENT]} (sign in to GitHub with git first)"
    fi
    gitc "$ctx" merge-base --is-ancestor "${REQUIRED_COMMIT[$CURRENT]}" origin/main \
      || die "origin/main of ${REPO_URL[$CURRENT]} does not contain ${REQUIRED_COMMIT[$CURRENT]:0:7}"
    CTX[$CURRENT]=$ctx
    what="runs image ${IMAGE[$CURRENT]}; will rebuild that tag from ${REPO_URL[$CURRENT]} main @ $(gitc "$ctx" rev-parse --short origin/main) (clone in $ctx)"
  fi

  NEEDS_KEY[$CURRENT]=0
  if [ "$CURRENT" = gnomledger ]; then
    env_now=$(docker inspect -f '{{range .Config.Env}}{{println .}}{{end}}' "${CONTAINER[$CURRENT]}")
    grep -q '^API_KEY_SECRET=.' <<< "$env_now" || die "$svc has no API_KEY_SECRET; refusing to upgrade (every API key is an HMAC under it)"
    grep -q '^PGL_LEDGER_API_KEY=.' <<< "$env_now" || echo "  warning: $svc has no PGL_LEDGER_API_KEY; cAPI and CAPPO cannot write to the ledger without it"
    if grep -qiE '^ENVIRONMENT=prod' <<< "$env_now" && ! grep -qE '^PGL_SIGNING_KEY_(PEM|PATH)=.' <<< "$env_now"; then
      [ -n "${ENV_FILE[$CURRENT]}" ] || die "$svc runs ENVIRONMENT=prod without PGL_SIGNING_KEY_PEM and has no env_file to add it to; give it an env_file in the compose file, then rerun"
      NEEDS_KEY[$CURRENT]=1
      what+="; will generate PGL_SIGNING_KEY_PEM into ${ENV_FILE[$CURRENT]}"
    fi
  fi
  PLAN_LINES+=("$CURRENT: service '$svc' (container ${CONTAINER[$CURRENT]}) $what")
done

log "Plan (backups go to $BACKUP_DIR)"
printf '  %s\n' "${PLAN_LINES[@]}"
echo "  Only these services are recreated; everything else in '$PROJECT' keeps running."
[ "$DRY_RUN" = 1 ] && { echo; echo "Dry run: nothing changed."; exit 0; }
if [ "$ASSUME_YES" != 1 ]; then
  read -r -p "Proceed? [y/N] " answer
  [ "$answer" = y ] || [ "$answer" = Y ] || { echo "Aborted. Nothing changed."; exit 1; }
fi
mkdir -p "$BACKUP_DIR"

restore_source() {
  local ctx=${CTX[$CURRENT]}
  if [ "${MODE[$CURRENT]}" = image ]; then
    docker tag "veklom-rollback/$CURRENT:$STAMP" "${IMAGE[$CURRENT]}"
    return 0
  fi
  if [ "${ORIG_REF[$CURRENT]}" = main ]; then
    gitc "$ctx" checkout -q -f -B main "${MAIN_BEFORE[$CURRENT]}"
  else
    gitc "$ctx" checkout -q -f "${ORIG_REF[$CURRENT]}"
    if [ -n "${MAIN_BEFORE[$CURRENT]}" ]; then gitc "$ctx" branch -q -f main "${MAIN_BEFORE[$CURRENT]}"; else gitc "$ctx" branch -q -D main 2>/dev/null || true; fi
  fi
  if [ "${STASHED[$CURRENT]}" = 1 ]; then gitc "$ctx" stash pop -q; fi
  return 0
}

rollback() {
  local svc=${SVC_NAME[$CURRENT]}
  eval "local args=(${COMPOSE_ARGS[$CURRENT]})"
  log "ROLLBACK $CURRENT: logs from the failed start"
  docker compose "${args[@]}" logs --tail 40 "$svc" || true
  restore_source || echo "  warning: could not fully restore ${CTX[$CURRENT]}; check it with git status" >&2
  if [ -f "$BACKUP_DIR/$CURRENT.env_file" ]; then cp "$BACKUP_DIR/$CURRENT.env_file" "${ENV_FILE[$CURRENT]}"; fi
  compose_up "$svc" "${args[@]}" || true
  if wait_healthy "$svc" "${args[@]}"; then
    echo "  $CURRENT is back on its previous version and healthy; its source, image and env file are as they were."
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
    # Through a container, so named volumes and Docker Desktop host paths both work.
    if docker run --rm -v "$src":/data:ro -v "$BACKUP_DIR":/backup alpine sh -c "tar czf '/backup/$out' -C /data . && chmod 600 '/backup/$out'"; then
      echo "  $dest -> $BACKUP_DIR/$out"
    else
      echo "  warning: could not back up $dest ($type $src)"
    fi
  done
  if [ -n "${ENV_FILE[$CURRENT]}" ] && [ -f "${ENV_FILE[$CURRENT]}" ]; then
    cp "${ENV_FILE[$CURRENT]}" "$BACKUP_DIR/$CURRENT.env_file"
  fi

  if [ "${MODE[$CURRENT]}" = build ]; then
    log "$CURRENT: moving $ctx to origin/main"
    if [ "${NEEDS_STASH[$CURRENT]}" = 1 ]; then
      gitc "$ctx" stash push -q -m "veklom-upgrade $STAMP" || rollback
      STASHED[$CURRENT]=1
      echo "  uncommitted changes stashed as 'veklom-upgrade $STAMP'"
    fi
    if [ -n "${MAIN_BEFORE[$CURRENT]}" ]; then
      if [ "${ORIG_REF[$CURRENT]}" != main ]; then gitc "$ctx" checkout -q main || rollback; fi
      gitc "$ctx" merge -q --ff-only origin/main || rollback
    else
      gitc "$ctx" checkout -q -b main origin/main || rollback
    fi
    echo "  ${OLD_SHA[$CURRENT]:0:7} -> $(gitc "$ctx" rev-parse --short HEAD)"
  else
    log "$CURRENT: building ${IMAGE[$CURRENT]} from origin/main"
    # Pin the running image first: once its tag moves and its container is replaced, Docker may delete it.
    docker tag "${OLD_IMAGE[$CURRENT]}" "veklom-rollback/$CURRENT:$STAMP"
    echo "  previous image kept as veklom-rollback/$CURRENT:$STAMP"
    gitc "$ctx" checkout -q -f -B main origin/main
    docker build "${BUILD_FLAGS[@]}" -t "${IMAGE[$CURRENT]}" "$ctx" || rollback
  fi

  if [ "${NEEDS_KEY[$CURRENT]}" = 1 ]; then
    log "$CURRENT: generating the ledger signing key"
    mkdir -p "$SECRETS_DIR" && chmod 700 "$SECRETS_DIR"
    key_file="$SECRETS_DIR/$PROJECT-pgl-signing-key.pem"
    [ -f "$key_file" ] || openssl genpkey -algorithm ed25519 -out "$key_file"
    chmod 600 "$key_file"
    printf "\nPGL_SIGNING_KEY_PEM='%s'\n" "$(awk '{printf "%s\\n", $0}' "$key_file")" >> "${ENV_FILE[$CURRENT]}"
    echo "  key saved to $key_file (copy it somewhere safe off this machine) and added to ${ENV_FILE[$CURRENT]}"
  fi

  log "$CURRENT: recreating '$svc'"
  compose_up "$svc" "${args[@]}" || rollback
  if wait_healthy "$svc" "${args[@]}"; then
    echo "  $CURRENT healthy on $(gitc "$ctx" rev-parse --short HEAD)"
    if [ "${STASHED[$CURRENT]}" = 1 ]; then echo "  your stashed changes in $ctx: git stash list"; fi
  else
    rollback
  fi
done

if [ -n "$PGL_URL" ]; then
  log "Verifying the Capability OS links"
  PGL_URL=$PGL_URL CAPI_URL=$CAPI_URL CAPPO_URL=$CAPPO_URL "$SCRIPT_DIR/verify-capos-link.sh"
fi
log "Done. Backups: $BACKUP_DIR"
