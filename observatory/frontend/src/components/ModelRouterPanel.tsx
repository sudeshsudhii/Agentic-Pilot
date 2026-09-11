import React from "react";
import { Cpu, Eye, ShieldAlert, ArrowRightLeft } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface ModelRouterPanelProps {
  events: ObservatoryEvent[];
}

export const ModelRouterPanel: React.FC<ModelRouterPanelProps> = ({ events }) => {
  // Extract latest routing and model invocation data from real events
  let plannerModel = "UNKNOWN";
  let visionModel = "UNKNOWN";
  let fallbackModel = "UNKNOWN";
  let routingReason = "UNKNOWN";
  let taskRequires = "UNKNOWN";

  const modelInvocations: Array<{
    id: string;
    model: string;
    purpose: string;
    durationMs: number | null;
    status: string;
    input: string;
    imageAttached: boolean;
    outputSummary: string;
  }> = [];

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "MODEL_SELECTED") {
      plannerModel = meta.planner_model || meta.model || plannerModel;
      visionModel = meta.vision_model || visionModel;
      fallbackModel = meta.fallback_model || fallbackModel;
      routingReason = meta.reason || routingReason;
      taskRequires = meta.role || "Intent & Planning Execution";
    }

    if (ev.event_type === "VISION_STATUS" && meta.model) {
      visionModel = meta.model;
    }

    if (ev.event_type === "VISION_COMPLETED") {
      modelInvocations.push({
        id: ev.event_id,
        model: meta.model || visionModel || "qwen3-vl:2b",
        purpose: "Visual element observation & action grounding",
        durationMs: meta.duration_ms || null,
        status: meta.status || "COMPLETED",
        input: meta.input_type || "Screenshot",
        imageAttached: meta.image_attached ?? true,
        outputSummary: meta.result_summary || ev.message || "Vision inference complete",
      });
    }

    if (ev.event_type === "PLAN_CREATED") {
      modelInvocations.push({
        id: ev.event_id,
        model: plannerModel !== "UNKNOWN" ? plannerModel : "qwen2.5:1.5b",
        purpose: "Task plan decomposition & intent parsing",
        durationMs: meta.duration_ms || null,
        status: "COMPLETED",
        input: "User prompt & page context",
        imageAttached: false,
        outputSummary: `Decomposed into ${meta.total_steps || 1} steps: ${meta.task_summary || ev.message}`,
      });
    }

    if (ev.event_type === "DECISION_MADE" && meta.source === "DOM") {
      // DOM grounding executed without calling vision model
    }
  });

  return (
    <div className="obs-card p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <Cpu className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Model & Dynamic Router
          </h2>
        </div>
        <span className="badge badge-cyan text-[10px]">Ollama Local Tier</span>
      </div>

      {/* 3 Model Tier Display */}
      <div className="grid grid-cols-1 sm:grid-cols-3 gap-3">
        {/* Planner */}
        <div className="bg-slate-900/90 border border-cyan-500/20 rounded-lg p-3">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span className="font-mono">Planner Model</span>
            <span className="badge badge-cyan text-[9px]">Primary</span>
          </div>
          <div className="text-sm font-mono font-bold text-cyan-300 truncate">
            {plannerModel}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Structured intent & JSON planner</div>
        </div>

        {/* Vision */}
        <div className="bg-slate-900/90 border border-purple-500/20 rounded-lg p-3">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span className="font-mono">Vision Model</span>
            <Eye className="w-3.5 h-3.5 text-purple-400" />
          </div>
          <div className="text-sm font-mono font-bold text-purple-300 truncate">
            {visionModel}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Multimodal coordinate grounding</div>
        </div>

        {/* Fallback */}
        <div className="bg-slate-900/90 border border-amber-500/20 rounded-lg p-3">
          <div className="flex items-center justify-between text-xs text-slate-400 mb-1">
            <span className="font-mono">Fallback Model</span>
            <ArrowRightLeft className="w-3.5 h-3.5 text-amber-400" />
          </div>
          <div className="text-sm font-mono font-bold text-amber-300 truncate">
            {fallbackModel}
          </div>
          <div className="text-[11px] text-slate-400 mt-1">Lightweight vision failover</div>
        </div>
      </div>

      {/* Router Rationale */}
      <div className="bg-slate-950/70 border border-white/5 rounded-lg p-3 text-xs flex flex-col gap-1.5 font-mono">
        <div className="flex items-center justify-between">
          <span className="text-slate-400">ROUTER POLICY:</span>
          <span className="text-cyan-400 font-semibold">{taskRequires}</span>
        </div>
        <div className="flex items-start gap-2">
          <span className="text-slate-400 shrink-0">REASON:</span>
          <span className="text-slate-300 font-sans text-[12px]">{routingReason}</span>
        </div>
      </div>

      {/* Invocations History */}
      <div>
        <div className="text-xs font-mono text-slate-400 mb-2 flex items-center justify-between">
          <span>MODEL INVOCATIONS ({modelInvocations.length}):</span>
          <span className="text-[11px] text-slate-400">Redacted credentials</span>
        </div>

        {modelInvocations.length === 0 ? (
          <div className="text-xs text-slate-400 italic p-3 bg-slate-950/40 rounded border border-white/5 text-center">
            No active model invocations recorded yet for this run.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-left text-xs font-mono border-collapse">
              <thead>
                <tr className="border-b border-white/10 text-slate-400 text-[11px]">
                  <th className="pb-1.5 font-semibold">MODEL</th>
                  <th className="pb-1.5 font-semibold">PURPOSE</th>
                  <th className="pb-1.5 font-semibold">IMAGE</th>
                  <th className="pb-1.5 font-semibold">DURATION</th>
                  <th className="pb-1.5 font-semibold">STATUS</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-white/5">
                {modelInvocations.map((inv) => (
                  <tr key={inv.id} className="hover:bg-white/[0.02]">
                    <td className="py-2 text-cyan-300 font-medium">{inv.model}</td>
                    <td className="py-2 text-slate-300 max-w-[200px] truncate" title={inv.purpose}>
                      {inv.purpose}
                    </td>
                    <td className="py-2">
                      {inv.imageAttached ? (
                        <span className="badge badge-purple text-[9px]">ATTACHED</span>
                      ) : (
                        <span className="badge badge-slate text-[9px]">NONE</span>
                      )}
                    </td>
                    <td className="py-2 text-slate-400">
                      {inv.durationMs ? `${(inv.durationMs / 1000).toFixed(2)}s` : "—"}
                    </td>
                    <td className="py-2">
                      <span className="badge badge-emerald text-[9px]">{inv.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  );
};
