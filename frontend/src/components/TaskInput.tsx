import { Send, Square } from "lucide-react";
import { FormEvent, useState } from "react";

type Props = {
  busy: boolean;
  onSubmit: (input: string) => Promise<void>;
  onCancel?: () => Promise<void>;
};

export function TaskInput({ busy, onSubmit, onCancel }: Props) {
  const [input, setInput] = useState("");

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    const value = input.trim();
    if (!value) {
      return;
    }
    setInput("");
    await onSubmit(value);
  }

  return (
    <form className="task-input" onSubmit={handleSubmit}>
      <textarea
        value={input}
        onChange={(event) => setInput(event.target.value)}
        placeholder="Search Google for latest AI agent news"
        rows={3}
      />
      <div className="task-actions">
        {busy && onCancel ? (
          <button className="icon-button danger" type="button" onClick={onCancel} aria-label="Cancel task">
            <Square size={18} />
          </button>
        ) : null}
        <button className="primary-button" type="submit" disabled={busy || !input.trim()}>
          <Send size={18} />
          Run
        </button>
      </div>
    </form>
  );
}
