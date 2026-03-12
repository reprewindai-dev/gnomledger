# Security & Compliance Hardening

## Threat Model Summary

1. **Ledger Tampering:** Adversary attempts to rewrite or delete lifecycle events. Mitigation: append-only hash chain, S3 Object Lock, periodic notarization.
2. **Unauthorized Access:** Compromised credentials gaining access to sensitive agent data. Mitigation: SSO + MFA, RBAC, IP allowlists, short-lived tokens, anomaly detection.
3. **Billing Abuse:** Bypassing quota enforcement to issue certificates for free. Mitigation: pre-flight billing service checks, signed usage records, Stripe webhook reconciliation.
4. **Data Leakage:** Sensitive genome/runtime configs exfiltrated. Mitigation: encryption at rest, field-level encryption for secrets, DLP scanning, zero-trust service to service.
5. **Incident Suppression:** Operator attempts to hide an incident. Mitigation: immutable incident log, requirement for dual approval to delete/comment, investor-facing alerts on suspicious gaps.

## Security Controls

### Identity & Access Management
- **SSO + MFA** via Auth0/Okta for all human users; SCIM provisioning for enterprises.
- **Service Accounts** use mTLS certificates stored in AWS Secrets Manager with automatic rotation.
- **RBAC Policies** enforce minimum privileges; policy engine denies ledger mutation without `operator` scope.
- **Investor Demo Role** has read-only access to curated views without access to raw genome configs.

### Data Protection
- **Encryption at Rest:** Postgres (AWS KMS), S3 (SSE-KMS), Redis TLS.
- **Encryption in Transit:** TLS 1.3 everywhere, HSTS enforced, API response signing option for auditors.
- **Field-Level Protection:** Sensitive genome parameters stored using envelope encryption; decrypt on access with audit logging.

### Ledger Integrity
- Each event stores `prev_hash` and `event_hash`; nightly job notarizes root hash to external transparency service (e.g., OpenTimestamps or notarized email) for independent verification.
- Write path enforces idempotency keys to prevent replay attacks.
- Verification endpoint recalculates chain and emits alert on mismatch; Prometheus alert triggers PagerDuty.

### Compliance Alignment
- **EU AI Act / NIST AI RMF:** evidence artifacts generated via PDF exports referencing ledger event IDs.
- **SOC 2 / ISO 27001:** change management logs, access reviews, automated evidence collection via Drata/ConductorOne integration.
- **GDPR/PII:** data minimization, regional storage requirements enforced, right-to-erasure applied only to personal metadata (ledger remains but references anonymized).

### Monitoring & Incident Response
- SIEM ingestion (Loki → Splunk/Datadog) with detection rules for abnormal API key usage.
- Incident runbooks stored in `docs/operations/runbooks/` (future) with on-call rotation via PagerDuty.
- Incident logs automatically notify designated auditors; tamper detection if response not acknowledged within SLA.

### Backup & Recovery
- Postgres PITR with hourly snapshots retained 35 days.
- Ledger S3 bucket uses Object Lock (compliance mode) with 7-year retention; cross-region replication for DR.
- Quarterly restore drills validated via automated Terraform workspace.

### Key & Secret Management
- AWS KMS per environment; customer-managed keys option for Enterprise tier.
- Secrets stored in AWS Secrets Manager, rotated via Lambda; injected into pods via CSI driver.
- Stripe webhook signing secret rotated quarterly with automated test harness.

## Tamper Evidence & Auditability
- Every admin action recorded in `audit_log` table with cryptographic signature.
- Audit exports include Merkle proofs for ledger subsets, enabling third parties to validate without full data access.
- Frontend surfaces integrity indicators (green for verified chain, amber for pending validation) on investor dashboards.

## Policy & Governance
- **Change Management:** GitOps + pull request approvals required for production changes; ArgoCD audit trail retained.
- **Vendor Management:** Third-party risk reviews for Auth0, Stripe, hosting provider.
- **User Education:** Security banners in UI, inline prompts for incident logging best practices, quarterly policy acknowledgement.

These controls collectively meet the SecEd enforcement standard defined in the global directive and provide investors with confidence that PGL enforces serious accountability.
