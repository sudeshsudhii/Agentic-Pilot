import { Save } from "lucide-react";
import { FormEvent, useEffect, useState } from "react";
import { Settings as SettingsType } from "../api/client";

type Props = {
  settings: SettingsType | null;
  onSave: (settings: Partial<SettingsType>) => Promise<void>;
};

export function Settings({ settings, onSave }: Props) {
  const [model, setModel] = useState(settings?.ollama_model ?? "qwen2.5:7b");
  const [autoApprove, setAutoApprove] = useState(settings?.auto_approve_low_risk ?? true);

  useEffect(() => {
    if (settings) {
      setModel(settings.ollama_model);
      setAutoApprove(settings.auto_approve_low_risk);
    }
  }, [settings]);

  async function handleSubmit(event: FormEvent) {
    event.preventDefault();
    await onSave({ ollama_model: model, auto_approve_low_risk: autoApprove });
  }

  return (
    <section className="panel">
      <div className="panel-heading">
        <h2>Settings</h2>
      </div>
      <form className="settings-form" onSubmit={handleSubmit}>
        <label>
          <span>Model</span>
          <input value={model} onChange={(event) => setModel(event.target.value)} />
        </label>
        <label className="toggle-row">
          <input type="checkbox" checked={autoApprove} onChange={(event) => setAutoApprove(event.target.checked)} />
          <span>Auto-approve low risk tasks</span>
        </label>
        <button className="primary-button" type="submit">
          <Save size={17} />
          Save
        </button>
      </form>
    </section>
  );
}
