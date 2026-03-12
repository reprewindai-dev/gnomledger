# Roadmap & Execution Timeline

## Phase 1 — Foundation (Weeks 1-3)
- Finalize revenue contracts with design partners.
- Implement FastAPI backend skeleton, database migrations, and core registry endpoints.
- Build initial Next.js dashboard with auth and certificate issuance wizard.
- Configure Stripe integration (billing, webhook, customer portal).
- Deliver investor-ready data room (docs already prepared in this repo).

## Phase 2 — Ledger & Lineage Depth (Weeks 4-6)
- Complete append-only ledger implementation with hash verification and cold storage export.
- Ship lineage DAG visualization with fork playback.
- Implement incident workflow, audit exports, and analytics events.
- Harden RBAC, rate limiting, and logging.

## Phase 3 — Security & Compliance (Weeks 7-9)
- Finalize tamper-proofing (S3 object lock, notarization jobs).
- Achieve SOC2 readiness artifacts (policies, monitoring, evidence collection).
- Expand billing metering and quota enforcement.

## Phase 4 — Launch & Investor Push (Weeks 10-12)
- Finish investor demo automation, metrics dashboards, and crowdfunding landing assets.
- Run staging/production cutover with blue/green deployments.
- Engage crowdsourced investors with recorded demo + self-serve sandbox access.
