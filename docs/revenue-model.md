# Revenue & Pricing Model

Project Genome Ledger (PGL) monetizes the accountability layer for AI systems by charging for certificate issuance, ledger storage, lineage analytics, and compliance automation. The platform targets regulated AI builders that must prove provenance, auditors that certify AI deployments, and enterprises exposing AI copilots to customers.

## Customer Segments

1. **Regulated AI Builders** — banks, insurers, healthcare networks, national security contractors deploying high-stakes AI agents. Need verifiable provenance, change control, and tamper-proof audit trails.
2. **AI Assurance & Audit Firms** — third-party assessors offering compliance packages (NIST AI RMF, EU AI Act) that require structured registries, lineage proof, and incident logs.
3. **Enterprise Platform Teams** — internal AI platform groups responsible for “copilot factories” across business units; they require centralized inventory, certificate issuance, and lifecycle policies.
4. **Government / Public Sector Programs** — agencies establishing AI assurance registries and vendor review pipelines.

## Value Proposition

- **Regulatory Readiness:** Automated issuance of AI birth certificates, lineage tracking, and ledger exports that align with EU AI Act, NIST AI RMF, ISO/IEC 42001, and internal policy audits.
- **Operational Control:** Per-agent lifecycle policies, incident logging, deployment attestations, and chargeback visibility across business units.
- **Investor-Grade Accountability:** Demonstrates governance maturity to stakeholders by exposing tamper-proof histories and verifiable lineage trees.

## Pricing Tiers

| Tier | Target User | Core Limits | Monthly Price | Overage | Notes |
|------|-------------|-------------|---------------|---------|-------|
| **Launch** | Small teams, pilot auditors | Up to 25 active agents, 10 GB ledger storage, 3 lineage trees | $749 | $30/agent, $0.50/GB | Includes PDF certificates, webhook notifications |
| **Scale** | Regulated builders | Up to 250 agents, 150 GB storage, 25 lineage trees, SSO | $4,950 | $25/agent, $0.35/GB | Adds custom branding, incident workflows, SIEM export |
| **Enterprise** | Banks, healthcare, gov | 1,000+ agents, dedicated cluster, unlimited lineage, private connectors | Custom | Usage-based | Includes on-prem edge, 24/7 support, audit concierge |

### Billing Mechanics
- **Per-Agent Certificate Fee:** Charged upon birth certificate issuance (non-refundable). Revocation and re-issuance incur new fees.
- **Ledger Storage Metering:** Aggregated monthly by GB across hot + cold storage, with automated tiered pricing.
- **Lineage Analytics:** Each rendered lineage tree beyond allowance bills at $15 per render for Launch tier and $5 for Scale.
- **Incident Response Add-on:** $1,500/month includes automated incident workflows, SLA-backed triage, and legal-ready exports.
- **API Usage Limits:** Signed JWT ensures requests carry account context; rate limiting tiers enforce 100/1,000/10,000 requests per minute.

## Payment & Access Control Flow

1. **Account Creation:** Users onboard via secure sign-up, choose tier, and enter payment details (Stripe Checkout + Customer Portal).
2. **Trial Guardrails:** 14-day Launch sandbox with 5 agent issuances and limited ledger retention. Exceeding limits triggers upgrade modal and API 402 responses.
3. **Billing Enforcement:**
   - Before certificate issuance, backend verifies quota via billing service; insufficient credits → payment-required event.
   - Ledger writes track estimated storage; nightly job reconciles bytes and records usage in billing_usage table.
   - Lineage render requests check allowance and decrement counters atomically.
4. **Revenue Analytics:** Events streamed to analytics warehouse (Snowflake/BigQuery) for MRR, churn, cohort reporting; investor dashboard displays live ARR.

## Onboarding & Upgrade Funnel

1. **Crowdfunding Landing Page CTA →** Book intro call or self-onboard to Launch tier.
2. **Guided Setup:**
   - Import existing agents via CSV/API.
   - Generate first birth certificate using curated wizard.
   - Run “Lifecycle Replay” demo with seeded data to experience ledger + lineage value.
3. **Activation Triggers:**
   - 3+ certificates issued within first week.
   - First incident log recorded.
   - Lineage tree shared with external auditor.
4. **Upgrade Prompts:**
   - Storage at 80% threshold.
   - Attempt to enable SSO or SIEM integration (Scale feature).
   - Activation of compliance pack (Enterprise feature) gates upgrade conversation.

## Crowdsourcing Pitch Hooks

- **Recurring Revenue:** Highlight contracted ARR via multi-year compliance deals.
- **Usage-Based Upside:** Growing AI fleets drive expansion revenue; per-agent fee is aligned with AI proliferation.
- **Defensible Moat:** Proprietary ledger + lineage data plus institutional integrations generate high switching cost.
- **Accountability Narrative:** Aligns with rising government mandates; investors fund infrastructure that de-risks AI deployment.

## KPIs for Investors

- ARR, NRR, payback period, average agents/account, ledger growth, incident reports logged, lineage renders per month.
- Compliance wins (number of audits passed using PGL exports).
- Time-to-certificate issuance (automation efficiency metric).

This revenue architecture positions PGL as the premium accountability layer for serious AI builders, providing clear monetization levers for crowdfunding investors.
