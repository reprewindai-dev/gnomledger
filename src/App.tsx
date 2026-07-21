import {
  Activity,
  Binary,
  BookLock,
  Bot,
  ChevronRight,
  Fingerprint,
  GitBranch,
  Layers3,
  ReceiptText,
  ShieldCheck,
  Sparkles
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { useEffect, useMemo, useState } from "react";

import {
  bootstrapAccount,
  createAgent,
  getAgentHistory,
  getHealth,
  getLineageTree,
  getUsage,
  getUsageLimit,
  listAgents,
  verifyAgentHistory
} from "./api";
import { defaultGenome, demoBundle } from "./data";
import type {
  AgentDetail,
  BillingUsage,
  DemoBundle,
  GenomePayload,
  LedgerEvent,
  LineageTreeNode,
  SessionState,
  UsageLimit
} from "./types";

const sessionStorageKey = "pgl-session";
type WorkspaceSection = "registry" | "certificates" | "ledger" | "lineage" | "billing" | "investor";
const demoSession: SessionState = {
  apiKey: "demo-mode",
  accountId: 0,
  role: "investor"
};
const navItems: Array<{ label: string; icon: LucideIcon; section: WorkspaceSection }> = [
  { label: "Registry", icon: Bot, section: "registry" },
  { label: "Certificates", icon: BookLock, section: "certificates" },
  { label: "Ledger", icon: ReceiptText, section: "ledger" },
  { label: "Lineage", icon: GitBranch, section: "lineage" },
  { label: "Billing", icon: Activity, section: "billing" },
  { label: "Investor Mode", icon: Sparkles, section: "investor" }
];

function readSession(): SessionState | null {
  const raw = window.localStorage.getItem(sessionStorageKey);
  return raw ? (JSON.parse(raw) as SessionState) : null;
}

function writeSession(session: SessionState | null) {
  if (!session) {
    window.localStorage.removeItem(sessionStorageKey);
    return;
  }
  window.localStorage.setItem(sessionStorageKey, JSON.stringify(session));
}

function tokenRows(genome: GenomePayload) {
  return [
    { label: "Model family", value: genome.model_family },
    { label: "Version", value: genome.model_version },
    { label: "Architecture", value: genome.architecture },
    { label: "Risk", value: genome.risk_category }
  ];
}

function flattenLineage(node: LineageTreeNode, depth = 0): Array<LineageTreeNode & { depth: number }> {
  return [{ ...node, depth }, ...node.children.flatMap((child) => flattenLineage(child, depth + 1))];
}

function downloadJson(filename: string, payload: unknown) {
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = filename;
  anchor.click();
  URL.revokeObjectURL(url);
}

export default function App() {
  const [session, setSession] = useState<SessionState | null>(() => readSession());
  const [health, setHealth] = useState<string>("checking");
  const [bootstrapState, setBootstrapState] = useState({
    bootstrap_token: "",
    account_name: "Genome Portfolio",
    account_tier: "launch" as const,
    admin_name: "owner@genomeledger.ai"
  });
  const [issueForm, setIssueForm] = useState({
    agent_name: "Sentinel-Prime",
    creator: "Reprewind Operator",
    jurisdiction: "CA-ON",
    genome: defaultGenome,
    parent_agent_ids: [] as string[]
  });
  const [agents, setAgents] = useState<AgentDetail[]>([]);
  const [selectedAgentId, setSelectedAgentId] = useState<string>("");
  const [ledgerEvents, setLedgerEvents] = useState<LedgerEvent[]>([]);
  const [lineage, setLineage] = useState<LineageTreeNode | null>(null);
  const [usage, setUsage] = useState<BillingUsage[]>([]);
  const [usageLimit, setUsageLimit] = useState<UsageLimit | null>(null);
  const [chainStatus, setChainStatus] = useState<{
    status: "verified" | "unmeasured" | "blocked";
    valid: boolean | null;
    checked_events: number;
  } | null>(null);
  const [busy, setBusy] = useState<string>("");
  const [message, setMessage] = useState<string>("");
  const [demoMode, setDemoMode] = useState<boolean>(true);
  const [activeSection, setActiveSection] = useState<WorkspaceSection>("certificates");
  const activeSession = session ?? (demoMode ? demoSession : null);

  useEffect(() => {
    getHealth()
      .then((response) => setHealth(response.status))
      .catch(() => setHealth("error"));
  }, []);

  useEffect(() => {
    if (!activeSession) {
      return;
    }
    void refreshWorkspace(activeSession);
  }, [activeSession]);

  useEffect(() => {
    if (!activeSession || !selectedAgentId) {
      return;
    }
    void Promise.all([
      getAgentHistory(activeSession, selectedAgentId).then(setLedgerEvents),
      getLineageTree(activeSession, selectedAgentId).then(setLineage),
      verifyAgentHistory(activeSession, selectedAgentId).then((result) =>
        setChainStatus({ status: result.status, valid: result.valid, checked_events: result.checked_events })
      )
    ]).catch((error: Error) => {
      const demoLedger = demoBundle.ledgerByAgent[selectedAgentId] ?? [];
      const demoLineage = demoBundle.lineageByAgent[selectedAgentId] ?? null;
      setLedgerEvents(demoLedger);
      setLineage(demoLineage);
      setChainStatus({ status: "unmeasured", valid: null, checked_events: demoLedger.length });
      setMessage(session ? error.message : "Investor replay is loaded from the local ledger snapshot.");
    });
  }, [activeSession, selectedAgentId]);

  useEffect(() => {
    if (session || demoMode) {
      return;
    }
    setAgents([]);
    setLedgerEvents([]);
    setLineage(null);
    setUsage([]);
    setUsageLimit(null);
    setSelectedAgentId("");
    setChainStatus(null);
    setMessage("");
  }, [demoMode, session]);

  function loadDemoBundle(bundle: DemoBundle, nextMessage: string) {
    setAgents(bundle.agents);
    setUsage(bundle.usage);
    setUsageLimit(bundle.usageLimit);
    setSelectedAgentId((current) => current || bundle.agents[0]?.agent_id || "");
    setMessage(nextMessage);
  }

  async function refreshWorkspace(activeSession: SessionState) {
    try {
      const [nextAgents, nextUsage, nextLimit] = await Promise.all([
        listAgents(activeSession),
        getUsage(activeSession),
        getUsageLimit(activeSession, "certificate_issuance")
      ]);
      setAgents(nextAgents);
      setUsage(nextUsage);
      setUsageLimit(nextLimit);
      if (nextAgents.length > 0) {
        setSelectedAgentId((current) => current || nextAgents[0].agent_id);
      }
      setMessage("");
    } catch (error) {
      loadDemoBundle(demoBundle, "Live registry unreachable. Investor replay data is loaded locally.");
    }
  }

  async function handleBootstrap() {
    setBusy("bootstrap");
    try {
      const response = await bootstrapAccount(bootstrapState);
      const nextSession: SessionState = {
        apiKey: response.api_key,
        accountId: response.account_id,
        role: response.role
      };
      writeSession(nextSession);
      setSession(nextSession);
      setMessage("Bootstrap complete. Owner key issued and workspace unlocked.");
    } catch (error) {
      loadDemoBundle(demoBundle, (error as Error).message);
    } finally {
      setBusy("");
    }
  }

  async function handleIssueCertificate() {
    if (!session) {
      setMessage("Connect a live owner key to issue a new certificate.");
      return;
    }
    setBusy("issue");
    try {
      const created = await createAgent(session, issueForm);
      await refreshWorkspace(session);
      setSelectedAgentId(created.agent_id);
      setMessage(`Certificate ${created.certificate_id} issued for ${created.name}.`);
    } catch (error) {
      setMessage((error as Error).message);
    } finally {
      setBusy("");
    }
  }

  const selectedAgent = useMemo(
    () => agents.find((agent) => agent.agent_id === selectedAgentId) ?? null,
    [agents, selectedAgentId]
  );

  const lineageRows = lineage ? flattenLineage(lineage) : [];
  const usageByMetric = useMemo(
    () => Object.fromEntries(usage.map((row) => [row.metric, row.amount])),
    [usage]
  );

  function focusSection(section: WorkspaceSection) {
    setActiveSection(section);
    document.getElementById(section)?.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  function handleExportCompliancePacket() {
    if (!selectedAgent) {
      setMessage("Select an agent before exporting a compliance packet.");
      return;
    }

    downloadJson(`${selectedAgent.agent_id}-compliance-packet.json`, {
      exported_at: new Date().toISOString(),
      mode: session ? "live" : "investor_replay",
      agent: selectedAgent,
      ledger_events: ledgerEvents,
      lineage,
      chain_status: chainStatus,
      usage_limit: usageLimit
    });
    setMessage(`Compliance packet exported for ${selectedAgent.name}.`);
  }

  function handleGenerateInvestorReplay() {
    const replayPayload = {
      exported_at: new Date().toISOString(),
      selected_agent_id: selectedAgentId,
      bundle: demoBundle,
      current_agent: selectedAgent,
      current_ledger: ledgerEvents,
      current_lineage: lineage
    };
    downloadJson(`${selectedAgentId || "investor"}-replay.json`, replayPayload);
    setMessage("Investor replay package generated.");
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand-block">
          <div className="brand-mark">
            <Fingerprint size={20} />
          </div>
          <div>
            <p className="eyeline">Project Genome Ledger</p>
            <h1>Control plane</h1>
          </div>
        </div>

        <nav className="nav-stack">
          {navItems.map(({ label, icon: Icon, section }) => (
            <button
              className={`nav-item ${activeSection === section ? "active" : ""}`}
              key={label}
              onClick={() => focusSection(section)}
            >
              <Icon size={16} />
              <span>{label}</span>
            </button>
          ))}
        </nav>

        <div className="investor-tile">
          <p>Investor scenario</p>
          <strong>Alpha/Beta lifecycle replay</strong>
          <span>Demo mode armed</span>
        </div>
      </aside>

      <main className="workspace">
        <header className="topbar">
          <div>
            <p className="status-line">
              Runtime <span className={`health-pill health-${health}`}>{health}</span>
            </p>
            <h2>Issue and govern every agent as a first-class asset.</h2>
          </div>
          <div className="topbar-actions">
            <button
              className="ghost-button"
              onClick={() => {
                writeSession(null);
                setSession(null);
                setAgents([]);
                setLedgerEvents([]);
                setLineage(null);
                setUsage([]);
                setUsageLimit(null);
                setSelectedAgentId("");
                setChainStatus(null);
                setMessage(demoMode ? "Live owner key removed. Investor replay remains available." : "");
              }}
            >
              Reset local key
            </button>
            <button className="primary-button" onClick={handleIssueCertificate} disabled={!session || busy === "issue"}>
              Issue Birth Certificate
            </button>
          </div>
        </header>

        <section className="utility-bar">
          <div className="utility-chip">
            <span>Investor Demo Mode</span>
            <button className={`toggle-chip ${demoMode ? "on" : ""}`} onClick={() => setDemoMode((current) => !current)}>
              <i />
            </button>
          </div>
          <div className="utility-chip">
            <span>View as</span>
            <strong>{activeSession?.role ?? "guest"}</strong>
          </div>
          <div className="utility-chip">
            <span>Network</span>
            <strong>{session ? "Live registry" : demoMode ? "Investor replay" : "Offline"}</strong>
          </div>
        </section>

        {message ? <div className="message-strip">{message}</div> : null}

        <section className="hero-grid" id="certificates">
          <div className="issue-panel">
            <div className="panel-head">
              <span>Certificate issuance workspace</span>
              <strong>Hash preview locked to genome payload</strong>
            </div>

            {!activeSession ? (
              <div className="bootstrap-grid">
                <div className="bootstrap-copy">
                  <h3>Bootstrap the registry once, then operate from the owner key.</h3>
                  <p>
                    This connects the account, issues the first privileged key, and unlocks the registry, ledger,
                    lineage, and billing surfaces in the same console.
                  </p>
                </div>
                <div className="bootstrap-form">
                  <label>
                    Bootstrap token
                    <input
                      value={bootstrapState.bootstrap_token}
                      onChange={(event) =>
                        setBootstrapState((current) => ({ ...current, bootstrap_token: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Account name
                    <input
                      value={bootstrapState.account_name}
                      onChange={(event) =>
                        setBootstrapState((current) => ({ ...current, account_name: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Owner identity
                    <input
                      value={bootstrapState.admin_name}
                      onChange={(event) =>
                        setBootstrapState((current) => ({ ...current, admin_name: event.target.value }))
                      }
                    />
                  </label>
                  <button className="primary-button" onClick={handleBootstrap} disabled={busy === "bootstrap"}>
                    {busy === "bootstrap" ? "Bootstrapping..." : "Create owner workspace"}
                  </button>
                </div>
              </div>
            ) : (
              <div className="issue-grid">
                <div className="form-cluster">
                  <label>
                    Agent name
                    <input
                      value={issueForm.agent_name}
                      onChange={(event) =>
                        setIssueForm((current) => ({ ...current, agent_name: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Creator
                    <input
                      value={issueForm.creator}
                      onChange={(event) =>
                        setIssueForm((current) => ({ ...current, creator: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Jurisdiction
                    <input
                      value={issueForm.jurisdiction}
                      onChange={(event) =>
                        setIssueForm((current) => ({ ...current, jurisdiction: event.target.value }))
                      }
                    />
                  </label>
                  <label>
                    Intended use
                    <textarea
                      value={issueForm.genome.intended_use}
                      disabled={!session}
                      onChange={(event) =>
                        setIssueForm((current) => ({
                          ...current,
                          genome: { ...current.genome, intended_use: event.target.value }
                        }))
                      }
                    />
                  </label>
                </div>

                <div className="certificate-preview">
                  <div className="certificate-sheet">
                    <div className="certificate-topline">
                      <ShieldCheck size={18} />
                      <span>Birth certificate ready</span>
                    </div>
                    <h3>{issueForm.agent_name}</h3>
                    <div className="token-grid">
                      {tokenRows(issueForm.genome).map((row) => (
                        <div key={row.label}>
                          <span>{row.label}</span>
                          <strong>{row.value}</strong>
                        </div>
                      ))}
                    </div>
                    <div className="hash-strip">
                      <Binary size={14} />
                      <code>
                        {btoa(
                          JSON.stringify(issueForm.genome)
                        ).slice(0, 40)}
                        ...
                      </code>
                    </div>
                    <div className="certificate-footer">
                      <span>{session ? issueForm.jurisdiction : "Replay artifact"}</span>
                      <span>{session ? issueForm.creator : "Investor scenario"}</span>
                    </div>
                  </div>
                </div>
              </div>
            )}
          </div>

          <div className="lineage-panel" id="lineage">
            <div className="panel-head">
              <span>Lineage explorer</span>
              <strong>Fork ancestry and identity continuity</strong>
            </div>
            {lineageRows.length > 0 ? (
              <div className="lineage-list">
                {lineageRows.map((node) => (
                  <div className="lineage-row" key={`${node.agent_id}-${node.depth}`} style={{ paddingLeft: `${node.depth * 28 + 18}px` }}>
                    <GitBranch size={14} />
                    <div>
                      <strong>{node.name}</strong>
                      <span>{node.agent_id}</span>
                    </div>
                    <em>{node.status}</em>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <Layers3 size={22} />
                <p>Issue the first agent to start a lineage tree.</p>
              </div>
            )}
          </div>
        </section>

        <section className="content-grid">
          <div className="registry-panel" id="registry">
            <div className="panel-head">
              <span>Agent registry</span>
              <strong>{agents.length} tracked identities</strong>
            </div>
            <div className="registry-table">
              <div className="table-row table-head">
                <span>Agent</span>
                <span>Status</span>
                <span>Purpose</span>
                <span>Ledger</span>
              </div>
              {agents.map((agent) => (
                <button
                  className={`table-row table-button ${selectedAgentId === agent.agent_id ? "selected" : ""}`}
                  key={agent.agent_id}
                  onClick={() => setSelectedAgentId(agent.agent_id)}
                >
                  <span>
                    <strong>{agent.name}</strong>
                    <em>{agent.agent_id}</em>
                  </span>
                  <span>{agent.status}</span>
                  <span>{agent.declared_purpose}</span>
                  <span className="hash-preview">{agent.latest_genome_hash.slice(0, 10)}...</span>
                </button>
              ))}
            </div>
          </div>

          <div className="ledger-panel" id="ledger">
            <div className="panel-head">
              <span>Life ledger</span>
              <strong>
                {chainStatus ? `${chainStatus.checked_events} events, ${chainStatus.status === "verified" ? "chain verified" : chainStatus.status === "blocked" ? "chain blocked" : "chain unmeasured"}` : "Awaiting agent"}
              </strong>
            </div>
            {ledgerEvents.length > 0 ? (
              <div className="timeline">
                {ledgerEvents.map((event) => (
                  <div className="timeline-row" key={event.event_id}>
                    <div className="timeline-marker" />
                    <div className="timeline-body">
                      <div className="timeline-top">
                        <strong>{event.summary}</strong>
                        <span>{new Date(event.created_at).toLocaleString()}</span>
                      </div>
                      <p>{event.event_type.replace(/_/g, " ")}</p>
                      <code>{event.event_hash.slice(0, 26)}...</code>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="empty-state">
                <ReceiptText size={22} />
                <p>The selected agent has no rendered event history yet.</p>
              </div>
            )}
          </div>

          <div className="rail-panel" id="billing">
            <div className="panel-head">
              <span>Billing and controls</span>
              <strong>Quota, integrity, export</strong>
            </div>
            <div className="usage-stack">
              <div className="usage-meter">
                <div className="usage-labels">
                  <span>Certificate issuance</span>
                  <strong>
                    {usageLimit ? `${usageLimit.used} / ${usageLimit.limit}` : "No limit loaded"}
                  </strong>
                </div>
                <div className="meter-track">
                  <div
                    className="meter-fill"
                    style={{
                      width: usageLimit ? `${Math.min(100, (usageLimit.used / usageLimit.limit) * 100)}%` : "0%"
                    }}
                  />
                </div>
              </div>

              <div className="stat-cluster">
                <div>
                  <span>Rendered lineage</span>
                  <strong>{usageByMetric.lineage_render ?? 0}</strong>
                </div>
                <div>
                  <span>Ledger usage</span>
                  <strong>{usageByMetric.ledger_write ?? 0}</strong>
                </div>
              </div>

              {selectedAgent ? (
                <div className="detail-card" id="investor">
                  <p>Selected certificate</p>
                  <strong>{selectedAgent.certificate_id}</strong>
                  <span>{selectedAgent.certificate_uri ?? "Artifact persisted in configured storage"}</span>
                </div>
              ) : null}

              <div className="action-list">
                <button className="rail-action" onClick={handleExportCompliancePacket}>
                  <ShieldCheck size={15} />
                  <span>Export compliance packet</span>
                  <ChevronRight size={15} />
                </button>
                <button className="rail-action" onClick={handleGenerateInvestorReplay}>
                  <BookLock size={15} />
                  <span>Generate investor replay</span>
                  <ChevronRight size={15} />
                </button>
              </div>
            </div>
          </div>
        </section>
      </main>
    </div>
  );
}
