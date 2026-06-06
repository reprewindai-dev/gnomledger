export type RiskCategory = "low" | "medium" | "high";

export interface GenomePayload {
  model_family: string;
  model_version: string;
  architecture: string;
  tools: string[];
  permissions: string[];
  safety_rules: string[];
  runtime_config: Record<string, string>;
  intended_use: string;
  risk_category: RiskCategory;
}

export interface BootstrapResponse {
  api_key: string;
  api_key_prefix: string;
  account_id: number;
  role: string;
  scopes: string[];
}

export interface AgentDetail {
  agent_id: string;
  certificate_id: string;
  name: string;
  creator: string;
  jurisdiction: string;
  declared_purpose: string;
  status: string;
  genome: GenomePayload;
  parent_agent_ids: string[];
  created_at: string;
  certificate_uri: string | null;
  version_count: number;
  latest_genome_hash: string;
}

export interface LedgerEvent {
  event_id: string;
  event_type: string;
  actor: string;
  summary: string;
  details: Record<string, string | number | boolean | string[]>;
  prev_event_hash: string | null;
  event_hash: string;
  created_at: string;
}

export interface LineageTreeNode {
  agent_id: string;
  name: string;
  status: string;
  children: LineageTreeNode[];
}

export interface BillingUsage {
  metric: string;
  amount: number;
  period_start: string;
  period_end: string;
}

export interface UsageLimit {
  account_id: number;
  metric: string;
  used: number;
  limit: number;
  remaining: number;
}

export interface SessionState {
  apiKey: string;
  accountId: number;
  role: string;
}

export interface DemoBundle {
  agents: AgentDetail[];
  ledgerByAgent: Record<string, LedgerEvent[]>;
  lineageByAgent: Record<string, LineageTreeNode>;
  usage: BillingUsage[];
  usageLimit: UsageLimit;
}
