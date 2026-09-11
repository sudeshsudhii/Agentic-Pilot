import React from "react";
import { SystemStatus } from "../types";
import { Activity, Radio, Clock, ShieldCheck, History, Database, Cpu } from "lucide-react";

interface HeaderProps {
  status: SystemStatus;
  activeTab: string;
  setActiveTab: (tab: string) => void;
  activeRunId: string | null;
  taskTitle: string;
  onReconnect: () => void;
}

export const Header: React.FC<HeaderProps> = ({
  status,
  activeTab,
  setActiveTab,
  activeRunId,
  taskTitle,
  onReconnect,
}) => {
  const backendOnline = status.pilot_backend_connected;
  const streamOnline = status.event_stream_connected;

  const formatAge = (age: number | null) => {
    if (age === null || age === undefined) return "Never";
    if (age < 2) return "Just now";
    if (age < 60) return `${Math.round(age)}s ago`;
    return `${Math.floor(age / 60)}m ${Math.round(age % 60)}s ago`;
  };

  return (
    <header className="obs-header-glow px-6 py-4 sticky top-0 z-40 backdrop-blur-md">
      <div className="max-w-[1700px] mx-auto flex flex-col gap-3">
        <div className="flex flex-wrap items-center justify-between gap-4">
          {/* Brand & App Title */}
          <div className="flex items-center gap-3">
            <div className="w-9 h-9 rounded-lg bg-gradient-to-tr from-cyan-500 to-indigo-600 flex items-center justify-center shadow-lg shadow-cyan-500/20">
              <Activity className="w-5 h-5 text-white animate-pulse" />
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h1 className="text-base font-bold tracking-wider text-white uppercase font-mono">
                  Pilot Agent Observatory
                </h1>
                <span className="badge badge-cyan text-[10px]">Dev Monitor :3001</span>
                <span className="badge badge-slate text-[10px]">Read-Only</span>
              </div>
              <p className="text-xs text-slate-400">
                Real-Time Execution Telemetry & Decision Inspector
              </p>
            </div>
          </div>

          {/* Connection Status Badges */}
          <div className="flex flex-wrap items-center gap-2 sm:gap-4 text-xs font-mono">
            {/* Pilot Backend */}
            <div className="flex items-center gap-2 bg-slate-900/80 border border-white/10 px-3 py-1.5 rounded-md">
              <span className="text-slate-400">PILOT BACKEND:</span>
              <span className={backendOnline ? "dot-online" : "dot-offline"} />
              <span className={backendOnline ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                {backendOnline ? "CONNECTED" : "DISCONNECTED"}
              </span>
            </div>

            {/* Event Stream */}
            <div className="flex items-center gap-2 bg-slate-900/80 border border-white/10 px-3 py-1.5 rounded-md">
              <Radio className="w-3.5 h-3.5 text-cyan-400" />
              <span className="text-slate-400">EVENT STREAM:</span>
              <span className={streamOnline ? "dot-online" : "dot-offline"} />
              <span className={streamOnline ? "text-emerald-400 font-semibold" : "text-rose-400 font-semibold"}>
                {streamOnline ? "CONNECTED" : "DISCONNECTED"}
              </span>
            </div>

            {/* Last Event */}
            <div className="flex items-center gap-2 bg-slate-900/80 border border-white/10 px-3 py-1.5 rounded-md">
              <Clock className="w-3.5 h-3.5 text-indigo-400" />
              <span className="text-slate-400">LAST EVENT:</span>
              <span className="text-slate-200 font-medium">{formatAge(status.last_event_age_sec)}</span>
            </div>

            {(!streamOnline || !backendOnline) && (
              <button
                onClick={onReconnect}
                className="btn-action text-xs"
                title="Force reconnect to Pilot Core"
              >
                Reconnect
              </button>
            )}
          </div>
        </div>

        {/* Sub-bar: Active Task + Tab Navigation */}
        <div className="flex flex-wrap items-center justify-between gap-3 pt-2 border-t border-white/5">
          <div className="flex items-center gap-3 text-xs font-mono overflow-hidden">
            <span className="text-slate-500 font-semibold">RUN ID:</span>
            <span className="text-cyan-300 font-bold bg-cyan-950/40 border border-cyan-500/30 px-2 py-0.5 rounded truncate max-w-[140px] sm:max-w-none">
              {activeRunId || "NONE (IDLE)"}
            </span>
            <span className="text-slate-500">|</span>
            <span className="text-slate-400 truncate max-w-[300px] sm:max-w-[600px]" title={taskTitle}>
              TASK: <span className="text-slate-200 font-sans">{taskTitle || "Waiting for task..."}</span>
            </span>
          </div>

          {/* Navigation Tabs */}
          <div className="flex items-center gap-1 bg-slate-950/60 p-1 rounded-lg border border-white/5">
            <button
              onClick={() => setActiveTab("live")}
              className={`btn-nav ${activeTab === "live" ? "active" : ""}`}
            >
              <Cpu className="w-3.5 h-3.5" />
              Live Observatory
            </button>
            <button
              onClick={() => setActiveTab("history")}
              className={`btn-nav ${activeTab === "history" ? "active" : ""}`}
            >
              <History className="w-3.5 h-3.5" />
              Run History
            </button>
            <button
              onClick={() => setActiveTab("experiences")}
              className={`btn-nav ${activeTab === "experiences" ? "active" : ""}`}
            >
              <Database className="w-3.5 h-3.5" />
              Experiences
            </button>
            <button
              onClick={() => setActiveTab("langgraph")}
              className={`btn-nav ${activeTab === "langgraph" ? "active" : ""}`}
            >
              <ShieldCheck className="w-3.5 h-3.5" />
              LangGraph State
            </button>
          </div>
        </div>
      </div>
    </header>
  );
};
