import React, { useState } from "react";
import { Fingerprint, RefreshCw, Copy, Check, ShieldCheck, AlertCircle } from "lucide-react";
import type { AgentDetail, ExecutionIdentityV1, SessionState } from "../types";
import { getExecutionIdentity } from "../api";

interface ExecutionIdentityV1ControlProps {
  agents: AgentDetail[];
  session: SessionState;
}

export default function ExecutionIdentityV1Control({ agents, session }: ExecutionIdentityV1ControlProps) {
  const [selectedAgentId, setSelectedAgentId] = useState(agents[0]?.agent_id ?? "");
  const [identity, setIdentity] = useState<ExecutionIdentityV1 | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);

  const handleFetch = async () => {
    if (!selectedAgentId) return;
    setLoading(true); setError(null);
    try {
      const id = await getExecutionIdentity(session, selectedAgentId);
      setIdentity(id);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const copy = (val: string, key: string) => {
    navigator.clipboard.writeText(val);
    setCopied(key);
    setTimeout(() => setCopied(null), 2000);
  };

  const fields: [string, keyof ExecutionIdentityV1][] = [
    ["Identity Hash", "identity_hash"],
    ["Genome Hash", "genome_hash"],
    ["Certificate ID", "certificate_id"],
    ["Jurisdiction", "jurisdiction"],
    ["Risk Category", "risk_category"],
    ["Signature", "signature"],
  ];

  return (
    <div className="bg-[#0A0A0A] border border-white/10 rounded-xl p-6 shadow-xl flex flex-col gap-6">
      <div className="border-b border-white/10 pb-4">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Fingerprint className="text-teal-400 size-5" />
          Execution Identity V1
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Retrieve the cryptographic execution identity bundle for a registered agent. The identity hash is deterministically derived from genome hash + certificate ID + jurisdiction.
        </p>
      </div>

      <div className="flex gap-3 items-end">
        <div className="flex-1">
          <label className="block text-[11px] font-mono text-white/50 mb-1">SELECT AGENT:</label>
          <select
            value={selectedAgentId}
            onChange={e => setSelectedAgentId(e.target.value)}
            className="w-full bg-[#050505] border border-white/10 rounded px-3 py-2 text-sm font-mono text-white outline-none cursor-pointer"
          >
            {agents.map(a => (
              <option key={a.agent_id} value={a.agent_id}>{a.name} ({a.agent_id})</option>
            ))}
          </select>
        </div>
        <button
          onClick={() => void handleFetch()}
          disabled={loading || !selectedAgentId}
          className="flex items-center gap-2 bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white px-4 py-2 rounded-lg text-sm font-semibold transition cursor-pointer"
        >
          <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
          {loading ? "Fetching..." : "Fetch Identity"}
        </button>
      </div>

      {error && (
        <div className="bg-rose-950/20 border border-rose-500/30 text-rose-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="size-4 shrink-0" /> {error}
        </div>
      )}

      {identity && (
        <div className="bg-[#050505] border border-white/10 rounded-xl p-5 flex flex-col gap-4">
          <div className="flex items-center gap-2 text-emerald-400 text-sm font-semibold">
            <ShieldCheck className="size-4" />
            Identity bundle loaded for {identity.agent_id}
          </div>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest">Declared Purpose:</span>
              <span className="text-sm text-white/90">{identity.declared_purpose}</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest">Issued At:</span>
              <span className="text-sm text-white/90">{new Date(identity.issued_at).toLocaleString()}</span>
            </div>
            {fields.map(([label, key]) => (
              <div key={key} className="flex flex-col gap-1">
                <span className="text-[10px] font-mono text-white/40 uppercase tracking-widest">{label}:</span>
                <div className="flex items-center gap-2">
                  <code className="text-xs font-mono text-teal-400 bg-[#0A0A0A] border border-white/5 rounded px-2 py-1 flex-1 truncate select-all">
                    {String(identity[key])}
                  </code>
                  <button onClick={() => copy(String(identity[key]), key)}
                    className="text-white/40 hover:text-white/80 transition cursor-pointer">
                    {copied === key ? <Check className="size-3.5 text-emerald-400" /> : <Copy className="size-3.5" />}
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}
