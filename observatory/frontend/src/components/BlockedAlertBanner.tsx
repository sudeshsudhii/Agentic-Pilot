import React from "react";
import { AlertTriangle, ShieldAlert, RefreshCw, AlertCircle } from "lucide-react";
import { ObservatoryEvent } from "../types";

interface BlockedAlertBannerProps {
  events: ObservatoryEvent[];
}

export const BlockedAlertBanner: React.FC<BlockedAlertBannerProps> = ({ events }) => {
  let isBlocked = false;
  let blockedReason = "";
  let recoveryOptions: string[] = [];
  let blockedUrl = "";

  const retries: Array<{
    number: number;
    strategy: string;
    reason: string;
    model?: string;
  }> = [];

  events.forEach((ev) => {
    const meta = ev.metadata || {};

    if (ev.event_type === "BLOCKED" || ev.event_type === "CAPTCHA_DETECTED" || ev.status === "blocked") {
      isBlocked = true;
      blockedReason = meta.reason || meta.blocked_reason || ev.message || "Execution blocked";
      if (meta.recovery_options && Array.isArray(meta.recovery_options)) {
        recoveryOptions = meta.recovery_options;
      }
      if (meta.url) blockedUrl = meta.url;
    }

    if (ev.event_type === "RETRY_ATTEMPTED" || ev.event_type === "RECOVERY_ATTEMPT") {
      retries.push({
        number: meta.retry_number || retries.length + 1,
        strategy: meta.strategy || "Escalation",
        reason: meta.reason || ev.message,
        model: meta.model,
      });
    }
  });

  return (
    <>
      {/* BLOCKED BANNER */}
      {isBlocked && (
        <div className="bg-rose-950/80 border-2 border-rose-500/80 rounded-xl p-4 shadow-lg shadow-rose-950/50 flex items-start gap-4">
          <div className="p-2 bg-rose-900/60 rounded-lg text-rose-300 shrink-0">
            <ShieldAlert className="w-6 h-6 animate-pulse" />
          </div>
          <div className="flex flex-col gap-1.5 flex-1 min-w-0 font-mono text-xs">
            <div className="flex items-center justify-between">
              <span className="text-sm font-bold text-rose-200 tracking-wider">
                EXECUTION BLOCKED — HUMAN VERIFICATION REQUIRED
              </span>
              <span className="badge badge-rose text-[10px]">BLOCKED</span>
            </div>
            <div className="text-slate-300 font-sans text-xs">
              <span className="font-mono text-rose-400 font-bold mr-1">REASON:</span>
              {blockedReason}
            </div>
            {blockedUrl && (
              <div className="text-slate-400 truncate">
                <span className="text-slate-500 mr-1">URL:</span>
                <span className="text-cyan-300">{blockedUrl}</span>
              </div>
            )}
            {recoveryOptions.length > 0 && (
              <div className="mt-1 flex items-center gap-2">
                <span className="text-slate-400">RECOVERY OPTIONS:</span>
                {recoveryOptions.map((opt) => (
                  <span key={opt} className="badge badge-amber text-[9px]">
                    {opt.replace("_", " ")}
                  </span>
                ))}
              </div>
            )}
          </div>
        </div>
      )}

      {/* RETRY / REPLAN CARDS */}
      {retries.length > 0 && (
        <div className="obs-card p-3 border-amber-500/30 bg-amber-950/10 flex flex-col gap-2">
          <div className="flex items-center gap-2 text-xs font-mono font-bold text-amber-400">
            <RefreshCw className="w-3.5 h-3.5" />
            <span>RETRY & RECOVERY ATTEMPTS ({retries.length})</span>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs font-mono">
            {retries.map((r, i) => (
              <div key={i} className="bg-slate-900/90 p-2 rounded border border-white/5">
                <div className="flex items-center justify-between text-amber-300 font-semibold mb-1">
                  <span>RETRY #{r.number}</span>
                  <span className="badge badge-amber text-[9px]">{r.strategy}</span>
                </div>
                <div className="text-slate-400 text-[11px] truncate">
                  Reason: <span className="text-slate-300 font-sans">{r.reason}</span>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </>
  );
};
