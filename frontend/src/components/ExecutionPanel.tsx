import { AlertCircle, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { API_BASE, Task, TaskEvent } from "../api/client";

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
      else if (latestEvent.type === "completed") browserState = "Completed";
  }

  return (
    <section className="panel execution-panel">
      <div className="panel-heading">
        <h2>Execution</h2>
        <span className={`status-pill ${task?.status ?? "idle"}`}>
          {(task?.status && statusIcon[task.status as keyof typeof statusIcon]) ?? <Clock3 size={17} />}
          {task?.status ?? "idle"}
        </span>
      </div>
      
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
