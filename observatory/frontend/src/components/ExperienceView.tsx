import React, { useEffect, useState } from "react";
import { Database, ShieldCheck, RefreshCw, Layers } from "lucide-react";
import { ExperienceItem } from "../types";

export const ExperienceView: React.FC = () => {
  const [experiences, setExperiences] = useState<ExperienceItem[]>([]);
  const [loading, setLoading] = useState(true);

  const fetchExperiences = async () => {
    setLoading(true);
    try {
      const res = await fetch("/api/experiences?limit=50");
      if (res.ok) {
        const data = await res.json();
        setExperiences(data);
      }
    } catch (err) {
      console.error("Failed to load experiences:", err);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchExperiences();
  }, []);

  return (
    <div className="obs-card p-5 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-3">
        <div className="flex items-center gap-2">
          <Database className="w-5 h-5 text-indigo-400" />
          <h2 className="text-sm font-bold uppercase tracking-wider font-mono text-slate-200">
            Collected Experiences & Episodic Memory ({experiences.length})
          </h2>
        </div>
        <div className="flex items-center gap-3">
          <span className="badge badge-rose text-[10px]">Model Training: DISABLED</span>
          <button onClick={fetchExperiences} className="btn-action flex items-center gap-1 text-xs">
            <RefreshCw className={`w-3.5 h-3.5 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </button>
        </div>
      </div>

      <div className="bg-slate-950/60 p-3 rounded-lg border border-white/5 text-xs text-slate-300 font-mono">
        <span className="text-cyan-400 font-bold mr-1.5">[READ-ONLY OBSERVER]</span>
        Displaying episodic experiences, failure strategies, and execution summaries captured in Pilot SQLite memory. Qwen model weights and parameters remain strictly unmodified.
      </div>

      {loading && experiences.length === 0 ? (
        <div className="text-center py-12 text-slate-400 font-mono text-xs">
          Querying episodic experiences from memories store...
        </div>
      ) : experiences.length === 0 ? (
        <div className="text-center py-12 text-slate-500 font-mono text-xs italic">
          No experience records collected yet. Run Pilot tasks to build episodic memory.
        </div>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          {experiences.map((exp) => (
            <div
              key={exp.memory_id}
              className="bg-slate-900/80 p-3.5 rounded-lg border border-white/5 flex flex-col gap-2 font-mono text-xs"
            >
              <div className="flex items-center justify-between">
                <span className="badge badge-purple text-[10px]">{exp.type.toUpperCase()}</span>
                <span className="text-slate-400 text-[11px]">{exp.created_at}</span>
              </div>

              <div>
                <span className="text-slate-500 text-[10px] block">ASSOCIATED TASK ID:</span>
                <span className="text-cyan-300 truncate block">{exp.task_id || "global"}</span>
              </div>

              <div>
                <span className="text-slate-500 text-[10px] block">MEMORY CONTENT:</span>
                <pre className="json-box text-[11px] mt-1 max-h-[160px]">
                  {typeof exp.content === "object"
                    ? JSON.stringify(exp.content, null, 2)
                    : String(exp.content)}
                </pre>
              </div>

              <div className="flex items-center justify-between text-[11px] text-slate-400 pt-2 border-t border-white/5">
                <span>Access count: {exp.access_count}</span>
                <span className="badge badge-slate text-[9px]">Training Eligible: FALSE</span>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
};
