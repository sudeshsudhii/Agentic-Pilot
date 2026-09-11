import React from "react";
import { Eye, Check, X, ShieldCheck, Camera } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface VisionObservabilityPanelProps {
  events: ObservatoryEvent[];
}

export const VisionObservabilityPanel: React.FC<VisionObservabilityPanelProps> = ({ events }) => {
  let screenshotCaptured = false;
  let screenshotCount = 0;
  let visionCalled = false;
  let imageAttached = false;
  let visionModel = "UNKNOWN";
  let visionDurationMs: number | null = null;
  let visionStatus = "INACTIVE";
  let visionRequired: boolean | null = null;
  let visionResultSummary = "None";

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "SCREENSHOT_CAPTURED" || ev.event_type === "SCREENSHOT_TAKEN") {
      screenshotCaptured = true;
      screenshotCount += 1;
    }

    if (ev.event_type === "VISION_STATUS") {
      visionModel = meta.model || visionModel;
      visionStatus = meta.status || visionStatus;
    }

    if (ev.event_type === "VISION_CHECK" && meta.vision_required !== undefined) {
      visionRequired = meta.vision_required;
    }

    if (ev.event_type === "DECISION_MADE" && meta.vision_required !== undefined) {
      visionRequired = meta.vision_required;
    }

    if (ev.event_type === "VISION_STARTED") {
      visionCalled = true;
      imageAttached = meta.image_attached ?? true;
      visionModel = meta.model || visionModel;
      visionStatus = "CALLING_MODEL";
    }

    if (ev.event_type === "VISION_COMPLETED") {
      visionCalled = true;
      imageAttached = meta.image_attached ?? true;
      visionModel = meta.model || visionModel;
      visionDurationMs = meta.duration_ms || null;
      visionStatus = meta.status || "COMPLETED";
      visionResultSummary = meta.result_summary || "Visual coordinates grounded successfully";
    }

    if (ev.event_type === "VISION_UNAVAILABLE") {
      visionCalled = false;
      visionStatus = "UNAVAILABLE";
      visionResultSummary = "Vision model unavailable or multimodal input unsupported";
    }
  });

  return (
    <div className="obs-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <Eye className="w-4 h-4 text-purple-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Vision Inference Telemetry
          </h2>
        </div>
        <span
          className={`badge text-[10px] ${
            visionCalled
              ? "badge-purple"
              : visionRequired === false
              ? "badge-emerald"
              : "badge-slate"
          }`}
        >
          {visionCalled ? "Vision Inferred" : visionRequired === false ? "DOM Grounded" : "Inactive"}
        </span>
      </div>

      {/* Strict Distinction Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
        {/* 1. Screenshot Captured */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex flex-col gap-1">
          <div className="text-slate-400 text-[11px] flex items-center gap-1">
            <Camera className="w-3 h-3 text-cyan-400" />
            <span>SCREENSHOT:</span>
          </div>
          <div className="flex items-center gap-1.5 font-bold">
            {screenshotCaptured ? (
              <span className="text-cyan-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5 text-cyan-400" /> CAPTURED ({screenshotCount})
              </span>
            ) : (
              <span className="text-slate-500">AWAITING</span>
            )}
          </div>
        </div>

        {/* 2. Vision Called */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex flex-col gap-1">
          <div className="text-slate-400 text-[11px]">VISION CALLED:</div>
          <div className="flex items-center gap-1.5 font-bold">
            {visionCalled ? (
              <span className="text-purple-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5 text-purple-400" /> TRUE
              </span>
            ) : (
              <span className="text-slate-400 flex items-center gap-1">
                <X className="w-3.5 h-3.5 text-slate-500" /> FALSE
              </span>
            )}
          </div>
        </div>

        {/* 3. Image Attached */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex flex-col gap-1">
          <div className="text-slate-400 text-[11px]">IMAGE ATTACHED:</div>
          <div className="flex items-center gap-1.5 font-bold">
            {imageAttached ? (
              <span className="text-purple-400 flex items-center gap-1">
                <Check className="w-3.5 h-3.5 text-purple-400" /> YES
              </span>
            ) : (
              <span className="text-slate-500">NO</span>
            )}
          </div>
        </div>

        {/* 4. Vision Required */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex flex-col gap-1">
          <div className="text-slate-400 text-[11px]">VISION REQUIRED:</div>
          <div className="font-bold">
            {visionRequired === false ? (
              <span className="text-emerald-400">FALSE (DOM First)</span>
            ) : visionRequired === true ? (
              <span className="text-amber-400">TRUE (Visual Required)</span>
            ) : (
              <span className="text-slate-500">EVALUATING</span>
            )}
          </div>
        </div>
      </div>

      {/* Vision Inference Details */}
      <div className="bg-slate-950/70 border border-white/5 rounded-lg p-3 text-xs font-mono flex flex-col gap-2">
        <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
          <div>
            <span className="text-slate-500 mr-2">VISION MODEL:</span>
            <span className="text-purple-300 font-bold">{visionModel}</span>
          </div>
          <div>
            <span className="text-slate-500 mr-2">INFERENCE LATENCY:</span>
            <span className="text-slate-200">
              {visionDurationMs !== null ? `${(visionDurationMs / 1000).toFixed(2)} sec` : "N/A"}
            </span>
          </div>
          <div>
            <span className="text-slate-500 mr-2">STATUS:</span>
            <span className={`badge ${visionCalled ? "badge-purple" : "badge-slate"} text-[9px]`}>
              {visionStatus}
            </span>
          </div>
        </div>

        <div>
          <span className="text-slate-500 mr-2">RESULT SUMMARY:</span>
          <span className="text-slate-300 font-sans text-xs">
            {visionCalled
              ? visionResultSummary
              : visionRequired === false
              ? "Vision was bypassed because DOM-first grounding identified interactive target directly."
              : "Vision model has not been invoked."}
          </span>
        </div>
      </div>
    </div>
  );
};
