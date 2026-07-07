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

// ---------------------------------------------------------------------------
// Migrated from pgl-studioai
// ---------------------------------------------------------------------------

export type IncidentSeverity = "low" | "medium" | "high" | "critical";
export type IncidentStatus = "open" | "investigating" | "resolved" | "closed";

export interface IncidentRecord {
  incident_id: string;
  agent_id: string;
  severity: IncidentSeverity;
  status: IncidentStatus;
  title: string;
  description: string;
  reporter: string;
  resolution_notes: string | null;
  created_at: string;
  resolved_at: string | null;
}

export type AuditReminderFrequency = "once" | "daily" | "weekly" | "monthly";

export interface AuditReminder {
  reminder_id: string;
  agent_id: string;
  title: string;
  message: string;
  frequency: AuditReminderFrequency;
  next_trigger_at: string;
  last_triggered_at: string | null;
  is_active: boolean;
  created_at: string;
}

export interface ChatMessage {
  id: string;
  role: "user" | "assistant";
  content: string;
  timestamp: string;
}

export interface NotaryChatRequest {
  message: string;
  agent_id?: string;
  model?: string;
}

export interface NotaryChatResponse {
  reply: string;
  model_used: string;
  input_tokens: number;
  output_tokens: number;
}

export interface GoogleSheetsSyncConfig {
  spreadsheet_id: string;
  sheet_name: string;
  agent_id?: string;
  include_ledger: boolean;
  include_incidents: boolean;
}

export interface GoogleSheetsSyncResult {
  rows_written: number;
  sheet_url: string;
  synced_at: string;
}

export interface ExecutionIdentityV1 {
  agent_id: string;
  identity_hash: string;
  genome_hash: string;
  certificate_id: string;
  jurisdiction: string;
  declared_purpose: string;
  risk_category: RiskCategory;
  issued_at: string;
  signature: string;
}
