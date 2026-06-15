import { AlertCircle, CheckCircle2, Clock3, ShieldAlert } from "lucide-react";
import { Task, TaskEvent } from "../api/client";

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
  return (
    <section className="panel execution-panel">
      <div className="panel-heading">
        <h2>Execution</h2>
        <span className={`status-pill ${task?.status ?? "idle"}`}>
          {(task?.status && statusIcon[task.status as keyof typeof statusIcon]) ?? <Clock3 size={17} />}
          {task?.status ?? "idle"}
        </span>
      </div>
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
