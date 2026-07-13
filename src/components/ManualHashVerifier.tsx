import { useState, useEffect } from "react";
import {
  ShieldCheck,
  ShieldAlert,
  Database,
  Copy,
  Check,
  AlertTriangle,
  Activity,
  ArrowRight,
  Fingerprint,
  Binary,
  Lock,
  History,
  Code,
  Clock,
  Trash2
} from "lucide-react";
import type { LedgerEvent, AgentDetail } from "../types";

/** Deterministic hash matching the pgl-studioai computeEventHash implementation.
 *  Uses djb2-style Int32 arithmetic over the canonical pipe-delimited payload string.
 */
function computeEventHash(payload: {
  event_id: string;
  agent_id: string;
  created_at: string;
  event_type: string;
  summary: string;
  details_json: string;
  actor: string;
  prev_event_hash: string | null;
}): string {
  const raw = [
    payload.event_id,
    payload.agent_id,
    payload.created_at,
    payload.event_type,
    payload.summary,
    payload.details_json,
    payload.actor,
    payload.prev_event_hash ?? "00000000000000000000000000000000",
  ].join("|");

  let h = 0;
  for (let i = 0; i < raw.length; i++) {
    h = (Math.imul(31, h) + raw.charCodeAt(i)) | 0;
  }
  const hex = (h >>> 0).toString(16).padStart(8, "0");
  return `hash_${hex}x${raw.length.toString(36)}v2`;
}

interface VerificationAttempt {
  id: string;
  timestamp: string;
  blockId: string;
  passed: boolean;
  computedHash: string;
  expectedHash: string;
}

interface ManualHashVerifierProps {
  ledgerEvents: LedgerEvent[];
  agents: AgentDetail[];
}

export default function ManualHashVerifier({ ledgerEvents, agents }: ManualHashVerifierProps) {
  const [selectedEventId, setSelectedEventId] = useState("");
  const [eventId, setEventId] = useState("");
  const [agentId, setAgentId] = useState("");
  const [createdAt, setCreatedAt] = useState("");
  const [eventType, setEventType] = useState("custom");
  const [summary, setSummary] = useState("");
  const [detailsJson, setDetailsJson] = useState("{}");
  const [actor, setActor] = useState("");
  const [prevEventHash, setPrevEventHash] = useState("");
  const [expectedHash, setExpectedHash] = useState("");
  const [jsonText, setJsonText] = useState("");
  const [jsonError, setJsonError] = useState<string | null>(null);
  const [copiedField, setCopiedField] = useState<string | null>(null);
  const [attempts, setAttempts] = useState<VerificationAttempt[]>([]);

  const triggerCopy = (text: string, label: string) => {
    navigator.clipboard.writeText(text);
    setCopiedField(label);
    setTimeout(() => setCopiedField(null), 2000);
  };

  const handleLogAttempt = (passed: boolean, computed: string, expected: string) => {
    const attempt: VerificationAttempt = {
      id: "attempt-" + Date.now().toString(36),
      timestamp: new Date().toLocaleString(),
      blockId: eventId || "independent-snap",
      passed,
      computedHash: computed,
      expectedHash: expected || "No expected signature entered",
    };
    setAttempts(prev => [attempt, ...prev].slice(0, 5));
  };

  const buildPayload = () => ({
    event_id: eventId,
    agent_id: agentId,
    created_at: createdAt,
    event_type: eventType,
    summary,
    details_json: detailsJson,
    actor,
    prev_event_hash: prevEventHash || null,
  });

  const computedHash = computeEventHash(buildPayload());
  const formattedDataString = [eventId, agentId, createdAt, eventType, summary, detailsJson, actor, prevEventHash || "00000000000000000000000000000000"].join("|");
  const hasExpectedHash = expectedHash.trim().length > 0;
  const isHashMatching = hasExpectedHash && computedHash.toLowerCase() === expectedHash.toLowerCase().trim();

  const matchedChainBlock = ledgerEvents.find(e => e.event_id === eventId);
  const isIdRegisteredInChain = !!matchedChainBlock;
  const doesComputedHashMatchChainRecord = isIdRegisteredInChain && computedHash === matchedChainBlock?.event_hash;
  const precedingBlock = prevEventHash ? ledgerEvents.find(e => e.event_hash === prevEventHash) : null;

  const handleSelectTimelineEvent = (id: string) => {
    setSelectedEventId(id);
    const evt = ledgerEvents.find(e => e.event_id === id);
    if (evt) {
      setEventId(evt.event_id);
      setAgentId(String(evt.details["agent_id"] ?? ""));
      setCreatedAt(evt.created_at);
      setEventType(evt.event_type);
      setSummary(evt.summary);
      setDetailsJson(JSON.stringify(evt.details, null, 2));
      setActor(evt.actor);
      setPrevEventHash(evt.prev_event_hash ?? "");
      setExpectedHash(evt.event_hash);
      syncJson(evt.event_id, String(evt.details["agent_id"] ?? ""), evt.created_at, evt.event_type, evt.summary, JSON.stringify(evt.details, null, 2), evt.actor, evt.prev_event_hash ?? "");
    }
  };

  const syncJson = (eid: string, aid: string, ts: string, et: string, s: string, dj: string, act: string, peh: string) => {
    setJsonText(JSON.stringify({ event_id: eid, agent_id: aid, created_at: ts, event_type: et, summary: s, details_json: dj, actor: act, prev_event_hash: peh }, null, 2));
    setJsonError(null);
  };

  const handleJsonChange = (val: string) => {
    setJsonText(val);
    if (!val.trim()) { setJsonError(null); return; }
    try {
      const p = JSON.parse(val);
      setJsonError(null);
      if (p.event_id !== undefined) setEventId(String(p.event_id));
      if (p.agent_id !== undefined) setAgentId(String(p.agent_id));
      if (p.created_at !== undefined) setCreatedAt(String(p.created_at));
      if (p.event_type !== undefined) setEventType(String(p.event_type));
      if (p.summary !== undefined) setSummary(String(p.summary));
      if (p.details_json !== undefined) setDetailsJson(String(p.details_json));
      if (p.actor !== undefined) setActor(String(p.actor));
      if (p.prev_event_hash !== undefined) setPrevEventHash(String(p.prev_event_hash));
      if (p.event_hash) setExpectedHash(p.event_hash);
    } catch (err: unknown) {
      setJsonError(`JSON Syntax Error: ${(err as Error).message}`);
    }
  };

  useEffect(() => {
    if (ledgerEvents.length > 0 && !eventId) {
      handleSelectTimelineEvent(ledgerEvents[0].event_id);
    } else if (!eventId) {
      const now = new Date().toISOString();
      setEventId("evt-manual-101"); setAgentId("agent-alpha-001"); setCreatedAt(now);
      setEventType("custom"); setSummary("Manual Diagnostic Ledger Frame");
      setDetailsJson("{}"); setActor("operator@veklom.com"); setPrevEventHash("00000000000000000000000000000000");
      syncJson("evt-manual-101", "agent-alpha-001", now, "custom", "Manual Diagnostic Ledger Frame", "{}", "operator@veklom.com", "00000000000000000000000000000000");
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [ledgerEvents]);

  return (
    <div className="bg-[#0A0A0A] border border-white/10 rounded-xl p-6 shadow-xl flex flex-col gap-6">
      <div className="border-b border-white/10 pb-4 flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-base font-semibold text-white flex items-center gap-2">
            <Fingerprint className="text-teal-400 size-5" />
            Decentralized Hash Integrity Verifier
          </h2>
          <p className="text-xs text-slate-400 mt-1">Verify serialized ledger blocks without requiring active agent selection.</p>
        </div>
        <div className="flex items-center gap-2">
          <label className="text-[10px] uppercase font-mono tracking-wider text-white/40">Load From Chain:</label>
          <select
            value={selectedEventId}
            onChange={e => handleSelectTimelineEvent(e.target.value)}
            className="bg-[#050505] border border-white/15 rounded px-2.5 py-1 text-xs font-mono text-white/90 outline-none cursor-pointer max-w-[260px]"
          >
            <option value="">-- Manual Sandbox Template --</option>
            {ledgerEvents.map(e => (
              <option key={e.event_id} value={e.event_id}>
                [{e.event_id.slice(0, 10)}] {e.summary.slice(0, 30)}...
              </option>
            ))}
          </select>
        </div>
      </div>

      <div className="grid grid-cols-1 xl:grid-cols-12 gap-6">
        {/* Left: payload editor */}
        <div className="xl:col-span-7 flex flex-col gap-5">
          <div className="bg-white/5 border border-white/5 rounded-xl p-4 flex flex-col gap-3">
            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <span className="text-[11px] font-mono text-white/40 uppercase tracking-widest flex items-center gap-1.5">
                <Code className="size-3.5 text-teal-400" /> Raw JSON Input
              </span>
            </div>
            <textarea
              value={jsonText}
              onChange={e => handleJsonChange(e.target.value)}
              placeholder="Paste serialized block JSON..."
              className="w-full h-44 bg-[#050505] border border-white/10 rounded-lg p-3 font-mono text-xs text-teal-400 outline-none focus:border-teal-500/40 resize-none"
            />
            {jsonError && <p className="text-[10.5px] font-mono text-rose-500">{jsonError}</p>}
          </div>

          <div className="bg-white/5 border border-white/5 rounded-xl p-5 flex flex-col gap-4">
            <h3 className="text-xs font-mono font-bold text-white/80 uppercase tracking-wider border-b border-white/5 pb-2 flex items-center gap-2">
              <Database className="size-3.5 text-teal-400" /> Block Parameters
            </h3>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {([
                ["EVENT ID", eventId, (v: string) => setEventId(v)],
                ["AGENT ID", agentId, (v: string) => setAgentId(v)],
                ["CREATED AT (ISO)", createdAt, (v: string) => setCreatedAt(v)],
                ["EVENT TYPE", eventType, (v: string) => setEventType(v)],
                ["ACTOR", actor, (v: string) => setActor(v)],
                ["PREV EVENT HASH", prevEventHash, (v: string) => setPrevEventHash(v)],
              ] as [string, string, (v: string) => void][]).map(([label, val, setter]) => (
                <div key={label}>
                  <label className="block text-[10.5px] font-mono text-white/50 mb-1">{label}:</label>
                  <input
                    type="text"
                    value={val}
                    onChange={e => setter(e.target.value)}
                    className="w-full bg-[#050505] border border-white/10 rounded px-3 py-1.5 text-xs font-mono text-white outline-none focus:border-teal-500"
                  />
                </div>
              ))}
              <div className="md:col-span-2">
                <label className="block text-[10.5px] font-mono text-white/50 mb-1">SUMMARY:</label>
                <input type="text" value={summary} onChange={e => setSummary(e.target.value)}
                  className="w-full bg-[#050505] border border-white/10 rounded px-3 py-1.5 text-xs font-sans text-white outline-none focus:border-teal-500" />
              </div>
              <div className="md:col-span-2">
                <label className="block text-[10.5px] font-mono text-white/50 mb-1">DETAILS JSON (stringified):</label>
                <textarea value={detailsJson} onChange={e => setDetailsJson(e.target.value)}
                  className="w-full h-16 bg-[#050505] border border-white/10 rounded px-3 py-1.5 text-xs font-mono text-white outline-none focus:border-teal-500 resize-none" />
              </div>
            </div>
          </div>
        </div>

        {/* Right: digest + audit */}
        <div className="xl:col-span-5 flex flex-col gap-6">
          <div className="bg-white/5 border border-white/5 rounded-xl p-5 flex flex-col gap-3">
            <h3 className="text-xs font-mono font-bold text-white/80 uppercase tracking-wider flex items-center gap-1.5">
              <Lock className="text-teal-400 size-3.5" /> Expected Signature
            </h3>
            <div className="flex gap-2">
              <input type="text" placeholder="Paste signature hash..." value={expectedHash}
                onChange={e => setExpectedHash(e.target.value)}
                className="flex-1 bg-[#050505] border border-white/10 rounded px-3 py-1.5 text-xs font-mono text-teal-400 outline-none focus:border-teal-500" />
              {expectedHash && (
                <button onClick={() => setExpectedHash("")}
                  className="bg-white/5 hover:bg-white/10 border border-white/15 px-2.5 rounded text-[10px] text-white/60 font-mono transition">Clear</button>
              )}
            </div>
          </div>

          <div className="bg-[#050505] border border-white/10 rounded-xl p-5 flex flex-col gap-4 relative overflow-hidden">
            <div className="absolute top-0 right-0 p-2 opacity-5"><Binary className="size-20" /></div>
            <h3 className="text-xs font-mono font-bold text-white flex items-center gap-2">
              <Activity className="text-teal-400 size-4" /> Live Digest Console
            </h3>
            <div className="space-y-1.5">
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest block">Payload Buffer:</span>
              <div className="bg-[#0A0A0A] border border-white/5 rounded p-3 font-mono text-[10.5px] text-zinc-400 select-all overflow-x-auto whitespace-pre">{formattedDataString}</div>
            </div>
            <div className="bg-[#0A0A0A] border border-white/5 rounded-lg p-4 flex flex-col gap-2.5">
              <div className="flex justify-between items-center text-[10px] font-mono text-white/50">
                <span>DIGEST: ACTIVE (Int32 Math)</span>
                <button onClick={() => triggerCopy(computedHash, "computed_hash")}
                  className="text-teal-400 hover:underline flex items-center gap-1 cursor-pointer">
                  {copiedField === "computed_hash" ? <Check className="size-3 text-emerald-400" /> : <Copy className="size-3" />}
                  <span>{copiedField === "computed_hash" ? "Copied!" : "Copy"}</span>
                </button>
              </div>
              <span className="text-[10px] font-mono text-white/40">Computed Hash:</span>
              <span className="text-lg font-mono font-bold text-emerald-400 tracking-tight select-all">{computedHash}</span>
            </div>
            <div className="flex flex-col gap-2.5">
              {!hasExpectedHash ? (
                <div className="bg-amber-950/10 border border-amber-500/20 text-amber-500 p-3 rounded-lg flex items-start gap-2.5">
                  <AlertTriangle className="size-4.5 shrink-0 mt-0.5" />
                  <div className="text-[11px]"><p className="font-semibold">Awaiting Benchmark Hash</p></div>
                </div>
              ) : isHashMatching ? (
                <div className="bg-emerald-950/20 border border-emerald-500/30 text-emerald-400 p-3 rounded-lg flex items-start gap-2.5">
                  <ShieldCheck className="size-4.5 shrink-0 mt-0.5" />
                  <div className="text-[11px]"><p className="font-semibold">Parity Validation Succeeded</p></div>
                </div>
              ) : (
                <div className="bg-rose-950/20 border border-rose-500/30 text-rose-400 p-3 rounded-lg flex items-start gap-2.5">
                  <ShieldAlert className="size-4.5 shrink-0 mt-0.5" />
                  <div className="text-[11px]"><p className="font-semibold">Hash Mismatch — Tamper Detected</p></div>
                </div>
              )}
              <button onClick={() => handleLogAttempt(isHashMatching, computedHash, expectedHash)}
                className="w-full bg-teal-600 hover:bg-teal-500 text-white py-1.5 rounded text-[11px] font-mono font-bold tracking-tight transition cursor-pointer flex items-center justify-center gap-1.5">
                <ShieldCheck className="size-3.5" /> Log Audit Check
              </button>
            </div>
          </div>

          {/* Chain traversal */}
          <div className="bg-[#050505] border border-white/10 rounded-xl p-5 flex flex-col gap-4">
            <h3 className="text-xs font-mono font-bold text-white flex items-center gap-2">
              <History className="text-teal-400 size-4" /> Chain Traversal Trace
            </h3>
            <div className="space-y-4">
              <div className="flex items-start gap-3 border-b border-white/5 pb-3">
                <div className={`p-1.5 rounded-full ${isIdRegisteredInChain ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-white/40"}`}>
                  <Database className="size-3.5" />
                </div>
                <div>
                  <div className="text-[11px] font-mono font-semibold text-white">
                    {isIdRegisteredInChain ? "Block found in chain" : "Off-chain snapshot"}
                  </div>
                  <div className="text-[10.5px] text-white/50 mt-0.5">
                    {isIdRegisteredInChain
                      ? `Matches ledger record for agent ${agents.find(a => a.agent_id)?.name ?? matchedChainBlock?.actor}.`
                      : "Block ID not in live ledger state."}
                  </div>
                </div>
              </div>
              {isIdRegisteredInChain && (
                <div className="flex items-start gap-3 border-b border-white/5 pb-3">
                  <div className={`p-1.5 rounded-full ${doesComputedHashMatchChainRecord ? "bg-emerald-500/10 text-emerald-400" : "bg-rose-500/10 text-rose-400"}`}>
                    <ShieldCheck className="size-3.5" />
                  </div>
                  <div>
                    <div className="text-[11px] font-mono font-semibold text-white">
                      {doesComputedHashMatchChainRecord ? "Matches canonical ledger hash" : "Tamper mismatch warning"}
                    </div>
                  </div>
                </div>
              )}
              <div className="flex items-start gap-3">
                <div className={`p-1.5 rounded-full ${precedingBlock ? "bg-emerald-500/10 text-emerald-400" : "bg-white/5 text-white/40"}`}>
                  <ArrowRight className="size-3.5" />
                </div>
                <div>
                  <div className="text-[11px] font-mono font-semibold text-white">
                    {precedingBlock ? "Lineage traced" : prevEventHash === "00000000000000000000000000000000" ? "Root block" : "Predecessor unresolved"}
                  </div>
                </div>
              </div>
            </div>
          </div>

          {/* Attempt history */}
          <div className="bg-[#050505] border border-white/10 rounded-xl p-5 flex flex-col gap-4">
            <div className="flex items-center justify-between border-b border-white/5 pb-2">
              <h3 className="text-xs font-mono font-bold text-white flex items-center gap-2">
                <Clock className="text-teal-400 size-4" /> Recent Verification Runs
              </h3>
              {attempts.length > 0 && (
                <button onClick={() => setAttempts([])}
                  className="text-[10px] font-mono text-rose-500 hover:underline flex items-center gap-1 cursor-pointer">
                  <Trash2 className="size-3" /> Clear
                </button>
              )}
            </div>
            {attempts.length === 0 ? (
              <div className="text-center py-6 text-white/30 text-xs">No audit runs logged this session.</div>
            ) : (
              <div className="flex flex-col gap-2.5">
                {attempts.map(att => (
                  <div key={att.id} className="bg-[#0A0A0A] border border-white/5 rounded p-3 text-xs font-mono flex flex-col gap-1.5">
                    <div className="flex items-center justify-between">
                      <span className="text-[10px] text-white/40">{att.timestamp}</span>
                      <span className={`text-[9px] font-bold px-1.5 py-0.5 rounded border flex items-center gap-1 ${
                        att.passed ? "text-emerald-400 bg-emerald-950/30 border-emerald-500/20" : "text-rose-400 bg-rose-950/30 border-rose-500/20"
                      }`}>{att.passed ? "PASS" : "FAIL"}</span>
                    </div>
                    <div className="text-[10px] text-white/60 truncate">Block: {att.blockId}</div>
                    <div className="text-[9.5px] text-white/40 border-t border-white/5 pt-1 truncate">
                      <span className="text-white/50">Expected:</span> {att.expectedHash}
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}
