import type { DemoBundle, GenomePayload } from "./types";

export const defaultGenome: GenomePayload = {
  model_family: "GPT-Operator",
  model_version: "2026.06",
  architecture: "multi-agent orchestration",
  tools: ["browser", "ledger", "deploy"],
  permissions: ["issue_certificate", "write_ledger", "fork_lineage"],
  safety_rules: ["human_escalation", "audit_required", "jurisdiction_locked"],
  runtime_config: {
    temperature: "0.2",
    sandbox: "strict",
    trace_level: "forensic"
  },
  intended_use: "Production deployment and accountable lifecycle management",
  risk_category: "high"
};

export const demoBundle: DemoBundle = {
  agents: [
    {
      agent_id: "agent_alpha",
      certificate_id: "cert_alpha",
      name: "Alpha Sentinel",
      creator: "Reprewind Operator",
      jurisdiction: "CA-ON",
      declared_purpose: "Primary operational guardian for production agent governance",
      status: "active",
      genome: defaultGenome,
      parent_agent_ids: [],
      created_at: "2026-06-05T21:30:00Z",
      certificate_uri: "/artifacts/cert_alpha.json",
      version_count: 3,
      latest_genome_hash: "a3f1940a1ef3f0cce5d4e1d0f2a912be4412fa31"
    },
    {
      agent_id: "agent_beta",
      certificate_id: "cert_beta",
      name: "Beta Playbook",
      creator: "Reprewind Operator",
      jurisdiction: "US-DE",
      declared_purpose: "Runbook synthesis for incident response and deployment recovery",
      status: "active",
      genome: {
        ...defaultGenome,
        model_family: "GPT-Writer",
        intended_use: "Runbook generation and procedural fallback guidance",
        risk_category: "medium"
      },
      parent_agent_ids: ["agent_alpha"],
      created_at: "2026-06-05T21:44:00Z",
      certificate_uri: "/artifacts/cert_beta.json",
      version_count: 2,
      latest_genome_hash: "6c711cb10f32a8199df38e3f4cfe75ef8d8c4f7d"
    },
    {
      agent_id: "agent_gamma",
      certificate_id: "cert_gamma",
      name: "Gamma Archive",
      creator: "Reprewind Operator",
      jurisdiction: "UK-LON",
      declared_purpose: "Ledger compression, export integrity, and regulator playback bundles",
      status: "active",
      genome: {
        ...defaultGenome,
        model_family: "GPT-Archivist",
        intended_use: "Audit export packaging and evidence retention",
        risk_category: "medium"
      },
      parent_agent_ids: ["agent_alpha"],
      created_at: "2026-06-05T21:58:00Z",
      certificate_uri: "/artifacts/cert_gamma.json",
      version_count: 4,
      latest_genome_hash: "f32b1cf1c8cb2fdc23385a9de2fa5a775adbc123"
    }
  ],
  ledgerByAgent: {
    agent_alpha: [
      {
        event_id: "evt-001",
        event_type: "birth_registration",
        actor: "Reprewind Operator",
        summary: "Alpha Sentinel registered",
        details: { jurisdiction: "CA-ON", attestation: "certificate_issued" },
        prev_event_hash: null,
        event_hash: "A1A7CC91DDE91827364655B012778F11",
        created_at: "2026-06-05T21:30:00Z"
      },
      {
        event_id: "evt-002",
        event_type: "deployment",
        actor: "Release Captain",
        summary: "Deployment promoted to production",
        details: { version: "2026.06", lane: "mainnet" },
        prev_event_hash: "A1A7CC91DDE91827364655B012778F11",
        event_hash: "CC91827364655B012778F11A1A7DDE9",
        created_at: "2026-06-05T21:39:00Z"
      },
      {
        event_id: "evt-003",
        event_type: "test_audit",
        actor: "Assurance Runner",
        summary: "Regression and policy suite passed",
        details: { suite: "ops-core-v3", score: 98 },
        prev_event_hash: "CC91827364655B012778F11A1A7DDE9",
        event_hash: "BC778F11A1A7CC91827364655B0127DD",
        created_at: "2026-06-05T21:52:00Z"
      }
    ],
    agent_beta: [
      {
        event_id: "evt-101",
        event_type: "birth_registration",
        actor: "Reprewind Operator",
        summary: "Beta Playbook forked from Alpha Sentinel",
        details: { parent_agent_id: "agent_alpha", branch: "playbook" },
        prev_event_hash: null,
        event_hash: "0BETA00127364655B012778F11A1A7CD",
        created_at: "2026-06-05T21:44:00Z"
      }
    ],
    agent_gamma: [
      {
        event_id: "evt-201",
        event_type: "birth_registration",
        actor: "Reprewind Operator",
        summary: "Gamma Archive issued for compliance export",
        details: { parent_agent_id: "agent_alpha", branch: "archive" },
        prev_event_hash: null,
        event_hash: "0GAMMA0127364655B012778F11A1A7CE",
        created_at: "2026-06-05T21:58:00Z"
      }
    ]
  },
  lineageByAgent: {
    agent_alpha: {
      agent_id: "agent_alpha",
      name: "Alpha Sentinel",
      status: "active",
      children: [
        { agent_id: "agent_beta", name: "Beta Playbook", status: "active", children: [] },
        { agent_id: "agent_gamma", name: "Gamma Archive", status: "active", children: [] }
      ]
    },
    agent_beta: {
      agent_id: "agent_alpha",
      name: "Alpha Sentinel",
      status: "active",
      children: [{ agent_id: "agent_beta", name: "Beta Playbook", status: "active", children: [] }]
    },
    agent_gamma: {
      agent_id: "agent_alpha",
      name: "Alpha Sentinel",
      status: "active",
      children: [{ agent_id: "agent_gamma", name: "Gamma Archive", status: "active", children: [] }]
    }
  },
  usage: [
    { metric: "certificate_issuance", amount: 3, period_start: "2026-06-01T00:00:00Z", period_end: "2026-06-30T23:59:59Z" },
    { metric: "lineage_render", amount: 9, period_start: "2026-06-01T00:00:00Z", period_end: "2026-06-30T23:59:59Z" },
    { metric: "ledger_write", amount: 21, period_start: "2026-06-01T00:00:00Z", period_end: "2026-06-30T23:59:59Z" }
  ],
  usageLimit: {
    account_id: 1,
    metric: "certificate_issuance",
    used: 3,
    limit: 25,
    remaining: 22
  }
};
