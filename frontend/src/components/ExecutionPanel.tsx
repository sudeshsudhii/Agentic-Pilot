import { AlertCircle, CheckCircle2, Clock3, Globe, Monitor, ShieldAlert, X } from "lucide-react";
import { useCallback, useEffect, useState } from "react";
import { API_BASE, BrowserStatus, closeBrowser, fallbackTask, getBrowserStatus, resumeTask, Task, TaskEvent } from "../api/client";

type Props = {
  task: Task | null;
  events: TaskEvent[];
};

const statusIcon = {
  completed: <CheckCircle2 size={17} />,
  failed: <AlertCircle size={17} />,
  waiting_approval: <ShieldAlert size={17} />,
  running: <Clock3 size={17} />,
  blocked: <ShieldAlert size={17} style={{ color: "#d97706" }} />
};

export function ExecutionPanel({ task, events }: Props) {
  const [browserStatus, setBrowserStatus] = useState<BrowserStatus | null>(null);
  const [closing, setClosing] = useState(false);
  const [recovering, setRecovering] = useState(false);
  const [recoveryError, setRecoveryError] = useState<string | null>(null);

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

  const handleResumeTask = useCallback(async () => {
    if (!task?.task_id || recovering) return;
    setRecovering(true);
    setRecoveryError(null);
    try {
      await resumeTask(task.task_id);
    } catch (err: any) {
      setRecoveryError(err.message || "CAPTCHA challenge is still active. Please complete it in the browser.");
    } finally {
      setRecovering(false);
    }
  }, [task?.task_id, recovering]);

  const handleFallbackTask = useCallback(async () => {
    if (!task?.task_id || recovering) return;
    setRecovering(true);
    setRecoveryError(null);
    try {
      await fallbackTask(task.task_id, "duckduckgo");
    } catch (err: any) {
      setRecoveryError(err.message || "Failed to switch to fallback search provider.");
    } finally {
      setRecovering(false);
    }
  }, [task?.task_id, recovering]);

  // Derive current state from the event stream
  const currentUrlEvent = events.slice().reverse().find(e => e.type === "CURRENT_URL_CHANGED" || e.type === "NAVIGATION_COMPLETED" || e.type === "ACTION_RESULT");
  const currentUrl = (currentUrlEvent?.payload?.url as string) || browserStatus?.url || "about:blank";

  // Task Progress & Current Step
  const stepEvent = events.slice().reverse().find(e => e.type === "STEP_PROGRESS");
  const taskProgress = stepEvent?.payload
    ? `${stepEvent.payload.step}/${stepEvent.payload.total}`
    : "1/1";

  const currentStep = (stepEvent?.payload?.description as string) || 
    (task?.parsed_intent ? `${(task.parsed_intent as Record<string, any>).action || ''} on ${(task.parsed_intent as Record<string, any>).site || 'web'}` : "Processing task");

  // Current Action
  const actionEvent = events.slice().reverse().find(e => 
    e.type.startsWith("ACTION_") || 
    e.type === "NAVIGATION_STARTED" || 
    e.type === "NAVIGATION_COMPLETED" || 
    e.type === "PAGE_READY" || 
    e.type === "DOM_OBSERVATION" || 
    e.type === "plan_generated" || 
    e.type === "VERIFICATION_STARTED"
  );
  let currentAction = actionEvent?.message || "Initializing...";
  if (actionEvent?.type === "ACTION_TYPE") {
    currentAction = "Typing requested text";
  } else if (actionEvent?.type === "NAVIGATION_COMPLETED" || actionEvent?.type === "PAGE_READY" || actionEvent?.type === "DOM_OBSERVATION") {
    currentAction = "Observing page and identifying input field";
  } else if (actionEvent?.type === "ACTION_CLICK") {
    currentAction = "Clicking search result / element";
  } else if (actionEvent?.type === "ACTION_EXTRACT") {
    currentAction = "Extracting page information";
  } else if (actionEvent?.type === "ACTION_KEY") {
    currentAction = `Pressing key "${actionEvent.payload?.key || 'Enter'}"`;
  } else if (actionEvent?.type === "VERIFICATION_STARTED") {
    currentAction = "Starting task verification";
  }

  // Vision Status
  const visionEvent = events.slice().reverse().find(e => e.type === "VISION_STATUS" || e.type === "VISION_UNAVAILABLE");
  const isVisionUnavailable = events.some(e => e.type === "VISION_UNAVAILABLE" || e.payload?.status === "Unavailable");
  const visionStatus = isVisionUnavailable ? "Unavailable" : ((visionEvent?.payload?.status as string) || "Active");

  // Last Action & Action Result
  const actionResultEvent = events.slice().reverse().find(e => e.type === "ACTION_RESULT");
  const lastAction = (actionResultEvent?.payload?.action_type as string) || "None yet";
  const actionResult = actionResultEvent
    ? (actionResultEvent.payload?.success ? "Success" : "Failed")
    : "None";

  // Verification Status
  const verificationEvent = events.slice().reverse().find(e => e.type === "VERIFICATION_RESULT" || e.type === "VERIFICATION_PASSED");
  const verification = verificationEvent
    ? (verificationEvent.type === "VERIFICATION_PASSED" || verificationEvent.payload?.passed ? "Passed" : "Failed")
    : (task?.status === "completed" ? "Passed" : "Pending");

  // Check if task is blocked or CAPTCHA detected
  const isBlocked = task?.status === "blocked" || events.some(e => e.type === "BLOCKED" || e.type === "CAPTCHA_DETECTED");
  const isCaptcha = events.some(e => e.type === "CAPTCHA_DETECTED" || (e.payload?.reason as string || "").includes("verification"));
  const browserState = isCaptcha ? "CAPTCHA DETECTED" : (task?.status === "completed" ? "Completed" : (task ? "Running" : "Idle"));

  // Overall Task Status: Do not show "Completed" unless task-level completion is verified
  let overallTask = "Executing";
  if (isBlocked) {
    overallTask = "BLOCKED";
  } else if (task?.status === "completed") {
    overallTask = "Completed";
  } else if (task?.status === "failed") {
    overallTask = "Failed";
  } else if (task?.status === "waiting_approval") {
    overallTask = "Waiting Approval";
  } else if (!task) {
    overallTask = "Idle";
  }

  const screenshotEvent = events.slice().reverse().find(e => e.type === "SCREENSHOT_TAKEN");
  const screenshotFilename = screenshotEvent?.payload?.filename as string | undefined;

  // Extracted Data and Final Answer
  const extractedData = (task?.result?.extracted_data as Record<string, any>) || {};
  const finalAnswer = (task?.result?.answer as string) || null;

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
        <span className={`status-pill ${isBlocked ? "blocked" : (task?.status ?? "idle")}`}>
          {(task?.status && statusIcon[task.status as keyof typeof statusIcon]) ?? <Clock3 size={17} />}
          {overallTask}
        </span>
      </div>

      {/* Browser Control Bar */}
      {browserStatus?.open && (task?.status === "completed" || isBlocked) && (
        <div className="browser-control-bar">
          <div className="browser-status-row">
            <span className="browser-status-indicator">
              <Monitor size={16} />
              <span className="browser-dot alive" />
              Browser Open ({browserState})
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

      {/* Recovery Box when BLOCKED */}
      {isBlocked && (
        <div className="blocked-recovery-card">
          <div className="blocked-header">
            <ShieldAlert size={22} className="blocked-icon" />
            <div>
              <strong style={{ fontSize: "14px", color: "#b45309" }}>Action Required: Bot Verification Challenge</strong>
              <p style={{ margin: "4px 0 0", fontSize: "13px", color: "#78350f" }}>
                Google has presented a CAPTCHA challenge. Complete it manually in the open browser, or switch to safe search.
              </p>
            </div>
          </div>
          {recoveryError && (
            <div className="recovery-error-banner" style={{ background: "#fef2f2", color: "#b91c1c", padding: "8px 12px", borderRadius: "6px", fontSize: "12.5px", margin: "10px 0" }}>
              {recoveryError}
            </div>
          )}
          <div className="recovery-buttons-row" style={{ display: "flex", gap: "10px", marginTop: "12px" }}>
            <button
              className="recovery-btn resume-btn"
              onClick={handleResumeTask}
              disabled={recovering}
              id="resume-captcha-btn"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                background: "#059669",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <CheckCircle2 size={15} />
              {recovering ? "Checking Page…" : "Complete CAPTCHA & Resume"}
            </button>
            <button
              className="recovery-btn fallback-btn"
              onClick={handleFallbackTask}
              disabled={recovering}
              id="fallback-search-btn"
              style={{
                display: "flex",
                alignItems: "center",
                gap: "6px",
                padding: "8px 14px",
                background: "#2563eb",
                color: "#ffffff",
                border: "none",
                borderRadius: "6px",
                fontWeight: 500,
                cursor: "pointer",
              }}
            >
              <Globe size={15} />
              {recovering ? "Switching Provider…" : "Use Safe Search Fallback"}
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
        <div className="execution-dashboard">
          <div className="dashboard-card">
            <span className="dashboard-label">Task Progress</span>
            <span className="dashboard-value">{taskProgress}</span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Overall Task</span>
            <span className={`dashboard-badge badge-${overallTask.toLowerCase()}`}>
              {overallTask}
            </span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Browser State</span>
            <span className={`dashboard-badge ${isCaptcha ? "badge-failed" : "badge-running"}`}>
              {browserState}
            </span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Vision</span>
            <span className={`dashboard-badge badge-${visionStatus.toLowerCase()}`}>
              {visionStatus}
            </span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Action Result</span>
            <span className={`dashboard-badge badge-${actionResult.toLowerCase()}`}>
              {actionResult}
            </span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Verification</span>
            <span className={`dashboard-badge badge-${verification.toLowerCase()}`}>
              {verification}
            </span>
          </div>
          {isBlocked && (
            <>
              <div className="dashboard-card card-wide">
                <span className="dashboard-label">Reason</span>
                <span className="dashboard-value" style={{ color: "#b45309" }}>Google requires human verification</span>
              </div>
              <div className="dashboard-card card-wide">
                <span className="dashboard-label">Recovery</span>
                <span className="dashboard-value" style={{ color: "#047857" }}>Waiting for user / fallback available</span>
              </div>
            </>
          )}
          <div className="dashboard-card card-wide">
            <span className="dashboard-label">Current Step</span>
            <span className="dashboard-value">{currentStep}</span>
          </div>
          <div className="dashboard-card card-wide">
            <span className="dashboard-label">Current Action</span>
            <span className="dashboard-value">{currentAction}</span>
          </div>
          <div className="dashboard-card">
            <span className="dashboard-label">Last Action</span>
            <span className="dashboard-value">{lastAction}</span>
          </div>
          <div className="dashboard-card card-wide">
            <span className="dashboard-label">Browser URL</span>
            <span className="dashboard-value" style={{ fontFamily: "monospace", fontSize: "12.5px" }}>{currentUrl}</span>
          </div>
        </div>
      ) : null}

      {/* Extracted Findings Display */}
      {Object.keys(extractedData).length > 0 && (
        <div className="findings-box">
          <h3>Extracted Campus Information</h3>
          {Object.entries(extractedData).map(([key, item]: [string, any]) => (
            <div key={key} style={{ marginBottom: "10px" }}>
              <strong>{item?.page_title || key}</strong>
              {item?.content_snippet && <p className="findings-content">{item.content_snippet}</p>}
            </div>
          ))}
        </div>
      )}

      {finalAnswer && (
        <div className="findings-box" style={{ background: "#f0f9ff", borderColor: "#bae6fd" }}>
          <h3 style={{ color: "#0369a1" }}>Final Answer</h3>
          <p className="findings-content" style={{ color: "#0c4a6e", whiteSpace: "pre-wrap" }}>{finalAnswer}</p>
        </div>
      )}

      {screenshotFilename && task?.task_id && (
        <div className="evidence-container">
          <p className="dashboard-label" style={{ marginBottom: "6px" }}>Browser Observation Proof</p>
          <img 
            src={`${API_BASE}/api/tasks/${task.task_id}/evidence/${screenshotFilename}`} 
            alt="Browser Evidence" 
            className="evidence-preview-img"
          />
        </div>
      )}

      {task ? <p className="task-line" style={{ marginTop: "12px", fontSize: "13px" }}><strong>Task Goal:</strong> {task.input_text}</p> : <p className="muted">No task is running.</p>}
      
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
      {task?.result && !finalAnswer ? <pre className="result-block">{JSON.stringify(task.result, null, 2)}</pre> : null}
      {task?.error ? <p className="error-text">{task.error}</p> : null}
    </section>
  );
}
