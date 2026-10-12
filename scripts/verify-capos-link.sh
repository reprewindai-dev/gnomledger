#!/usr/bin/env bash
# Checks that Genome Ledger (PGL), cAPI, CAPPO and PGL Studio are talking to each other.
#
#   PGL_URL=https://pgl.veklom.com CAPI_URL=https://capi.veklom.com CAPPO_URL=https://cappo.veklom.com \
#   STUDIO_URL=https://studio.example PGL_RUNTIME_KEY=... scripts/verify-capos-link.sh [--write]
#
# Read-only by default. --write also registers a throwaway agent and appends one cAPI-shaped
# evidence event, then verifies the hash chain; the ledger is append-only, so these records
# stay. Needs PGL_RUNTIME_KEY (the Capability OS runtime key, PGL_LEDGER_API_KEY).
# Exit status is the number of failed checks.
set -u

PGL_URL=${PGL_URL:-http://127.0.0.1:8001}
CAPI_URL=${CAPI_URL:-}
CAPPO_URL=${CAPPO_URL:-}
STUDIO_URL=${STUDIO_URL:-}
PGL_RUNTIME_KEY=${PGL_RUNTIME_KEY:-}
WRITE=0
[ "${1:-}" = "--write" ] && WRITE=1

failures=0
pass() { printf '  \033[32mPASS\033[0m %s\n' "$1"; }
fail() { printf '  \033[31mFAIL\033[0m %s\n' "$1"; failures=$((failures + 1)); }
skip() { printf '  SKIP %s\n' "$1"; }

# json EXPR: evaluates a Python expression against the JSON on stdin (bound to d).
json() { python3 -c "import json,sys
try:
    d = json.load(sys.stdin)
    print($1)
except Exception as exc:
    print('ERR', exc)"; }
get() { curl -sS -m 20 "$@" 2>/dev/null; }

echo "Genome Ledger: $PGL_URL"
ready=$(get "$PGL_URL/health/ready" | json 'd.get("status"), d.get("database")')
[ "$ready" = "ok ready" ] && pass "ready, database ready" || fail "health/ready: $ready"
paths=$(get "$PGL_URL/openapi.json" | json 'len(d["paths"])')
pass "API exposes $paths endpoints"
key=$(get "$PGL_URL/.well-known/pgl-signing-key" | json 'd.get("algorithm"), d.get("key_id")')
case "$key" in Ed25519*) pass "signing key published ($key)";; *) fail "signing key missing (old build?): $key";; esac
caps=$(get "$PGL_URL/api/v1/capabilities" | json 'd.get("contract_version")')
[ "$caps" = "pgl-execution-v1" ] && pass "capability contract pgl-execution-v1" || fail "capabilities: $caps"

if [ -n "$CAPI_URL" ]; then
  echo "cAPI: $CAPI_URL"
  reg=$(get "$CAPI_URL/api/v1/registry/services/gnomledger" | json 'd.get("authenticated"), d.get("stale")')
  [ "$reg" = "True False" ] && pass "gnomledger registered with cAPI (authenticated, fresh)" || fail "gnomledger registration: $reg"
  deps=$(get "$CAPI_URL/health/dependencies" | json '" ".join(k + "=" + str(v.get("state")) for k, v in d["dependencies"].items())')
  case "$deps" in *pgl=healthy*) pass "cAPI reaches the ledger ($deps)";; *) fail "cAPI dependencies: $deps";; esac
  case "$deps" in *cappo=healthy*) pass "cAPI reaches CAPPO";; *cappo=unconfigured*) skip "cAPI has no CAPPO configured";; *) fail "cAPI cannot reach CAPPO";; esac
  cappo_reg=$(get "$CAPI_URL/api/v1/registry/services/cappo" | json 'd.get("authenticated"), d.get("stale")')
  [ "$cappo_reg" = "True False" ] && pass "CAPPO registered with cAPI (authenticated, fresh)" || fail "CAPPO registration: $cappo_reg"
else
  skip "cAPI checks (set CAPI_URL)"
fi

if [ -n "$CAPPO_URL" ]; then
  echo "CAPPO: $CAPPO_URL"
  h=$(get "$CAPPO_URL/health" | json 'd.get("status")')
  [ "$h" = "ok" ] && pass "CAPPO healthy" || fail "CAPPO health: $h"
else
  skip "CAPPO checks (set CAPPO_URL)"
fi

if [ -n "$STUDIO_URL" ]; then
  echo "PGL Studio: $STUDIO_URL"
  h=$(get "$STUDIO_URL/health" | json 'd.get("status"), d.get("database")')
  [ "$h" = "ok ready" ] && pass "Studio proxies to the ledger" || fail "Studio /health: $h"
  code=$(curl -s -m 20 -o /dev/null -w '%{http_code}' "$STUDIO_URL/api/v1/agents")
  [ "$code" = 200 ] && pass "Studio's server key reads agents" || fail "Studio /api/v1/agents returned $code (PGL_STUDIO_API_KEY set?)"
else
  skip "Studio checks (set STUDIO_URL)"
fi

if [ "$WRITE" = 1 ]; then
  echo "Write path (appends to the ledger)"
  if [ -z "$PGL_RUNTIME_KEY" ]; then
    fail "--write needs PGL_RUNTIME_KEY"
  else
    auth=(-H "x-api-key: $PGL_RUNTIME_KEY" -H 'content-type: application/json')
    agent=$(get -X POST "$PGL_URL/api/v1/agents" "${auth[@]}" -d '{"agent_name":"capos-link-check","jurisdiction":"CA","genome":{"model_family":"link-check","model_version":"1","intended_use":"Capability OS link check","risk_category":"low"}}' | json 'd.get("agent_id")')
    case "$agent" in agent_*) pass "runtime key registers an agent ($agent)";; *) fail "agent registration: $agent";; esac
    if [ "${agent#agent_}" != "$agent" ]; then
      ev=$(get -X POST "$PGL_URL/api/v1/ledger/events" "${auth[@]}" -d "{\"agent_id\":\"$agent\",\"event_type\":\"custom\",\"actor\":\"capos-link-check\",\"summary\":\"covenant link check\",\"details\":{\"source\":\"capi\"}}" | json 'd.get("persisted"), d.get("event_id")')
      case "$ev" in True\ evt_*) pass "cAPI-shaped evidence appended (${ev#True })";; *) fail "evidence append: $ev";; esac
      v=$(get "$PGL_URL/api/v1/ledger/agents/$agent/verify" "${auth[@]}" | json 'd.get("valid"), d.get("checked_events")')
      case "$v" in True\ *) pass "hash chain verifies ($v)";; *) fail "chain verify: $v";; esac
    fi
  fi
fi

echo
[ "$failures" = 0 ] && echo "All checks passed." || echo "$failures check(s) failed."
exit "$failures"
