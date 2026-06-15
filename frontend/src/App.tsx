import { Bot, History, Plug, Settings as SettingsIcon, TerminalSquare } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import {
  Approval,
  PluginManifest,
  Settings as SettingsType,
  Task,
  cancelTask,
  createTask,
  getSettings,
  getTask,
  listApprovals,
  listPlugins,
  listTasks,
  respondApproval,
  updateSettings
} from "./api/client";
import { ApprovalModal } from "./components/ApprovalModal";
import { ExecutionPanel } from "./components/ExecutionPanel";
import { PluginManager } from "./components/PluginManager";
import { Settings } from "./components/Settings";
import { SetupWizard } from "./components/SetupWizard";
import { TaskHistory } from "./components/TaskHistory";
import { TaskInput } from "./components/TaskInput";
import { useTaskStream } from "./hooks/useTaskStream";

type View = "workbench" | "history" | "plugins" | "settings";

export default function App() {
  const [settings, setSettings] = useState<SettingsType | null>(null);
  const [tasks, setTasks] = useState<Task[]>([]);
  const [currentTask, setCurrentTask] = useState<Task | null>(null);
  const [approvals, setApprovals] = useState<Approval[]>([]);
  const [plugins, setPlugins] = useState<PluginManifest[]>([]);
  const [view, setView] = useState<View>("workbench");
  const [busy, setBusy] = useState(false);
  const events = useTaskStream(currentTask?.task_id ?? null);

  const active = useMemo(() => currentTask && !["completed", "failed", "cancelled"].includes(currentTask.status), [currentTask]);

  async function refresh() {
    const [settingsBody, taskBody, approvalBody, pluginBody] = await Promise.all([
      getSettings(),
      listTasks(),
      listApprovals(),
      listPlugins()
    ]);
    setSettings(settingsBody);
    setTasks(taskBody);
    setApprovals(approvalBody);
    setPlugins(pluginBody);
    if (currentTask) {
      setCurrentTask(await getTask(currentTask.task_id));
    }
  }

  useEffect(() => {
    refresh().catch(console.error);
    const interval = window.setInterval(() => refresh().catch(console.error), 2500);
    return () => window.clearInterval(interval);
  }, []);

  async function handleSubmit(input: string) {
    setBusy(true);
    try {
      const created = await createTask(input);
      const task = await getTask(created.task_id);
      setCurrentTask(task);
      await refresh();
    } finally {
      setBusy(false);
    }
  }

  async function handleCancel() {
    if (!currentTask) {
      return;
    }
    const task = await cancelTask(currentTask.task_id);
    setCurrentTask(task);
    await refresh();
  }

  async function handleDecision(approvalId: string, decision: "approved" | "rejected") {
    await respondApproval(approvalId, decision);
    await refresh();
  }

  async function handleSettingsSave(next: Partial<SettingsType>) {
    setSettings(await updateSettings(next));
  }

  if (settings && !settings.setup_complete) {
    return <SetupWizard settings={settings} onComplete={refresh} />;
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <Bot size={26} />
          <span>Pilot</span>
        </div>
        <nav>
          <button className={view === "workbench" ? "active" : ""} onClick={() => setView("workbench")}>
            <TerminalSquare size={18} />
            Workbench
          </button>
          <button className={view === "history" ? "active" : ""} onClick={() => setView("history")}>
            <History size={18} />
            History
          </button>
          <button className={view === "plugins" ? "active" : ""} onClick={() => setView("plugins")}>
            <Plug size={18} />
            Plugins
          </button>
          <button className={view === "settings" ? "active" : ""} onClick={() => setView("settings")}>
            <SettingsIcon size={18} />
            Settings
          </button>
        </nav>
      </aside>
      <main>
        {view === "workbench" ? (
          <div className="workbench">
            <section className="panel command-panel">
              <div className="panel-heading">
                <h1>Run Task</h1>
                <span className="model-label">{settings?.ollama_model ?? "qwen2.5:7b"}</span>
              </div>
              <TaskInput busy={busy || Boolean(active)} onSubmit={handleSubmit} onCancel={handleCancel} />
            </section>
            <ExecutionPanel task={currentTask} events={events} />
          </div>
        ) : null}
        {view === "history" ? <TaskHistory tasks={tasks} onRefresh={refresh} onSelect={setCurrentTask} /> : null}
        {view === "plugins" ? <PluginManager plugins={plugins} /> : null}
        {view === "settings" ? <Settings settings={settings} onSave={handleSettingsSave} /> : null}
      </main>
      <ApprovalModal approvals={approvals} onDecision={handleDecision} />
    </div>
  );
}
