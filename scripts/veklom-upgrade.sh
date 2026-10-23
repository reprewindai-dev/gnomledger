#!/usr/bin/env bash
# Guided upgrade of the Veklom stack on the Docker Desktop host. Upgrade-Veklom.cmd (Windows)
# starts it in WSL; it also runs directly from WSL: scripts/veklom-upgrade.sh
#
# 1. Read-only report: what is running, where each Compose project was started from, and a dry
#    run of every upgrade below. Saved to ~/veklom-backups/stack-report-*.txt (and copied to
#    %USERPROFILE%\veklom-upgrade on Windows). Nothing changes in this step.
# 2. Each upgrade is offered on its own and runs only on "y":
#      Genome Ledger + CAPPO on staging, then on production (production only after staging
#      succeeded or when there is no staging project), then cAPI on staging and on production.
#    Each one backs up, upgrades a single service at a time and rolls back on failure
#    (scripts/upgrade-capos-stack.sh).
#
# STAGING_PROJECT / PROD_PROJECT override the Compose project names; CORE_SERVICES (default
# gnomledger,cappo) the services of the first upgrade.
set -uo pipefail

DIR=$(cd "$(dirname "$0")" && pwd)
UPGRADE="$DIR/upgrade-capos-stack.sh"
STAGING=${STAGING_PROJECT:-veklom-staging}
PROD=${PROD_PROJECT:-veklom-capability-os-rc1}
CORE=${CORE_SERVICES:-gnomledger,cappo}
PROD_URLS=(--pgl-url https://pgl.veklom.com --capi-url https://capi.veklom.com --cappo-url https://cappo.veklom.com)
STAMP=$(date +%Y%m%d-%H%M%S)
OUT=$HOME/veklom-backups
mkdir -p "$OUT"
REPORT=$OUT/stack-report-$STAMP.txt
LOG=$OUT/upgrade-$STAMP.log
STATE=$(mktemp -d)
trap 'rm -rf "$STATE"' EXIT

ask() { local a; read -r -p "$1 [y/N] " a; [[ $a == [yY] ]]; }
section() { printf '\n######## %s\n' "$*"; }
win_dir() { # %USERPROFILE%\veklom-upgrade as a WSL path, when running under WSL
  command -v cmd.exe >/dev/null && command -v wslpath >/dev/null || return 1
  local p; p=$(cd /mnt/c 2>/dev/null && cmd.exe /c 'echo %USERPROFILE%' 2>/dev/null | tr -d '\r') || return 1
  [ -n "$p" ] && echo "$(wslpath -u "$p")/veklom-upgrade"
}
project_exists() { [ -n "$(docker ps -aq --filter "label=com.docker.compose.project=$1" | head -1)" ]; }
dry_run() { # NAME PROJECT ARGS... -> runs the dry run, records ok/failed in $STATE/NAME
  local name=$1; shift
  if "$UPGRADE" "$@" --dry-run; then touch "$STATE/$name"; fi
}
run_step() { # NAME PROJECT ARGS... -> real upgrade, logged; records $STATE/NAME.done or .failed
  local name=$1; shift
  echo "---- $name: $UPGRADE $* --yes" >> "$LOG"
  "$UPGRADE" "$@" --yes 2>&1 | tee -a "$LOG"
  if [ "${PIPESTATUS[0]}" = 0 ]; then touch "$STATE/$name.done"; RESULTS+=("$name: upgraded"); return 0; fi
  touch "$STATE/$name.failed"; RESULTS+=("$name: FAILED and rolled back (see $LOG)"); return 1
}

echo "Veklom stack upgrade: Genome Ledger, CAPPO, cAPI"
echo "Step 1 only reads. Nothing changes until you answer y to a question."
if ! docker info >/dev/null 2>&1; then
  echo
  echo "Docker is not reachable from this WSL shell. Start Docker Desktop and turn on"
  echo "Settings > Resources > WSL integration for your default distro, then run this again."
  exit 1
fi

{
  section "Veklom stack report $STAMP (read-only)"
  echo "host: $(uname -sr); docker server $(docker version --format '{{.Server.Version}}' 2>&1)"
  for t in docker git git.exe python3 curl openssl wslpath; do printf '  %-8s %s\n' "$t" "$(command -v "$t" || echo missing)"; done

  section "Compose containers (project | service | container | image | status)"
  docker ps -a --filter label=com.docker.compose.project \
    --format '{{.Label "com.docker.compose.project"}} | {{.Label "com.docker.compose.service"}} | {{.Names}} | {{.Image}} | {{.Status}}' | sort

  section "Where each Compose project was started from"
  for p in $(docker ps -a --filter label=com.docker.compose.project --format '{{.Label "com.docker.compose.project"}}' | sort -u); do
    c=$(docker ps -aq --filter "label=com.docker.compose.project=$p" | head -1)
    echo "$p: $(docker inspect -f '{{index .Config.Labels "com.docker.compose.project.working_dir"}}  files: {{index .Config.Labels "com.docker.compose.project.config_files"}}' "$c")"
  done

  for p in "$STAGING" "$PROD"; do
    if ! project_exists "$p"; then section "Project $p: not found on this machine"; continue; fi
    section "Dry run: Genome Ledger + CAPPO in $p"
    dry_run "core-$p" "$p" --services "$CORE"
    section "Dry run: cAPI in $p"
    dry_run "capi-$p" "$p" --services capi
  done
} 2>&1 | tee "$REPORT"

if wd=$(win_dir); then mkdir -p "$wd" && cp "$REPORT" "$wd/" && REPORT_SHOWN="$(wslpath -w "$wd")\\$(basename "$REPORT")"; fi
echo
echo "Report saved: ${REPORT_SHOWN:-$REPORT}"
echo "Nothing has changed so far."

RESULTS=()
offer() { # NAME PROJECT LABEL ARGS...
  local name=$1 project=$2 label=$3; shift 3
  if [ ! -e "$STATE/$name" ]; then
    project_exists "$project" && RESULTS+=("$name: skipped, its dry run stopped with an error (see the report)")
    return 1
  fi
  echo
  if ask "Upgrade $label in '$project' now?"; then run_step "$name" "$project" "$@"; else RESULTS+=("$name: skipped by you"); return 1; fi
}

offer "core-$STAGING" "$STAGING" "Genome Ledger + CAPPO" --services "$CORE"
if [ -e "$STATE/core-$STAGING.failed" ]; then
  project_exists "$PROD" && RESULTS+=("core-$PROD: not offered, because staging failed")
elif [ -e "$STATE/core-$STAGING.done" ] || ! project_exists "$STAGING"; then
  offer "core-$PROD" "$PROD" "Genome Ledger + CAPPO (production)" --services "$CORE" "${PROD_URLS[@]}"
elif project_exists "$PROD"; then
  RESULTS+=("core-$PROD: not offered until staging is upgraded")
fi
offer "capi-$STAGING" "$STAGING" "cAPI"
if [ ! -e "$STATE/capi-$STAGING.failed" ]; then
  offer "capi-$PROD" "$PROD" "cAPI (production)" --services capi "${PROD_URLS[@]}"
fi

{
  section "Results"
  if [ ${#RESULTS[@]} -eq 0 ]; then echo "Nothing to upgrade."; else printf '  %s\n' "${RESULTS[@]}"; fi
  [ -f "$LOG" ] && echo "  full upgrade log: $LOG"
} | tee -a "$REPORT"
[ -n "${wd:-}" ] && cp "$REPORT" "$wd/" 2>/dev/null
echo
echo "Send the report (${REPORT_SHOWN:-$REPORT}) to Claude to confirm the result."
