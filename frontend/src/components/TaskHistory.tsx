import { History, RefreshCw } from "lucide-react";
import { Task } from "../api/client";

type Props = {
  tasks: Task[];
  onRefresh: () => Promise<void>;
  onSelect: (task: Task) => void;
};

export function TaskHistory({ tasks, onRefresh, onSelect }: Props) {
  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>History</h2>
        <button className="icon-button" aria-label="Refresh history" onClick={onRefresh}>
          <RefreshCw size={17} />
        </button>
      </div>
      <div className="history-list">
        {tasks.length === 0 ? (
          <p className="muted">No tasks yet.</p>
        ) : (
          tasks.map((task) => (
            <button className="history-item" key={task.task_id} onClick={() => onSelect(task)}>
              <History size={16} />
              <span>{task.input_text}</span>
              <strong>{task.status}</strong>
            </button>
          ))
        )}
      </div>
    </section>
  );
}
