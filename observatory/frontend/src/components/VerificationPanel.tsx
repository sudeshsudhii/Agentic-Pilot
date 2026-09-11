import React from "react";
import { CheckCheck, CheckCircle, XCircle, Clock } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface VerificationPanelProps {
  events: ObservatoryEvent[];
}

const formatValue = (val: any): string => {
  if (val === null || val === undefined) return "UNKNOWN";
  if (typeof val === "object") {
    try {
      return JSON.stringify(val, null, 2);
    } catch {
      return String(val);
    }
  }
  return String(val);
};

export const VerificationPanel: React.FC<VerificationPanelProps> = ({ events }) => {
  let requirement: any = "Awaiting task verification...";
  let expected: any = "UNKNOWN";
  let observed: any = "UNKNOWN";
  let domCheck = "PENDING";
  let visionCheck = "SKIPPED";
  let overall = "PENDING";
  let taskCompleted = false;

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "VERIFICATION_STARTED") {
      requirement = ev.message || "Verifying goal satisfaction";
      overall = "VERIFYING";
    }

    if (ev.event_type === "VERIFICATION_RESULT") {
      requirement = meta.message || requirement;
      expected = meta.expected || expected;
      observed = meta.observed || observed;
      overall = meta.passed ? "PASS" : "REJECTED";
      domCheck = meta.passed ? "PASS" : "FAIL";
    }

    if (ev.event_type === "VERIFICATION_PASSED") {
      requirement = meta.requirement || ev.message || requirement;
      expected = meta.expected || expected;
      observed = meta.observed || observed;
      domCheck = meta.dom_check || "PASS";
      visionCheck = meta.vision_check || visionCheck;
      overall = meta.overall || "PASS";
    }

    if (ev.event_type === "TASK_COMPLETED") {
      taskCompleted = true;
    }
  });

  return (
    <div className="obs-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <CheckCheck className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Task Goal Verification
          </h2>
        </div>
        <div className="flex items-center gap-2">
          <span
            className={`badge text-[10px] ${
              overall === "PASS"
                ? "badge-emerald"
                : overall === "REJECTED"
                ? "badge-amber"
                : overall === "FAIL"
                ? "badge-rose"
                : "badge-slate"
            }`}
          >
            Verification: {overall}
          </span>
          {taskCompleted && <span className="badge badge-cyan text-[10px]">TASK COMPLETED</span>}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-3 gap-2 text-xs font-mono">
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 md:col-span-3">
          <span className="text-slate-500 block text-[10px] mb-0.5">VERIFICATION REQUIREMENT</span>
          <span className="text-slate-200 font-sans">{formatValue(requirement)}</span>
        </div>

        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 md:col-span-3 grid grid-cols-1 sm:grid-cols-2 gap-3">
          <div>
            <span className="text-slate-500 block text-[10px] mb-1">EXPECTED VALUE</span>
            <pre className="bg-slate-950/80 p-2 rounded text-cyan-300 font-mono text-[11px] break-words border border-white/5 whitespace-pre-wrap">
              {formatValue(expected)}
            </pre>
          </div>
          <div>
            <span className="text-slate-500 block text-[10px] mb-1">OBSERVED VALUE</span>
            <pre className="bg-slate-950/80 p-2 rounded text-emerald-300 font-mono text-[11px] break-words border border-white/5 whitespace-pre-wrap">
              {formatValue(observed)}
            </pre>
          </div>
        </div>

        {/* Breakdown Badges */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">DOM VERIFICATION:</span>
          <span
            className={`font-bold flex items-center gap-1 ${
              domCheck === "PASS" ? "text-emerald-400" : domCheck === "FAIL" ? "text-rose-400" : "text-slate-400"
            }`}
          >
            {domCheck === "PASS" && <CheckCircle className="w-3.5 h-3.5" />}
            {domCheck === "FAIL" && <XCircle className="w-3.5 h-3.5" />}
            {domCheck}
          </span>
        </div>

        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">VISION VERIFICATION:</span>
          <span
            className={`font-bold flex items-center gap-1 ${
              visionCheck === "PASS" ? "text-purple-400" : "text-slate-400"
            }`}
          >
            {visionCheck}
          </span>
        </div>

        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 flex items-center justify-between">
          <span className="text-slate-400 text-[11px]">OVERALL VERDICT:</span>
          <span
            className={`font-bold flex items-center gap-1 ${
              overall === "PASS" ? "text-emerald-400" : overall === "FAIL" ? "text-rose-400" : "text-amber-400"
            }`}
          >
            {overall === "PASS" && <CheckCircle className="w-3.5 h-3.5" />}
            {overall === "VERIFYING" && <Clock className="w-3.5 h-3.5 animate-spin" />}
            {overall}
          </span>
        </div>
      </div>
    </div>
  );
};
