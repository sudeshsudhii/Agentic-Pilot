import React, { useState } from "react";
import { Globe, Layers, Image as ImageIcon, Maximize2, X, ChevronLeft, ChevronRight } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface ObservationPanelProps {
  events: ObservatoryEvent[];
  activeRunId: string | null;
}

export const ObservationPanel: React.FC<ObservationPanelProps> = ({ events, activeRunId }) => {
  const [modalOpen, setModalOpen] = useState(false);
  const [activeScreenshotIdx, setActiveScreenshotIdx] = useState<number | null>(null);

  // Extract observation metadata
  let currentUrl = "about:blank";
  let pageTitle = "UNKNOWN";
  let domElementCount: number | "UNKNOWN" = "UNKNOWN";
  let interactiveElementCount: number | "UNKNOWN" = "UNKNOWN";

  const screenshots: Array<{
    filename: string;
    url: string;
    width: number;
    height: number;
    title: string;
    timestamp: string;
    stepIndex: number;
  }> = [];

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (meta.url) currentUrl = meta.url;
    if (meta.page_title) pageTitle = meta.page_title;

    if (ev.event_type === "DOM_OBSERVED" || ev.event_type === "DOM_OBSERVATION") {
      if (meta.element_count !== undefined) domElementCount = meta.element_count;
      if (meta.interactive_elements !== undefined) interactiveElementCount = meta.interactive_elements;
      if (meta.url) currentUrl = meta.url;
      if (meta.page_title) pageTitle = meta.page_title;
    }

    if (
      (ev.event_type === "SCREENSHOT_CAPTURED" || ev.event_type === "SCREENSHOT_TAKEN") &&
      meta.filename
    ) {
      const taskFolder = ev.task_id || activeRunId || "";
      const imgUrl = `/api/evidence/${taskFolder}/${meta.filename}`;
      // Avoid duplicate filenames
      if (!screenshots.some((s) => s.filename === meta.filename)) {
        screenshots.push({
          filename: meta.filename,
          url: imgUrl,
          width: meta.width || 1280,
          height: meta.height || 800,
          title: ev.message || meta.filename,
          timestamp: ev.timestamp,
          stepIndex: ev.step_index || 0,
        });
      }
    }
  });

  const latestScreenshot = screenshots.length > 0 ? screenshots[screenshots.length - 1] : null;
  const currentIdx = activeScreenshotIdx !== null ? activeScreenshotIdx : screenshots.length - 1;
  const displayedScreenshot = screenshots[currentIdx] || latestScreenshot;

  return (
    <div className="obs-card p-4 flex flex-col gap-4">
      <div className="flex items-center justify-between border-b border-white/5 pb-2">
        <div className="flex items-center gap-2">
          <Globe className="w-4 h-4 text-cyan-400" />
          <h2 className="text-xs font-bold uppercase tracking-wider font-mono text-slate-200">
            Observation & Browser Proof
          </h2>
        </div>
        <span className="badge badge-cyan text-[10px]">
          {screenshots.length} Screenshots
        </span>
      </div>

      {/* Observation Meta Grid */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 text-xs font-mono">
        {/* URL */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5 col-span-2">
          <div className="text-slate-400 text-[11px] mb-1 flex items-center gap-1">
            <Globe className="w-3 h-3 text-cyan-400" />
            <span>CURRENT URL:</span>
          </div>
          <div className="text-cyan-300 truncate font-sans text-xs" title={currentUrl}>
            {currentUrl}
          </div>
        </div>

        {/* DOM Elements */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5">
          <div className="text-slate-400 text-[11px] mb-1 flex items-center gap-1">
            <Layers className="w-3 h-3 text-indigo-400" />
            <span>DOM ELEMENTS:</span>
          </div>
          <div className="text-slate-200 font-bold">
            {domElementCount !== "UNKNOWN" ? `${domElementCount} elements` : "UNKNOWN"}
          </div>
        </div>

        {/* Interactive Elements */}
        <div className="bg-slate-900/80 p-2.5 rounded border border-white/5">
          <div className="text-slate-400 text-[11px] mb-1">
            <span>INTERACTIVE:</span>
          </div>
          <div className="text-slate-200 font-bold">
            {interactiveElementCount !== "UNKNOWN" ? `${interactiveElementCount} interactive` : "UNKNOWN"}
          </div>
        </div>
      </div>

      {/* Screenshot Viewer Area */}
      <div className="flex flex-col gap-2">
        <div className="flex items-center justify-between text-xs font-mono text-slate-400">
          <span>
            PROOF SCREENSHOT:{" "}
            <span className="text-slate-200 font-bold">
              {displayedScreenshot ? `${displayedScreenshot.width} × ${displayedScreenshot.height}` : "1280 × 800"}
            </span>
          </span>
          {displayedScreenshot && (
            <button
              onClick={() => setModalOpen(true)}
              className="flex items-center gap-1 text-cyan-400 hover:text-cyan-300 transition-colors"
            >
              <Maximize2 className="w-3.5 h-3.5" />
              Expand
            </button>
          )}
        </div>

        {/* Screenshot Preview Box */}
        <div className="relative aspect-[16/10] bg-black/60 rounded-lg overflow-hidden border border-white/10 flex items-center justify-center group">
          {displayedScreenshot ? (
            <>
              <img
                src={displayedScreenshot.url}
                alt={displayedScreenshot.title}
                className="w-full h-full object-contain cursor-pointer"
                onClick={() => setModalOpen(true)}
                onError={(e) => {
                  // If image fails to load via proxy, fallback placeholder
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
              <div className="absolute bottom-2 left-2 right-2 bg-slate-950/80 backdrop-blur-md p-2 rounded text-[11px] font-mono text-slate-300 border border-white/10 flex items-center justify-between">
                <span className="truncate">{displayedScreenshot.title}</span>
                <span className="text-slate-400 shrink-0 ml-2">Step {displayedScreenshot.stepIndex}</span>
              </div>
            </>
          ) : (
            <div className="flex flex-col items-center gap-2 text-slate-400 text-xs font-mono p-6 text-center">
              <ImageIcon className="w-8 h-8 opacity-40" />
              <span>Awaiting first screenshot capture event...</span>
            </div>
          )}
        </div>

        {/* Historical Screenshot Carousel */}
        {screenshots.length > 1 && (
          <div className="flex items-center gap-2 overflow-x-auto py-1">
            {screenshots.map((s, idx) => (
              <button
                key={s.filename}
                onClick={() => setActiveScreenshotIdx(idx)}
                className={`relative shrink-0 w-16 h-10 rounded border overflow-hidden transition-all ${
                  idx === currentIdx
                    ? "border-cyan-400 ring-2 ring-cyan-500/30"
                    : "border-white/10 opacity-60 hover:opacity-100"
                }`}
              >
                <img src={s.url} alt={s.title} className="w-full h-full object-cover" />
                <span className="absolute bottom-0 right-0 bg-black/80 text-[8px] font-mono px-1 text-slate-200">
                  {s.stepIndex}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Fullscreen Expand Modal */}
      {modalOpen && displayedScreenshot && (
        <div className="fixed inset-0 z-50 bg-black/90 backdrop-blur-md flex flex-col p-4">
          <div className="flex items-center justify-between pb-3 border-b border-white/10 text-xs font-mono text-slate-300">
            <div>
              <span className="text-cyan-400 font-bold">{displayedScreenshot.title}</span>
              <span className="text-slate-500 ml-2">({displayedScreenshot.width} × {displayedScreenshot.height})</span>
            </div>
            <button
              onClick={() => setModalOpen(false)}
              className="p-1 hover:bg-white/10 rounded text-slate-400 hover:text-white"
            >
              <X className="w-5 h-5" />
            </button>
          </div>
          <div className="flex-1 overflow-auto flex items-center justify-center p-4">
            <img
              src={displayedScreenshot.url}
              alt={displayedScreenshot.title}
              className="max-w-full max-h-full object-contain rounded shadow-2xl border border-white/10"
            />
          </div>
        </div>
      )}
    </div>
  );
};
