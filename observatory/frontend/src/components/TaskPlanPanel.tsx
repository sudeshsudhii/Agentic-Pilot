import React from "react";
import { CheckCircle2, Circle, Clock, ListChecks } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface TaskPlanPanelProps {
  events: ObservatoryEvent[];
}

export const TaskPlanPanel: React.FC<TaskPlanPanelProps> = ({ events }) => {
  let taskSummary = "No plan created yet";
  let steps: Array<{
    step_index: number;
    description: string;
    action_type?: string;
    status: string;
    expected_outcome?: string;
  }> = [];

  let currentStepIdx = 1;

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "PLAN_CREATED") {
      taskSummary = meta.task_summary || ev.message || taskSummary;
      if (Array.isArray(meta.plan)) {
        steps = meta.plan;
      }
    }

    if (ev.event_type === "STEP_PROGRESS" && meta.step) {
      currentStepIdx = meta.step;
      const matchingStep = steps.find((s) => s.step_index === meta.step);
      if (matchingStep) {
        matchingStep.status = meta.action_status || "running";
      }
    }

    if (ev.event_type === "NAVIGATION_SUCCEEDED" && steps.length > 0) {
      if (steps[0].action_type === "navigate" || steps[0].description.toLowerCase().includes("navigate")) {
        steps[0].status = "completed";
      }
    }

    if (ev.event_type === "ACTION_SUCCEEDED" && meta.step_index) {
      const matching = steps.find((s) => s.step_index === meta.step_index);
      if (matching) matching.status = "completed";
    }

    if (ev.event_type === "VERIFICATION_PASSED" || ev.event_type === "TASK_COMPLETED") {
      steps.forEach((s) => (s.status = "completed"));
    }
  });

  return (
    <div className="obs-card p-4 flex flex-col gap-3">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <ListChecks className="w-4 h-4 text-emerald-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Task Plan & Progress
          </h2>
        </div>
        <span className="badge badge-emerald text-[10px]">
          {steps.length > 0 ? `${steps.filter((s) => s.status === "completed").length}/${steps.length} Steps` : "Idle"}
        </span>
      </div>

      <div className="text-xs text-slate-300 font-sans font-medium bg-slate-950/60 p-2.5 rounded-md border border-white/5">
        <span className="font-mono text-slate-500 font-semibold mr-1.5">GOAL:</span>
        {taskSummary}
      </div>

      {/* Steps List */}
      <div className="flex flex-col gap-2">
        {steps.length === 0 ? (
          <div className="text-xs text-slate-400 italic p-3 text-center">
            Awaiting intent parsing and task plan decomposition...
          </div>
        ) : (
          steps.map((step) => {
            const isCompleted = step.status === "completed";
            const isCurrent = step.step_index === currentStepIdx && !isCompleted;
            const isPending = !isCompleted && !isCurrent;

            return (
              <div
                key={step.step_index}
                className={`flex items-start gap-3 p-2.5 rounded-lg border text-xs transition-all ${
                  isCompleted
                    ? "bg-emerald-950/20 border-emerald-500/30 text-emerald-300"
                    : isCurrent
                    ? "bg-cyan-950/30 border-cyan-500/40 text-cyan-200 shadow-md shadow-cyan-950/50"
                    : "bg-slate-900/40 border-white/5 text-slate-400"
                }`}
              >
                {/* Status Icon */}
                <div className="mt-0.5 shrink-0">
                  {isCompleted ? (
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                  ) : isCurrent ? (
                    <Clock className="w-4 h-4 text-cyan-400 animate-spin" />
                  ) : (
                    <Circle className="w-4 h-4 text-slate-600" />
                  )}
                </div>

                <div className="flex flex-col gap-0.5 flex-1 min-w-0">
                  <div className="flex items-center justify-between gap-2">
                    <span className="font-mono font-bold">
                      {step.step_index}. {step.description}
                    </span>
                    <span
                      className={`badge text-[9px] ${
                        isCompleted
                          ? "badge-emerald"
                          : isCurrent
                          ? "badge-cyan"
                          : "badge-slate"
                      }`}
                    >
                      {isCompleted ? "COMPLETED" : isCurrent ? "CURRENT" : "PENDING"}
                    </span>
                  </div>

                  {step.expected_outcome && (
                    <div className="text-[11px] text-slate-400 italic">
                      Expected: {step.expected_outcome}
                    </div>
                  )}
                </div>
              </div>
            );
          })
        )}
      </div>
    </div>
  );
};
