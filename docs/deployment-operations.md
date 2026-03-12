# Deployment & Operations Playbook

## Environments

| Environment | Purpose | Hosting | Notes |
|-------------|---------|---------|-------|
| Dev | Internal feature work | Shared EKS namespace | Uses test Stripe keys, Auth0 dev tenant, lower rate limits |
| Staging | Pre-prod, investor dry runs | Dedicated EKS cluster | Mirrors prod config, runs against Stripe test mode, nightly data reset |
| Production | Customer & investor demos | Dedicated EKS cluster across 3 AZs | Uses prod Stripe, hardened network policies, autoscaling enabled |

All environments use separate AWS accounts with isolated VPCs, security groups, and secrets stores to enforce blast-radius containment.

## Infrastructure Components

- **Kubernetes (EKS/GKE):** Hosts FastAPI app, worker jobs, and Next.js frontend (served via Vercel/CloudFront depending on tier).
- **PostgreSQL:** Managed RDS with Multi-AZ; read replica for analytics. Parameters tuned for ledger append workloads.
- **Redis (ElastiCache):** Rate limiting, cache, background job coordination.
- **Object Storage:** S3 buckets for certificates, ledger exports, backups (Object Lock enabled).
- **CI/CD:** GitHub Actions → Docker build/push (ECR) → Trivy scan → ArgoCD sync → deployment to cluster.
- **Networking:** API served via AWS ALB with WAF rules; CloudFront CDN for frontend + certificate downloads.

## Deployment Workflow

1. **Merge to main** triggers CI pipeline:
   - Run unit/integration tests (pytest, Playwright).
   - Static analysis (ruff/mypy) and security scans (Bandit, Trivy).
   - Build Docker images for backend + worker; tag with Git SHA.
2. **Artifact promotion**
   - ArgoCD deploys to staging cluster; smoke tests (health, migration status, API contract) run automatically.
   - Manual approval (two-person rule) to promote to production.
3. **Blue/Green Deployments**
   - New pods deployed alongside old ones; once health checks pass, traffic shifts gradually via ALB weighted target groups.
4. **Database Migrations**
   - Alembic jobs run as init containers; backwards-compatible migrations required; destructive changes gated behind feature flags.

## Monitoring & Alerting

- **Metrics:** Prometheus scrapes (latency, error rate, certificate issuance/sec, ledger writes, queue lag). Grafana dashboards per module.
- **Logging:** Loki stack with structured JSON logs; retention 90 days. Investor demo events mirrored to BigQuery.
- **Tracing:** OpenTelemetry traces shipped to Tempo; used for debugging slow ledger writes or billing checks.
- **Alerts:** PagerDuty routing for P1 (API downtime, Stripe webhook failures, chain verification errors); Opsgenie for P2 (quota anomalies).

## Scaling Strategy

- HPA scales FastAPI pods based on CPU + custom metric (requests per second).
- Ledger ingestion uses SQS workers; scale worker deployments based on queue depth.
- PostgreSQL read replicas added for analytics; partition ledger tables monthly to keep indexes manageable.
- Object storage lifecycle moves cold ledger exports to Glacier after 90 days with instant retrieval stored elsewhere.

## Cost Controls

- AWS Budgets with alerts at 70/90/100% of forecast.
- Spot instances for stateless workers in dev/staging; prod uses reserved instances for predictability.
- Storage lifecycle policies (delete staging data after 14 days, compress logs).
- Autoscaling ceilings enforced via Terraform to prevent runaway costs.

## Incident Response & Support

1. Detection via alerts or customer ticket.
2. Triage playbook (docs/operations/runbooks/) determines severity, assigns incident commander.
3. Communication templates for investors/regulators, including ledger proof attachments.
4. Post-incident review within 48 hours; action items tracked in Jira and referenced in investor updates.

## Backup & DR

- Postgres: automated snapshots, PITR enabled; weekly full backups copied to secondary region.
- S3: Cross-region replication + Object Lock (7-year retention) for ledger data.
- Redis: daily snapshots stored encrypted.
- DR drills quarterly: restore full stack into isolated account using Terraform + database snapshots; verify chain integrity.

## Investor Demo Guide

1. **Pre-demo checklist:**
   - Staging environment seeded via `scripts/seed_demo.py`.
   - Investor role enabled with read-only dashboards.
   - Health dashboard displayed on secondary monitor.
2. **Demo flow:**
   - Issue new certificate via UI; highlight Stripe charge logs.
   - Show ledger timeline and lineage tree for Alpha/Beta.
   - Trigger incident entry and demonstrate immutable log + alert.
   - Display ARR dashboard sourced from real billing usage.
3. **Post-demo:**
   - Reset staging data (script) to maintain consistency.
   - Send investors ledger verification link and summary PDF.

This playbook ensures consistent, secure deployments and polished investor experiences while maintaining operational rigor.
