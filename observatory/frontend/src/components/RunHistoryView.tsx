import React, { useEffect, useState } from "react";
import { History, CheckCircle2, XCircle, ShieldAlert, Clock, RefreshCw } from "lucide-react";
import { RunSummary } from "../types";

interface RunHistoryViewProps {
  onSelectRun: (runId: string) => void;
}

export const RunHistoryView: React.FC<RunHistoryViewProps> = ({ onSelectRun }) => {
  const [runs, setRuns] = useState<RunSummary[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchRuns = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/runs?limit=50");
      if (res.ok) {
        const data = await res.json();
        setRuns(data);
      }
    } catch (err) {
      console.error("Failed to load runs:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchRuns();
  }, []);

  return (
    <div className="obs-card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <History className="w-5 h-5 text-cyan-400" />
          <h2 className="text-sm font-bold uppercase tracking-wider font-mono text-slate-200">
            Historical Executions ({runs.length})
          </h2>
        </div>
        <button onClick={fetchRuns} className="btn-action flex items-center gap-1 text-xs">
          <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
          Refresh
        </button>
      </div>

      {loading && runs.length === 0 ? (
        <div className="text-center py-12 text-slate-400 font-mono text-xs">
          Loading historical runs from SQLite database...
        </div>
      ) : runs.length === 0 ? (
        <div className="text-center py-12 text-slate-500 font-mono text-xs italic">
          No previous runs found in database.
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-xs font-mono border-collapse">
            <thead>
              <tr className="border-b border-white/10 text-slate-400 text-[11px]">
                <th className="py-2.5 px-3 font-semibold">STATUS</th>
                <th className="py-2.5 px-3 font-semibold">RUN ID</th>
                <th className="py-2.5 px-3 font-semibold">TASK PROMPT</th>
                <th className="py-2.5 px-3 font-semibold">PLANNER</th>
                <th className="py-2.5 px-3 font-semibold">VISION</th>
                <th className="py-2.5 px-3 font-semibold">START TIME</th>
                <th className="py-2.5 px-3 font-semibold">ACTIONS</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-white/5">
              {runs.map((r) => {
                const isCompleted = r.status === "completed";
                const isBlocked = r.status === "blocked";
                const isFailed = r.status === "failed";

                return (
                  <tr key={r.run_id} className="hover:bg-white/[0.02] transition-colors">
                    <td className="py-3 px-3">
                      <span
                        className={`badge text-[10px] flex items-center gap-1 w-fit ${
                          isCompleted
                            ? "badge-emerald"
                            : isBlocked
                            ? "badge-rose"
                            : isFailed
                            ? "badge-rose"
                            : "badge-cyan"
                        }`}
                      >
                        {isCompleted && <CheckCircle2 className="w-3 h-3" />}
                        {isBlocked && <ShieldAlert className="w-3 h-3" />}
                        {isFailed && <XCircle className="w-3 h-3" />}
                        {r.status.toUpperCase()}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-cyan-300 font-bold max-w-[120px] truncate" title={r.run_id}>
                      {r.run_id.slice(0, 8)}...
                    </td>
                    <td className="py-3 px-3 text-slate-200 font-sans max-w-[320px] truncate" title={r.input_text}>
                      {r.input_text}
                    </td>
                    <td className="py-3 px-3 text-slate-300">{r.model}</td>
                    <td className="py-3 px-3">
                      <span
                        className={`badge text-[9px] ${
                          r.vision_status === "Active"
                            ? "badge-purple"
                            : r.vision_status === "Unavailable"
                            ? "badge-rose"
                            : "badge-slate"
                        }`}
                      >
                        {r.vision_status}
                      </span>
                    </td>
                    <td className="py-3 px-3 text-slate-400 text-[11px] whitespace-nowrap">
                      {r.created_at}
                    </td>
                    <td className="py-3 px-3">
                      <button
                        onClick={() => onSelectRun(r.run_id)}
                        className="btn-action text-xs px-2 py-1"
                      >
                        Inspect Trace
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
};
