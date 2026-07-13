import { useState } from "react";
import { Table2, RefreshCw, ExternalLink, CheckCircle2, AlertCircle } from "lucide-react";
import type { AgentDetail, GoogleSheetsSyncConfig, GoogleSheetsSyncResult, SessionState } from "../types";
import { googleSheetsSync } from "../api";

interface GoogleSheetsSyncProps {
  agents: AgentDetail[];
  session: SessionState;
}

export default function GoogleSheetsSync({ agents, session }: GoogleSheetsSyncProps) {
  const [spreadsheetId, setSpreadsheetId] = useState("");
  const [sheetName, setSheetName] = useState("Genome Ledger Export");
  const [selectedAgentId, setSelectedAgentId] = useState("");
  const [includeLedger, setIncludeLedger] = useState(true);
  const [includeIncidents, setIncludeIncidents] = useState(false);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState<GoogleSheetsSyncResult | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleSync = async () => {
    if (!spreadsheetId.trim()) { setError("Spreadsheet ID is required."); return; }
    setLoading(true); setError(null); setResult(null);
    try {
      const config: GoogleSheetsSyncConfig = {
        spreadsheet_id: spreadsheetId.trim(),
        sheet_name: sheetName.trim() || "Genome Ledger Export",
        agent_id: selectedAgentId || undefined,
        include_ledger: includeLedger,
        include_incidents: includeIncidents,
      };
      const res = await googleSheetsSync(session, config);
      setResult(res);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="bg-[#0A0A0A] border border-white/10 rounded-xl p-6 shadow-xl flex flex-col gap-6">
      <div className="border-b border-white/10 pb-4">
        <h2 className="text-base font-semibold text-white flex items-center gap-2">
          <Table2 className="text-teal-400 size-5" />
          Google Sheets Sync
        </h2>
        <p className="text-xs text-slate-400 mt-1">
          Export ledger events and incidents to a Google Sheet. Requires the sheet to be shared with the gnomledger service account.
        </p>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="md:col-span-2">
          <label className="block text-[11px] font-mono text-white/50 mb-1">SPREADSHEET ID:</label>
          <input
            type="text"
            value={spreadsheetId}
            onChange={e => setSpreadsheetId(e.target.value)}
            placeholder="1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgVE2upms"
            className="w-full bg-[#050505] border border-white/10 rounded px-3 py-2 text-sm font-mono text-white outline-none focus:border-teal-500"
          />
        </div>
        <div>
          <label className="block text-[11px] font-mono text-white/50 mb-1">SHEET / TAB NAME:</label>
          <input
            type="text"
            value={sheetName}
            onChange={e => setSheetName(e.target.value)}
            className="w-full bg-[#050505] border border-white/10 rounded px-3 py-2 text-sm font-mono text-white outline-none focus:border-teal-500"
          />
        </div>
        <div>
          <label className="block text-[11px] font-mono text-white/50 mb-1">FILTER BY AGENT (optional):</label>
          <select
            value={selectedAgentId}
            onChange={e => setSelectedAgentId(e.target.value)}
            className="w-full bg-[#050505] border border-white/10 rounded px-3 py-2 text-sm font-mono text-white outline-none cursor-pointer"
          >
            <option value="">All agents</option>
            {agents.map(a => (
              <option key={a.agent_id} value={a.agent_id}>{a.name}</option>
            ))}
          </select>
        </div>
        <div className="flex items-center gap-6">
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={includeLedger} onChange={e => setIncludeLedger(e.target.checked)}
              className="accent-teal-500" />
            <span className="text-[12px] text-white/70">Include ledger events</span>
          </label>
          <label className="flex items-center gap-2 cursor-pointer">
            <input type="checkbox" checked={includeIncidents} onChange={e => setIncludeIncidents(e.target.checked)}
              className="accent-teal-500" />
            <span className="text-[12px] text-white/70">Include incidents</span>
          </label>
        </div>
      </div>

      <button
        onClick={() => void handleSync()}
        disabled={loading || !spreadsheetId.trim()}
        className="flex items-center justify-center gap-2 bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white py-2.5 rounded-lg text-sm font-semibold transition cursor-pointer"
      >
        <RefreshCw className={`size-4 ${loading ? "animate-spin" : ""}`} />
        {loading ? "Syncing..." : "Sync to Google Sheets"}
      </button>

      {error && (
        <div className="bg-rose-950/20 border border-rose-500/30 text-rose-400 px-4 py-3 rounded-lg flex items-center gap-2 text-sm">
          <AlertCircle className="size-4 shrink-0" /> {error}
        </div>
      )}

      {result && (
        <div className="bg-emerald-950/20 border border-emerald-500/30 text-emerald-400 px-4 py-3 rounded-lg flex flex-col gap-1">
          <div className="flex items-center gap-2 text-sm font-semibold">
            <CheckCircle2 className="size-4" /> Sync complete — {result.rows_written} rows written
          </div>
          <a href={result.sheet_url} target="_blank" rel="noopener noreferrer"
            className="text-xs text-teal-400 hover:underline flex items-center gap-1 mt-1">
            <ExternalLink className="size-3" /> Open in Google Sheets
          </a>
          <span className="text-[11px] text-white/40">Synced at {new Date(result.synced_at).toLocaleString()}</span>
        </div>
      )}
    </div>
  );
}
