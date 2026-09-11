import React, { useState } from "react";
import { ListFilter, ChevronDown, ChevronRight, Copy, Check, Terminal, Search } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface TimelineTraceProps {
  events: ObservatoryEvent[];
}

export const TimelineTrace: React.FC<TimelineTraceProps> = ({ events }) => {
  const [filter, setFilter] = useState<string>("");
  const [selectedEventId, setSelectedEventId] = useState<string | null>(null);
  const [copiedId, setCopiedId] = useState<string | null>(null);

  const filteredEvents = events.filter((e) => {
    if (!filter) return true;
    const q = filter.toLowerCase();
    return (
      e.event_type.toLowerCase().includes(q) ||
      e.message.toLowerCase().includes(q) ||
      e.event_id.toLowerCase().includes(q)
    );
  });

  const getEventBadgeClass = (type: string, status: string) => {
    if (type.includes("FAIL") || status === "failed" || type === "BLOCKED") return "badge-rose";
    if (type.includes("SUCCEEDED") || type.includes("PASSED") || type.includes("COMPLETED")) return "badge-emerald";
    if (type.includes("VISION")) return "badge-purple";
    if (type.includes("MODEL") || type.includes("PLAN")) return "badge-cyan";
    if (type.includes("ACTION") || type.includes("DECISION")) return "badge-amber";
    return "badge-slate";
  };

  const copyJson = (event: ObservatoryEvent) => {
    navigator.clipboard.writeText(JSON.stringify(event, null, 2));
    setCopiedId(event.event_id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const selectedEvent = events.find((e) => e.event_id === selectedEventId);

  return (
    <div className="obs-card p-4 flex flex-col gap-3">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <Terminal className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Live Execution Trace ({events.length} Events)
          </h2>
        </div>

        {/* Filter Input */}
        <div className="flex items-center gap-2">
          <div className="relative">
            <Search className="w-3.5 h-3.5 text-slate-500 absolute left-2.5 top-2.5" />
            <input
              type="text"
              placeholder="Filter events..."
              value={filter}
              onChange={(e) => setFilter(e.target.value)}
              className="bg-slate-950/80 border border-white/10 rounded px-2.5 py-1 pl-8 text-xs font-mono text-slate-200 focus:outline-none focus:border-cyan-500/50 w-44"
            />
          </div>
        </div>
      </div>

      {/* Timeline Stream */}
      <div className="flex flex-col md:flex-row gap-4 max-h-[500px] overflow-hidden">
        {/* Events List */}
        <div className="flex-1 overflow-y-auto pr-1 flex flex-col gap-1.5 timeline-track pl-4">
          {filteredEvents.length === 0 ? (
            <div className="text-xs text-slate-400 italic p-6 text-center">
              No events recorded yet. Connect to Pilot backend or execute a task.
            </div>
          ) : (
            filteredEvents.map((ev) => {
              const isSelected = ev.event_id === selectedEventId;
              const timeStr = ev.timestamp ? ev.timestamp.split("T")[1]?.slice(0, 8) || ev.timestamp : "";

              return (
                <div
                  key={ev.event_id}
                  onClick={() => setSelectedEventId(isSelected ? null : ev.event_id)}
                  className={`p-2 rounded-lg border text-xs font-mono cursor-pointer transition-all flex items-center justify-between gap-3 ${
                    isSelected
                      ? "bg-cyan-950/40 border-cyan-500/50 ring-1 ring-cyan-500/30"
                      : "bg-slate-900/60 border-white/5 hover:border-white/15 hover:bg-slate-900/90"
                  }`}
                >
                  <div className="flex items-center gap-2.5 min-w-0">
                    <span className="text-slate-400 text-[11px] shrink-0">{timeStr}</span>
                    <span className={`badge ${getEventBadgeClass(ev.event_type, ev.status)} text-[9px]`}>
                      {ev.event_type}
                    </span>
                    <span className="text-slate-300 font-sans text-xs truncate" title={ev.message}>
                      {ev.message}
                    </span>
                  </div>

                  <div className="flex items-center gap-1 shrink-0">
                    {ev.step_index > 0 && (
                      <span className="text-[10px] text-slate-400">Step {ev.step_index}</span>
                    )}
                    {isSelected ? (
                      <ChevronDown className="w-3.5 h-3.5 text-cyan-400" />
                    ) : (
                      <ChevronRight className="w-3.5 h-3.5 text-slate-600" />
                    )}
                  </div>
                </div>
              );
            })
          )}
        </div>

        {/* Event Inspector Drawer */}
        {selectedEvent && (
          <div className="w-full md:w-[360px] lg:w-[420px] bg-slate-950/90 border border-cyan-500/30 rounded-lg p-3 text-xs font-mono flex flex-col gap-2 shrink-0">
            <div className="flex items-center justify-between border-b border-white/10 pb-2">
              <span className="font-bold text-cyan-400">EVENT INSPECTOR</span>
              <button
                onClick={() => copyJson(selectedEvent)}
                className="flex items-center gap-1 text-[11px] text-slate-400 hover:text-white"
              >
                {copiedId === selectedEvent.event_id ? (
                  <Check className="w-3.5 h-3.5 text-emerald-400" />
                ) : (
                  <Copy className="w-3.5 h-3.5" />
                )}
                {copiedId === selectedEvent.event_id ? "Copied" : "Copy JSON"}
              </button>
            </div>

            <div className="space-y-1 text-[11px]">
              <div>
                <span className="text-slate-400">EVENT ID:</span>{" "}
                <span className="text-slate-200">{selectedEvent.event_id}</span>
              </div>
              <div>
                <span className="text-slate-400">EVENT TYPE:</span>{" "}
                <span className="text-cyan-300 font-bold">{selectedEvent.event_type}</span>
              </div>
              <div>
                <span className="text-slate-400">STATUS:</span>{" "}
                <span className="text-emerald-400">{selectedEvent.status}</span>
              </div>
              <div>
                <span className="text-slate-400">TIMESTAMP:</span>{" "}
                <span className="text-slate-200">{selectedEvent.timestamp}</span>
              </div>
              <div>
                <span className="text-slate-400">RUN / TASK ID:</span>{" "}
                <span className="text-slate-300 truncate block">{selectedEvent.run_id}</span>
              </div>
              <div>
                <span className="text-slate-400">MESSAGE:</span>{" "}
                <span className="text-slate-200 font-sans">{selectedEvent.message}</span>
              </div>
            </div>

            <div className="mt-1 flex flex-col gap-1">
              <span className="text-slate-400 text-[10px]">PAYLOAD METADATA:</span>
              <pre className="json-box text-[11px] whitespace-pre-wrap">
                {JSON.stringify(selectedEvent.metadata || {}, null, 2)}
              </pre>
            </div>
          </div>
        )}
      </div>
    </div>
  );
};
