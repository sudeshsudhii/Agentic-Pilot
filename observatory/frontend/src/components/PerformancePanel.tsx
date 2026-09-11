import React from "react";
import { Gauge, Clock, Zap } from "lucide-react";
import { PerformanceMetrics } from "../types";

interface PerformancePanelProps {
  metrics: PerformanceMetrics;
}

export const PerformancePanel: React.FC<PerformancePanelProps> = ({ metrics }) => {
  const total = metrics.total_duration_sec || 0;
  const planner = metrics.planner_duration_sec || 0;
  const vision = metrics.vision_duration_sec || 0;
  const browser = metrics.browser_duration_sec || 0;
  const verif = metrics.verification_duration_sec || 0;
  const waiting = metrics.waiting_duration_sec || 0;
  const retry = metrics.retry_duration_sec || 0;

  // Percentage calculations for stacked progress bar
  const getPct = (val: number) => (total > 0 ? Math.min(100, Math.round((val / total) * 100)) : 0);

  return (
    <div className="obs-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <Gauge className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Execution Latency & Performance
          </h2>
        </div>
        <div className="flex items-center gap-1.5 text-xs font-mono">
          <span className="text-slate-400">TOTAL:</span>
          <span className="text-cyan-300 font-bold bg-cyan-950/40 border border-cyan-500/30 px-2 py-0.5 rounded">
            {total.toFixed(1)}s
          </span>
        </div>
      </div>

      {/* Stacked Breakdown Bar */}
      <div className="w-full h-3 bg-slate-950 rounded-full overflow-hidden flex border border-white/5">
        <div style={{ width: `${getPt(planner)}%` }} className="bg-cyan-500" title={`Planner: ${planner}s`} />
        <div style={{ width: `${getPt(vision)}%` }} className="bg-purple-500" title={`Vision: ${vision}s`} />
        <div style={{ width: `${getPt(browser)}%` }} className="bg-emerald-500" title={`Browser: ${browser}s`} />
        <div style={{ width: `${getPt(verif)}%` }} className="bg-blue-500" title={`Verification: ${verif}s`} />
        <div style={{ width: `${getPt(waiting)}%` }} className="bg-slate-600" title={`Waiting: ${waiting}s`} />
        <div style={{ width: `${getPt(retry)}%` }} className="bg-rose-500" title={`Retry: ${retry}s`} />
      </div>

      {/* Latency Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 text-xs font-mono">
        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-cyan-500 inline-block" /> Planner
          </span>
          <span className="text-cyan-300 font-bold">{planner.toFixed(1)}s</span>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-purple-500 inline-block" /> Vision
          </span>
          <span className="text-purple-300 font-bold">{vision.toFixed(1)}s</span>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-emerald-500 inline-block" /> Browser
          </span>
          <span className="text-emerald-300 font-bold">{browser.toFixed(1)}s</span>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-blue-500 inline-block" /> Verif.
          </span>
          <span className="text-blue-300 font-bold">{verif.toFixed(1)}s</span>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-slate-600 inline-block" /> Waiting
          </span>
          <span className="text-slate-300 font-bold">{waiting.toFixed(1)}s</span>
        </div>

        <div className="bg-slate-900/80 p-2 rounded border border-white/5">
          <span className="text-slate-400 block text-[10px] flex items-center gap-1">
            <span className="w-2 h-2 rounded-full bg-rose-500 inline-block" /> Retry
          </span>
          <span className="text-rose-300 font-bold">{retry.toFixed(1)}s</span>
        </div>
      </div>
    </div>
  );
};

// Helper for percent
function getPt(val: number): number {
  return Math.max(0, val);
}
