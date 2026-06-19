import { AlertCircle, CheckCircle2, Clock3, Globe, Monitor, ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, BrowserStatus, closeBrowser, getBrowserStatus, Task, TaskEvent } from "../api/client";

type Props = {
  task: Task | null;
  events: TaskEvent[];
};

const statusIcon = {
  completed: <CheckCircle2 size={17} />,
  failed: <AlertCircle size={17} />,
  waiting_approval: <ShieldAlert size={17} />,
  running: <Clock3 size={17} />
};

export function ExecutionPanel({ task, events }: Props) {
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null);
  const [closing, setClosing] = useState(false);

  // Poll browser status when task is completed
  useEffect(() => {
    if (!task || task.status !== "completed") {
      setBrowserStatus(null);
      return;
    }

    let cancelled = false;

    async function poll() {
      try {
        const status = await getBrowserStatus();
        if (!cancelled) setBrowserStatus(status);
      } catch {
        if (!cancelled) setBrowserStatus(null);
      }
    }

    poll();
    const interval = window.setInterval(poll, 3000);
    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [task?.task_id, task?.status]);

  // Also react to BROWSER_CLOSED/BROWSER_TIMEOUT events
  useEffect(() => {
    const browserClosed = events.some(
      (e) => e.type === "BROWSER_CLOSED" || e.type === "BROWSER_TIMEOUT"
    );
    if (browserClosed) {
      setBrowserStatus((prev) => (prev ? { ...prev, open: false } : null));
    }
  }, [events]);

  const handleCloseBrowser = useCallback(async () => {
    if (!task?.task_id || closing) return;
    setClosing(true);
    try {
      await closeBrowser(task.task_id);
      setBrowserStatus((prev) => (prev ? { ...prev, open: false } : null));
    } catch (err) {
      console.error("Failed to close browser:", err);
    } finally {
      setClosing(false);
    }
  }, [task?.task_id, closing]);

  // Derive current state from the event stream
  const currentUrlEvent = events.slice().reverse().find(e => e.type === "CURRENT_URL_CHANGED" || e.type === "NAVIGATION_COMPLETED");
  const currentUrl = (currentUrlEvent?.payload?.url as string) || "about:blank";

  const actionEvent = events.slice().reverse().find(e => e.type.startsWith("ACTION_") || e.type === "NAVIGATION_STARTED" || e.type === "plan_generated" || e.type === "VERIFICATION_STARTED");
  const currentAction = actionEvent?.message || "Initializing...";

  const screenshotEvent = events.slice().reverse().find(e => e.type === "SCREENSHOT_TAKEN");
  const screenshotFilename = screenshotEvent?.payload?.filename as string | undefined;
  
  // Derive a simple browser state text based on recent events
  const latestEvent = events[events.length - 1];
  let browserState = "Idle";
  if (latestEvent) {
      if (latestEvent.type === "BROWSER_LAUNCHED") browserState = "Launching";
      else if (latestEvent.type === "TAB_CREATED") browserState = "Ready";
      else if (latestEvent.type === "NAVIGATION_STARTED") browserState = "Navigating";
      else if (latestEvent.type.startsWith("ACTION_")) browserState = "Executing Action";
      else if (latestEvent.type.startsWith("VERIFICATION_")) browserState = "Verifying";
      else if (latestEvent.type === "BROWSER_RETAINED") browserState = "Open (Retained)";
      else if (latestEvent.type === "BROWSER_CLOSED") browserState = "Closed";
      else if (latestEvent.type === "BROWSER_TIMEOUT") browserState = "Closed (Timeout)";
      else if (latestEvent.type === "completed") browserState = "Completed";
  }

  // Format idle time
  const formatIdleTime = (seconds: number): string => {
    if (seconds < 60) return `${seconds}s`;
    const mins = Math.floor(seconds / 60);
    const secs = seconds % 60;
    return `${mins}m ${secs}s`;
  };

  return (
    <section className="panel execution-panel">
      <div className="panel-heading">
        <h2>Execution</h2>
        <span className={`status-pill ${task?.status ?? "idle"}`}>
          {(task?.status && statusIcon[task.status as keyof typeof statusIcon]) ?? <Clock3 size={17} />}
          {task?.status ?? "idle"}
        </span>
      </div>

      {/* Browser Control Bar */}
      {browserStatus?.open && task?.status === "completed" && (
        <div className="browser-control-bar">
          <div className="browser-status-row">
            <span className="browser-status-indicator">
              <Monitor size={16} />
              <span className="browser-dot alive" />
              Browser Open
            </span>
            <span className="browser-idle-time">
              <Clock3 size={13} />
              Idle: {formatIdleTime(browserStatus.idle_seconds)} / {browserStatus.timeout_minutes}m
            </span>
          </div>
          {browserStatus.url && (
            <div className="browser-url-row">
              <Globe size={13} />
              <span className="browser-url-text" title={browserStatus.url}>{browserStatus.url}</span>
            </div>
          )}
          <div className="browser-actions-row">
            <button
              className="browser-close-btn"
              onClick={handleCloseBrowser}
              disabled={closing}
              id="close-browser-btn"
              aria-label="Close browser"
            >
              <X size={14} />
              {closing ? "Closing…" : "Close Browser"}
            </button>
          </div>
        </div>
      )}

      {/* Browser Closed Banner */}
      {browserStatus && !browserStatus.open && task?.status === "completed" && (
        <div className="browser-closed-banner">
          <Monitor size={16} />
          Browser closed
        </div>
      )}
      
      {task ? (
        <div className="observability-banner">
          <div className="obs-row">
            <span className="obs-label">Current Action:</span>
            <span className="obs-value">{currentAction}</span>
          </div>
          <div className="obs-row">
            <span className="obs-label">Current URL:</span>
            <span className="obs-value">{currentUrl}</span>
          </div>
          <div className="obs-row">
            <span className="obs-label">Browser State:</span>
            <span className="obs-value">{browserState}</span>
          </div>
          {screenshotFilename && task.task_id && (
            <div className="obs-screenshot">
              <span className="obs-label">Last Screenshot:</span>
              <img 
                src={`${API_BASE}/api/tasks/${task.task_id}/evidence/${screenshotFilename}`} 
                alt="Browser Evidence" 
                className="evidence-img"
              />
            </div>
          )}
        </div>
      ) : null}

      {task ? <p className="task-line">{task.input_text}</p> : <p className="muted">No task is running.</p>}
      <div className="event-list">
        {events.map((event) => (
          <div className="event-row" key={event.id}>
            <span className="event-dot" />
            <div>
              <strong>{event.message}</strong>
              <small>{event.type}</small>
            </div>
          </div>
        ))}
      </div>
      {task?.result ? <pre className="result-block">{JSON.stringify(task.result, null, 2)}</pre> : null}
      {task?.error ? <p className="error-text">{task.error}</p> : null}
    </section>
  );
}
