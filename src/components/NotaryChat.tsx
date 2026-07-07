import React, { useState, useRef, useEffect } from "react";
import { ShieldAlert, Send, Sparkles, User, Terminal } from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { ChatMessage, AgentDetail, NotaryChatRequest } from "../types";
import { notaryChat } from "../api";
import type { SessionState } from "../types";

interface NotaryChatProps {
  agents: AgentDetail[];
  selectedAgent: AgentDetail | null;
  session: SessionState;
}

export default function NotaryChat({ agents, selectedAgent, session }: NotaryChatProps) {
  const [messages, setMessages] = useState<ChatMessage[]>([
    {
      id: "init-msg",
      role: "assistant",
      content:
        "Greetings. I am the **Notary Custodian AI** of Project Genome Ledger.\n\n" +
        "I monitor and audit all active agent genome births, lifecycle events, and compliance signatures on this platform.\n\n" +
        "Ask me about regulatory guidelines (EU AI Act, NIST AI RMF), audit specific agent parameters, or generate a security assessment instantly.",
      timestamp: new Date().toISOString(),
    },
  ]);
  const [input, setInput] = useState("");
  const [loading, setLoading] = useState(false);
  const [selectedModel, setSelectedModel] = useState("gemini-2.5-flash");
  const [error, setError] = useState<string | null>(null);
  const threadEndRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    threadEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const handleSend = async () => {
    const trimmed = input.trim();
    if (!trimmed || loading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: "user",
      content: trimmed,
      timestamp: new Date().toISOString(),
    };
    setMessages(prev => [...prev, userMsg]);
    setInput("");
    setLoading(true);
    setError(null);

    try {
      const payload: NotaryChatRequest = {
        message: trimmed,
        agent_id: selectedAgent?.agent_id,
        model: selectedModel,
      };
      const result = await notaryChat(session, payload);
      const assistantMsg: ChatMessage = {
        id: `assistant-${Date.now()}`,
        role: "assistant",
        content: result.reply,
        timestamp: new Date().toISOString(),
      };
      setMessages(prev => [...prev, assistantMsg]);
    } catch (err: unknown) {
      setError((err as Error).message);
    } finally {
      setLoading(false);
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      void handleSend();
    }
  };

  const agentContext = selectedAgent
    ? `Context: ${selectedAgent.name} (${selectedAgent.agent_id})`
    : `${agents.length} agent${agents.length !== 1 ? "s" : ""} loaded`;

  return (
    <div className="bg-[#0A0A0A] border border-white/10 rounded-xl flex flex-col h-[700px] shadow-xl">
      {/* Header */}
      <div className="flex items-center justify-between px-5 py-3 border-b border-white/10">
        <div className="flex items-center gap-2">
          <ShieldAlert className="text-teal-400 size-5" />
          <span className="text-sm font-semibold text-white">Notary Custodian AI</span>
          <span className="text-[10px] font-mono text-white/40 ml-2">{agentContext}</span>
        </div>
        <div className="flex items-center gap-2">
          <Terminal className="size-3.5 text-white/40" />
          <select
            value={selectedModel}
            onChange={e => setSelectedModel(e.target.value)}
            className="bg-[#050505] border border-white/10 rounded px-2 py-1 text-[11px] font-mono text-white/70 outline-none cursor-pointer"
          >
            <option value="gemini-2.5-flash">gemini-2.5-flash</option>
            <option value="gemini-2.5-pro">gemini-2.5-pro</option>
          </select>
        </div>
      </div>

      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-5 py-4 flex flex-col gap-4">
        {messages.map(msg => (
          <div key={msg.id} className={`flex gap-3 ${msg.role === "user" ? "flex-row-reverse" : ""}`}>
            <div className={`size-7 rounded-full flex items-center justify-center shrink-0 ${
              msg.role === "user" ? "bg-teal-500/20 text-teal-400" : "bg-white/5 text-white/60"
            }`}>
              {msg.role === "user" ? <User className="size-3.5" /> : <Sparkles className="size-3.5" />}
            </div>
            <div className={`max-w-[80%] rounded-xl px-4 py-3 text-sm leading-relaxed ${
              msg.role === "user"
                ? "bg-teal-500/10 border border-teal-500/20 text-white ml-auto"
                : "bg-white/5 border border-white/5 text-white/90"
            }`}>
              <ReactMarkdown>{msg.content}</ReactMarkdown>
              <span className="block text-[10px] text-white/30 mt-2">
                {new Date(msg.timestamp).toLocaleTimeString()}
              </span>
            </div>
          </div>
        ))}
        {loading && (
          <div className="flex gap-3">
            <div className="size-7 rounded-full flex items-center justify-center shrink-0 bg-white/5 text-white/60">
              <Sparkles className="size-3.5 animate-pulse" />
            </div>
            <div className="bg-white/5 border border-white/5 rounded-xl px-4 py-3">
              <span className="inline-flex gap-1">
                {[0, 1, 2].map(i => (
                  <span key={i} className="size-1.5 bg-white/40 rounded-full animate-bounce" style={{ animationDelay: `${i * 150}ms` }} />
                ))}
              </span>
            </div>
          </div>
        )}
        {error && (
          <div className="bg-rose-950/20 border border-rose-500/30 text-rose-400 px-4 py-3 rounded-xl text-sm">
            Error: {error}
          </div>
        )}
        <div ref={threadEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/10 px-4 py-3 flex gap-3 items-end">
        <textarea
          value={input}
          onChange={e => setInput(e.target.value)}
          onKeyDown={handleKeyDown}
          placeholder="Ask the Notary Custodian... (Enter to send, Shift+Enter for newline)"
          rows={2}
          className="flex-1 bg-[#050505] border border-white/10 rounded-lg px-3 py-2 text-sm text-white outline-none focus:border-teal-500/50 resize-none placeholder-white/20"
        />
        <button
          onClick={() => void handleSend()}
          disabled={!input.trim() || loading}
          className="bg-teal-600 hover:bg-teal-500 disabled:opacity-40 disabled:cursor-not-allowed text-white p-2.5 rounded-lg transition cursor-pointer"
        >
          <Send className="size-4" />
        </button>
      </div>
    </div>
  );
}
