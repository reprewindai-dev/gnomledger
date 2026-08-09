# Project Genome Ledger — Security & Compliance Posture

> [!IMPORTANT]
> Read [`../00_VEKLOM_BIBLE.md`](../00_VEKLOM_BIBLE.md) first. Security and compliance claims must be proven at the exact layer being described.

## What may be claimed from repository behavior

Only claim controls that current source/tests/runtime evidence demonstrate. Current core security/evidence concepts include:

- authenticated protected routes using the implemented API-key/RBAC model;
- persisted ledger records with hash-linking/chain verification behavior;
- database-backed identity, genome, certificate, ledger, lineage, and billing state;
- server-side validation and authorization where implemented;
- explicit failure rather than silent production demo fallback.

Use current source and tests to determine the exact implementation before making a customer-facing claim.

## Evidence semantics

- **Hash-linked** means tamper-evident; it does not mean physically undeletable.
- **Verified chain** means the implemented verification procedure passed; it does not automatically prove external anchoring or legal non-repudiation.
- **External finality** requires verification against the authoritative external anchor/system.
- **Compliance evidence** is not the same thing as certification.

## Claims that require separate proof

Do not claim the following unless independently verified in the deployed environment:

- SOC 2 Type II certification or compliance;
- ISO 27001 certification;
- HIPAA compliance;
- FIPS validation;
- S3 Object Lock / WORM retention;
- AWS KMS / Secrets Manager / RDS / EKS / ArgoCD controls;
- HSM, SGX, TDX, or hardware-enclave protection;
- SSO/SCIM/Okta/Auth0 deployment;
- SIEM/PagerDuty/Splunk/Datadog integration;
- multi-region DR/PITR/backup retention;
- TLS 1.3 “everywhere”;
- external notarization or on-chain finality.

Source code, config examples, or design documents are not proof that these controls are active.

## Secret handling

- Never commit production secrets.
- Use deployment secret management for runtime values.
- Never print tokens/private keys in logs, issues, reports, or chat.
- Verify key-management properties at the actual implementation boundary; do not infer hardware isolation from naming.

## Deployment boundary

For the verified Veklom environment, Coolify is deployment/runtime configuration truth. Host port `8000` belongs to Coolify, including its UI/API/MCP listener. Gnomledger may use internal Docker port `8000` behind Traefik without owning host port `8000`.

## Compliance language

Prefer precise statements such as:

- “the ledger exposes a chain-verification endpoint”;
- “this event is persisted and its hash chain verifies”;
- “this control is configured but not independently verified”;
- “this capability can produce evidence relevant to an audit.”

Avoid statements that a product “meets” or is “compliant with” a regulation/standard unless the legal/operational requirements and evidence actually support that conclusion.

## Historical document

The old AWS/enterprise-control security document is `ARCHIVED`; see [`archive/2026-08-09/security-compliance.md`](./archive/2026-08-09/security-compliance.md).
