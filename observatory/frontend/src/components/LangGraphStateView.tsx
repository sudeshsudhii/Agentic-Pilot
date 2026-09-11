import React, { useEffect, useState } from "react";
import { ShieldCheck, RefreshCw, Copy, Check, Code } from "lucide-react";

interface LangGraphStateViewProps {
  activeRunId: string | null;
}

export const LangGraphStateView: React.FC<LangGraphStateViewProps> = ({ activeRunId }) => {
  const [stateData, setStateData] = useState<any>(null);
  const [loading, setLoading] = useState(false);
  const [copied, setCopied] = useState(false);

  const fetchState = async () => {
    if (!activeRunId) return;
    setLoading(true);
    try {
      const res = await fetch(`/api/runs/${activeRunId}/state`);
      if (res.ok) {
        const data = await res.json();
        setStateData(data);
      } else {
        setStateData(null);
      }
    } catch (err) {
      console.error("Failed to load state:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchState();
  }, [activeRunId]);

  const copyJson = () => {
    if (!stateData) return;
    navigator.clipboard.writeText(JSON.stringify(stateData, null, 2));
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  return (
    <div className="obs-card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <ShieldCheck className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-bold uppercase tracking-wider font-mono text-slate-200">
            LangGraph State Machine Inspector
          </h2>
        </div>
        <div className="flex items-center gap-2">
          {stateData && (
            <button onClick={copyJson} className="btn-action flex items-center gap-1 text-xs">
              {copied ? <Check className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
              {copied ? "Copied" : "Copy State JSON"}
            </button>
          )}
          <button
            onClick={fetchState}
            disabled={!activeRunId}
            className="btn-action flex items-center gap-1 text-xs disabled:opacity-40"
          >
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="text-xs text-slate-400 font-mono flex items-center justify-between bg-slate-950/60 p-2.5 rounded border border-white/5">
        <div>
          <span>INSPECTING RUN: </span>
          <span className="text-cyan-300 font-bold">{activeRunId || "NONE SELECTED"}</span>
        </div>
        <span className="badge badge-cyan text-[10px]">Secrets Redacted</span>
      </div>

      {!activeRunId ? (
        <div className="text-center py-12 text-slate-500 font-mono text-xs italic">
          No run selected. Start or select a task to inspect its LangGraph state checkpoint.
        </div>
      ) : loading && !stateData ? (
        <div className="text-center py-12 text-slate-400 font-mono text-xs">
          Loading state checkpoint from disk...
        </div>
      ) : !stateData ? (
        <div className="text-center py-12 text-slate-500 font-mono text-xs italic">
          No checkpoint saved for run {activeRunId}.
        </div>
      ) : (
        <div className="flex flex-col gap-3">
          {/* Key Fields Summary */}
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
            <div className="bg-slate-900/80 p-2 rounded border border-white/5">
              <span className="text-slate-500 block text-[10px]">CURRENT NODE</span>
              <span className="text-cyan-300 font-bold">{stateData.current_node || "completed"}</span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-white/5">
              <span className="text-slate-500 block text-[10px]">TASK STATUS</span>
              <span className="text-emerald-400 font-bold">{stateData.status || "UNKNOWN"}</span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-white/5">
              <span className="text-slate-500 block text-[10px]">STEP INDEX</span>
              <span className="text-slate-200 font-bold">{stateData.current_step_index ?? 1}</span>
            </div>
            <div className="bg-slate-900/80 p-2 rounded border border-white/5">
              <span className="text-slate-500 block text-[10px]">RETRY COUNT</span>
              <span className="text-slate-200 font-bold">{stateData.retry_count ?? 0}</span>
            </div>
          </div>

          {/* Full State JSON */}
          <div className="flex flex-col gap-1">
            <span className="text-slate-400 text-xs font-mono">FULL STATE GRAPH:</span>
            <pre className="json-box max-h-[500px] text-xs whitespace-pre-wrap leading-relaxed">
              {JSON.stringify(stateData, null, 2)}
            </pre>
          </div>
        </div>
      )}
    </div>
  );
};
