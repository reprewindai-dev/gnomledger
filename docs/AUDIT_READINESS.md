# Audit readiness: agent registration, certificate and ledger

What an auditor or regulator can check in Gnomledger to accept that an AI agent is owned,
bounded, accountable and replayable, which field answers which question, and what is still
not covered.

This document describes what the software records. It is not legal advice; references to the
EU AI Act explain why a default was chosen, not whether a system complies.

## Genome vs task lifetime

Veklom agents are ephemeral task agents: one spawns, does one task, and is revoked.

- The **genome** (registration + birth certificate) is registered **once** for a kind of
  agent. It holds identity, lineage, ownership, accountability, bounds and the CAPPO
  capability packages the agent may mount.
- **Every task** is an ephemeral spawn under a single-use CAPPO permit. The permit references
  the genome (`agent_id`, `genome_hash`), and the task appends its evidence
  (`pre_execution_authorization`, `post_execution_attestation`) to that genome's ledger chain.
- The genome is **not** re-registered per task. It changes only through
  `PATCH /agents/{agent_id}/genome` (with a reason, see below) and ends with
  `POST /agents/{agent_id}/decommission`.
- The genome declares which models the agent may use (`declared_models`). The model a task
  **actually** used belongs on that task's execution evidence as `model_used` (CAPPO's run
  record), and it must be one of the declared models. `POST /agents/execution/validate`
  refuses an undeclared `model_used`; the pre/post execution evidence schemas accept
  `model_used`.

## Who is accountable

The accountable party is the **operator**, never the agent. The agent is a generic,
disposable executor named by a server-generated handle
`<OperatorInitials>-<OperatorShortId>-<runSeq>` (for example `AM-133f1339-17`, the operator's
17th registration). The handle is derived from the authenticated account and cannot be
supplied by the client:

- OperatorInitials: the account owner's full name (`admin_full_name` at bootstrap), falling
  back to the account name.
- OperatorShortId: first 8 hex of SHA-256 of the account id (accounts here have integer ids,
  not UUIDs).
- runSeq: per account, never reused.

## Field map: auditor question to field

| Auditor question | Where it is answered | Fields |
|---|---|---|
| **Who owns it / who is accountable?** | genome, certificate `accountability` | `accountable_owner {name, role, email, organization}`, `registered_by` (API key that registered it, from the auth context), `creator`, `agent_handle` |
| Who do I call when it goes wrong? | genome, certificate `accountability` | `incident_contact` (email or http(s) URL) |
| Which organizations carry the EU AI Act provider / deployer roles? | genome, certificate `accountability` | `provider`, `deployer` |
| **What is it for?** | genome, certificate `bounded_use`, `context` | `intended_use`, `industry`, `jurisdiction` |
| **What are its limits?** | genome, certificate `bounded_use` | `out_of_scope_uses`, `known_limitations`, `data_categories` (none, personal, special_category, financial, health, credentials, public) |
| How risky is it? | genome, certificate `bounded_use` | `regulatory_risk_class` (prohibited, high_risk, limited, minimal, unassessed) + `risk_rationale`; legacy `risk_category` (low/medium/high) kept |
| **Who can stop it?** | genome, certificate `oversight` | `oversight {stop_mechanism, oversight_contact, escalation_path}` |
| Does it run without a human, and who decided that? | genome, certificate `run_mode`, ledger | `run_mode` (human_in_the_loop, autonomous); certificate `run_mode.authorized_by` + `authorized_at`; a later switch records `run_mode_authorization` on the `mutation_update` event |
| **What can it actually do?** | certificate `authority` | `capability_refs` (CAPPO capability packages; CAPPO enforces these). `permissions` and `safety_rules` are recorded as declarative only; `tools` are checked only when a runtime calls `execution/validate` |
| Which models does it use? | genome, certificate `model` | `declared_models [{provider, identifier, role, family, version}]`; single-model fields read as one entry; per task: `model_used` on execution evidence |
| Is the deployed configuration the registered one? | genome, certificate `configuration_integrity` | `system_prompt_sha256` (digest only; prompt text is refused), `code_commit`, `image_digest`, `tool_versions` |
| **What changed, and who approved it?** | genome versions, `mutation_update` events | `reason` (required), `changed_by` (API key, account, role from the auth context), `declared_actor`, `previous_genome_hash`, `new_genome_hash`, `previous_version`, `new_version`, `changed_fields` |
| Was it retired, by whom, why? | `decommission` event, agent `status` | `reason` (required), `decommissioned_by`, `previous_status`; status `decommissioned` |
| What was left out at registration? | certificate | `missing_accountability_fields`, `missing_integrity_fields` (gaps are listed, not silent) |
| **Can I verify independently?** | public key, certificate, checkpoint, audit bundle | see below |
| **How long are records kept?** | genome, certificate `retention` | `log_retention_days` (default and minimum 180), plus the retention behaviour below |

## Verifying independently

1. Fetch the public key: `GET /.well-known/pgl-signing-key` (also `GET /api/v1/ledger/signing-key`).
   It returns `key_id`, `public_key_pem` and a `jwk` (OKP / Ed25519).
2. Signed objects: birth certificate (`certificate` + `signature`), checkpoint (all fields
   except `signature`), audit bundle (all fields except `bundle_signature`). Each signature is
   Ed25519 over the *pgl-c14n* bytes: UTF-8 JSON, keys sorted, separators `,` and `:`, no
   whitespace, non-ASCII escaped (Python `json.dumps(obj, sort_keys=True, separators=(",", ":"))`).
   Signature values are base64url without padding.
3. `genome_hash` is SHA-256 of the pgl-c14n bytes of the stored genome payload. Each
   `event_hash` is SHA-256 of the pgl-c14n bytes of `{event_id, event_type, agent_id, actor,
   summary, details, prev_event_hash, created_at}` with `created_at` taken from
   `created_at_canonical` in the audit bundle.
4. Checkpoints: keep a copy of `GET /ledger/agents/{agent_id}/checkpoint`. Later, `POST` it to
   `/ledger/checkpoints/verify` (no auth). It reports `extends_checkpoint: false` if events were
   removed (the chain is shorter, or the event at the checkpoint position has a different
   hash) or rewritten (even when every later hash was recomputed so the chain alone still
   verifies). Nothing about the chain is disclosed unless the checkpoint's signature verifies.
5. Audit bundle: `GET /ledger/agents/{agent_id}/audit-bundle` (account-scoped) returns the
   agent, every genome version, the signed certificate, the full event chain, a fresh signed
   checkpoint, verification results and the public key, signed as a whole. Everything above
   can be checked from the bundle alone.

## Retention

- `log_retention_days` defaults to 180 and values below 180 are refused. The default reflects
  the six-month minimum that EU AI Act Article 19 sets for logs of high-risk AI systems.
- The service has no delete endpoint for agents, genome versions, certificates or ledger
  events. ORM relationships no longer cascade deletes from accounts or agents, ORM deletes of
  these records raise, and ledger events, genome versions, certificate signatures and agent
  handles are append-only at the ORM layer. An account with registered agents cannot be
  deleted through the ORM.
- Agents leave service through `POST /agents/{agent_id}/decommission`, which keeps every
  record; a decommissioned agent fails `execution/validate` and its genome can no longer change.

## Backward compatibility

- The original registration shape (`agent_name`, `creator`, `jurisdiction`, genome with
  `model_family`, `model_version`, `architecture`, `tools`, `permissions`, `safety_rules`,
  `runtime_config`, `intended_use`, `risk_category`) still registers, and its genome hash is
  unchanged: the canonical genome omits newer fields left at their defaults.
- Certificates issued before signing are served with `signature_status: "unsigned_legacy"` and
  their gaps computed from the birth genome. They are not re-signed after the fact.
- Breaking by design: `PATCH /genome` now requires `reason` (422 without it), and
  `decommission` events can only be written by the decommission endpoint.

## Not covered yet

- Ledger events are hash-chained and covered by signed checkpoints, but are not individually
  signed.
- No external RFC 3161 timestamp or third-party witness anchors checkpoints. A checkpoint
  detects truncation or rewrite only for a party that kept an earlier copy; nothing is
  published to a transparency log.
- Only the current signing key is published; there is no key rotation history or revocation
  list, so signatures made with a retired key cannot be checked through the service.
- Declared fields (owner, limits, data categories, permissions, model declarations) are the
  registrant's statements. The ledger records and signs them; it does not verify them.
  `capability_refs` are enforced by CAPPO, not by this ledger.
- `model_used` per task is accepted and checked when supplied, but CAPPO's execute/evidence
  path must record it on every run for the per-task model trail to be complete.
- Retention guards act at the ORM layer. Direct database access can still delete or alter
  rows; checkpoints held outside the ledger expose that, but do not prevent it.
- Incident records and audit reminders can still be deleted through their API endpoints.
- The operator short id is derived from the account's integer id, not from an identity
  provider UUID, and handles count registrations per account rather than per human operator
  within an account.
- `log_retention_days` is a declared minimum; there is no automated purge or legal-hold
  workflow, because nothing is purged.
