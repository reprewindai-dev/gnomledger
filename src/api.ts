import type {
  AgentDetail,
  BillingUsage,
  BootstrapResponse,
  LedgerEvent,
  LineageTreeNode,
  SessionState,
  UsageLimit
} from "./types";

const API_ROOT = "/api/v1";

function normalizeErrorMessage(raw: string, status: number) {
  if (!raw) {
    return `Request failed with status ${status}`;
  }

  try {
    const parsed = JSON.parse(raw) as { detail?: string };
    if (typeof parsed.detail === "string" && parsed.detail.trim()) {
      return parsed.detail;
    }
  } catch {
    return raw;
  }

  return raw;
}

async function request<T>(path: string, init?: RequestInit, session?: SessionState | null): Promise<T> {
  const headers = new Headers(init?.headers);
  headers.set("Content-Type", "application/json");
  if (session?.apiKey) {
    headers.set("x-api-key", session.apiKey);
  }

  const response = await fetch(`${API_ROOT}${path}`, {
    ...init,
    headers
  });

  if (!response.ok) {
    const text = await response.text();
    throw new Error(normalizeErrorMessage(text, response.status));
  }

  return (await response.json()) as T;
}

export async function getHealth(): Promise<{ status: string; timestamp: string }> {
  const response = await fetch("/health");
  if (!response.ok) {
    throw new Error("Health check failed");
  }
  return (await response.json()) as { status: string; timestamp: string };
}

export function bootstrapAccount(payload: {
  bootstrap_token: string;
  account_name: string;
  account_tier: "launch" | "scale" | "enterprise";
  admin_name: string;
}) {
  return request<BootstrapResponse>("/admin/bootstrap", {
    method: "POST",
    body: JSON.stringify(payload)
  });
}

export function listAgents(session: SessionState) {
  return request<AgentDetail[]>("/agents", undefined, session);
}

export function createAgent(session: SessionState, payload: unknown) {
  return request<AgentDetail>("/agents", {
    method: "POST",
    body: JSON.stringify(payload)
  }, session);
}

export function getAgentHistory(session: SessionState, agentId: string) {
  return request<LedgerEvent[]>(`/ledger/agents/${agentId}`, undefined, session);
}

export function verifyAgentHistory(session: SessionState, agentId: string) {
  return request<{
    valid: boolean;
    latest_event_hash: string | null;
    checked_events: number;
    first_event_at: string | null;
    last_event_at: string | null;
    errors: string[];
  }>(`/ledger/agents/${agentId}/verify`, undefined, session);
}

export function getLineageTree(session: SessionState, agentId: string) {
  return request<LineageTreeNode>(`/lineage/tree/${agentId}`, undefined, session);
}

export function getUsage(session: SessionState) {
  return request<BillingUsage[]>("/billing/usage", undefined, session);
}

export function getUsageLimit(session: SessionState, metric: string) {
  return request<UsageLimit>(`/billing/usage/${metric}/limit`, undefined, session);
}
