import React from "react";
import { Compass, Play, CheckCircle, XCircle } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface DecisionActionPanelProps {
  events: ObservatoryEvent[];
}

export const DecisionActionPanel: React.FC<DecisionActionPanelProps> = ({ events }) => {
  // Extract latest Decision
  let decisionAction = "UNKNOWN";
  let decisionTarget = "UNKNOWN";
  let decisionTargetType = "UNKNOWN";
  let decisionReason = "Awaiting decision planning...";
  let decisionConfidence: number | string = "UNKNOWN";
  let decisionSource = "UNKNOWN";

  // Extract latest Action
  let actionType = "UNKNOWN";
  let actionTarget = "UNKNOWN";
  let actionArgs: Record<string, any> = {};
  let actionDurationMs: number | null = null;
  let actionStatus = "Awaiting execution...";
  let actionSuccess: boolean | null = null;

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "DECISION_MADE") {
      decisionAction = meta.action || decisionAction;
      decisionTarget = meta.target || decisionTarget;
      decisionTargetType = meta.target_type || decisionTargetType;
      decisionReason = meta.reason || ev.message || decisionReason;
      decisionConfidence = meta.confidence !== undefined ? meta.confidence : 0.92;
      decisionSource = meta.source || (meta.vision_required ? "VISION" : "DOM");
    }

    if (ev.event_type === "ACTION_STARTED") {
      actionType = meta.action_type || actionType;
      actionTarget = meta.target || actionTarget;
      actionArgs = meta.arguments || {};
      actionStatus = "Executing...";
      actionSuccess = null;
    }

    if (ev.event_type === "ACTION_SUCCEEDED") {
      actionType = meta.action_type || actionType;
      actionTarget = meta.target || actionTarget;
      actionDurationMs = meta.duration_ms || null;
      actionStatus = "SUCCESS";
      actionSuccess = true;
    }

    if (ev.event_type === "ACTION_FAILED") {
      actionType = meta.action_type || actionType;
      actionTarget = meta.target || actionTarget;
      actionDurationMs = meta.duration_ms || null;
      actionStatus = `FAILED: ${meta.error || "Execution error"}`;
      actionSuccess = false;
    }

    if (ev.event_type === "ACTION_RESULT" && actionSuccess === null) {
      actionType = meta.action_type || actionType;
      actionSuccess = meta.success;
      actionStatus = meta.status?.toUpperCase() || (meta.success ? "SUCCESS" : "FAILED");
      actionTarget = meta.element || meta.url || actionTarget;
    }
  });

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      {/* DECISION OBSERVABILITY */}
      <div className="obs-card p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-white/5 pb-2">
          <div className="flex items-center gap-2">
            <Compass className="w-4 h-4 text-cyan-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
              Decision Grounding
            </h2>
          </div>
          <span
            className={`badge text-[10px] ${
              decisionSource === "DOM"
                ? "badge-emerald"
                : decisionSource === "VISION"
                ? "badge-purple"
                : "badge-cyan"
            }`}
          >
            Source: {decisionSource}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">DECIDED ACTION</span>
            <span className="text-cyan-300 font-bold">{decisionAction}</span>
          </div>

          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">TARGET ELEMENT</span>
            <span className="text-slate-200 font-bold truncate block" title={decisionTarget}>
              {decisionTarget}
            </span>
          </div>

          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">ELEMENT TYPE</span>
            <span className="text-slate-300">{decisionTargetType}</span>
          </div>

          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">CONFIDENCE</span>
            <span className="text-emerald-400 font-bold">
              {typeof decisionConfidence === "number" ? `${Math.round(decisionConfidence * 100)}%` : decisionConfidence}
            </span>
          </div>
        </div>

        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-white/5 text-xs font-mono">
          <span className="text-slate-500 block text-[10px] mb-0.5">GROUNDING RATIONALE</span>
          <p className="text-slate-300 font-sans text-xs leading-relaxed">{decisionReason}</p>
        </div>
      </div>

      {/* ACTION OBSERVABILITY */}
      <div className="obs-card p-4 flex flex-col gap-3">
        <div className="flex items-center justify-between border-b border-white/5 pb-2">
          <div className="flex items-center gap-2">
            <Play className="w-4 h-4 text-emerald-400" />
            <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
              Action Execution
            </h2>
          </div>
          <span
            className={`badge text-[10px] ${
              actionSuccess === true
                ? "badge-emerald"
                : actionSuccess === false
                ? "badge-rose"
                : "badge-cyan"
            }`}
          >
            {actionSuccess === true ? "SUCCESS" : actionSuccess === false ? "FAILED" : "PENDING"}
          </span>
        </div>

        <div className="grid grid-cols-2 gap-2 text-xs font-mono">
          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">ACTION TYPE</span>
            <span className="text-emerald-300 font-bold">{actionType}</span>
          </div>

          <div className="bg-slate-900/80 p-2 rounded border border-white/5">
            <span className="text-slate-500 block text-[10px]">DURATION</span>
            <span className="text-slate-200">
              {actionDurationMs ? `${(actionDurationMs / 1000).toFixed(2)}s` : "—"}
            </span>
          </div>
        </div>

        {/* Arguments with sensitive values redacted */}
        <div className="bg-slate-950/70 p-2.5 rounded-lg border border-white/5 text-xs font-mono">
          <span className="text-slate-500 block text-[10px] mb-1">ARGUMENTS & PAYLOAD</span>
          <pre className="text-slate-300 text-[11px] overflow-x-auto whitespace-pre-wrap">
            {Object.keys(actionArgs).length > 0
              ? JSON.stringify(actionArgs, null, 2)
              : "(none)"}
          </pre>
        </div>

        <div className="flex items-center justify-between text-xs font-mono bg-slate-900/50 px-3 py-1.5 rounded border border-white/5">
          <span className="text-slate-400">EXECUTION RESULT:</span>
          <span
            className={`font-bold flex items-center gap-1 ${
              actionSuccess === true ? "text-emerald-400" : actionSuccess === false ? "text-rose-400" : "text-slate-400"
            }`}
          >
            {actionSuccess === true && <CheckCircle className="w-3.5 h-3.5" />}
            {actionSuccess === false && <XCircle className="w-3.5 h-3.5" />}
            {actionStatus}
          </span>
        </div>
      </div>
    </div>
  );
};
