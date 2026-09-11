import React, { useEffect, useState, useRef, useCallback } from "react";
import { Header } from "./components/Header";
import { ModelRouterPanel } from "./components/ModelRouterPanel";
import { TaskPlanPanel } from "./components/TaskPlanPanel";
import { ObservationPanel } from "./components/ObservationPanel";
import { VisionObservabilityPanel } from "./components/VisionObservabilityPanel";
import { DecisionActionPanel } from "./components/DecisionActionPanel";
import { VerificationPanel } from "./components/VerificationPanel";
import { BlockedAlertBanner } from "./components/BlockedAlertBanner";
import { PerformancePanel } from "./components/PerformancePanel";
import { TimelineTrace } from "./components/TimelineTrace";
import { RunHistoryView } from "./components/RunHistoryView";
import { ExperienceView } from "./components/ExperienceView";
import { LangGraphStateView } from "./components/LangGraphStateView";
import { ObservatoryEvent, PerformanceMetrics, SystemStatus } from "./types";

class ErrorBoundary extends React.Component<{ children: React.ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error };
  }

  componentDidCatch(error: Error, errorInfo: any) {
    console.error("Observatory ErrorBoundary caught error:", error, errorInfo);
  }

  render() {
    if (this.state.hasError) {
      return (
        <div className="obs-card p-6 border-rose-500/30 bg-rose-950/20 text-slate-200 m-6 flex flex-col gap-3">
          <h2 className="text-base font-bold text-rose-400 font-mono">Telemetry Render Error Recovered</h2>
          <p className="text-xs text-slate-300">An unexpected data format occurred while rendering telemetry panels:</p>
          <pre className="bg-black/50 p-3 rounded text-rose-300 text-xs font-mono overflow-auto">
            {this.state.error?.message}
          </pre>
          <button
            onClick={() => this.setState({ hasError: false, error: null })}
            className="btn-action w-fit text-xs mt-2"
          >
            Reset Dashboard
          </button>
        </div>
      );
    }
    return this.props.children;
  }
}

export const App: React.FC = () => {
  const [activeTab, setActiveTab] = useState<string>("live");
  const [activeRunId, setActiveRunId] = useState<string | null>(null);
  const [taskTitle, setTaskTitle] = useState<string>("");
  const [events, setEvents] = useState<ObservatoryEvent[]>([]);
  const [status, setStatus] = useState<SystemStatus>({
    pilot_backend_connected: false,
    event_stream_connected: false,
    last_event_timestamp: null,
    last_event_age_sec: null,
    active_run_id: null,
    event_buffer_size: 0,
  });

  const [metrics, setMetrics] = useState<PerformanceMetrics>({
    total_duration_sec: 0,
    planner_duration_sec: 0,
    vision_duration_sec: 0,
    browser_duration_sec: 0,
    verification_duration_sec: 0,
    waiting_duration_sec: 0,
    retry_duration_sec: 0,
    model_latencies: [],
  });

  const wsRef = useRef<WebSocket | null>(null);
  const reconnectTimeoutRef = useRef<any>(null);
  const backoffRef = useRef<number>(1000);

  // Poll system status and metrics every 5s with equality check to prevent needless re-renders
  const fetchStatus = useCallback(async () => {
    try {
      const res = await fetch("/api/status");
      if (res.ok) {
        const data: SystemStatus = await res.json();
        setStatus((prev) => {
          if (
            prev.pilot_backend_connected === data.pilot_backend_connected &&
            prev.event_stream_connected === data.event_stream_connected &&
            prev.active_run_id === data.active_run_id &&
            prev.event_buffer_size === data.event_buffer_size &&
            prev.last_event_timestamp === data.last_event_timestamp &&
            Math.abs((prev.last_event_age_sec ?? 0) - (data.last_event_age_sec ?? 0)) < 1
          ) {
            return prev;
          }
          return data;
        });
        if (data.active_run_id && !activeRunId) {
          setActiveRunId(data.active_run_id);
        }
      }
    } catch {
      setStatus((prev) => {
        if (!prev.pilot_backend_connected && !prev.event_stream_connected) {
          return prev;
        }
        return {
          ...prev,
          pilot_backend_connected: false,
          event_stream_connected: false,
        };
      });
    }
  }, [activeRunId]);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000);
    return () => clearInterval(interval);
  }, [fetchStatus]);

  // Fetch performance metrics when runId changes
  useEffect(() => {
    if (!activeRunId) return;
    const fetchPerf = async () => {
      try {
        const res = await fetch(`/api/runs/${activeRunId}/performance`);
        if (res.ok) {
          const p: PerformanceMetrics = await res.json();
          setMetrics((prev) => {
            if (
              prev.total_duration_sec === p.total_duration_sec &&
              prev.planner_duration_sec === p.planner_duration_sec &&
              prev.vision_duration_sec === p.vision_duration_sec &&
              prev.browser_duration_sec === p.browser_duration_sec &&
              prev.model_latencies.length === p.model_latencies.length
            ) {
              return prev;
            }
            return p;
          });
        }
      } catch {}
    };
    fetchPerf();
  }, [activeRunId, events.length]);

  // Connect WebSocket to Observatory Backend directly on port 8766 to avoid Vite proxy drops
  const connectWebSocket = useCallback(() => {
    if (reconnectTimeoutRef.current) {
      clearTimeout(reconnectTimeoutRef.current);
      reconnectTimeoutRef.current = null;
    }
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.close();
      wsRef.current = null;
    }

    const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
    const hostname = window.location.hostname || "127.0.0.1";
    // Connect directly to Observatory backend on 8766 in dev to bypass Vite proxy disconnects
    const wsUrl =
      window.location.port === "3001" || hostname === "localhost" || hostname === "127.0.0.1"
        ? `${proto}//${hostname}:8766/ws`
        : `${proto}//${window.location.host}/ws`;

    try {
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;
      let pingTimer: any = null;

      ws.onopen = () => {
        if (wsRef.current !== ws) return;
        backoffRef.current = 1000;
        setStatus((s) => ({ ...s, event_stream_connected: true, pilot_backend_connected: true }));
        // Keepalive ping every 10s
        pingTimer = setInterval(() => {
          if (ws.readyState === WebSocket.OPEN) {
            try {
              ws.send("ping");
            } catch {}
          }
        }, 10000);
      };

      ws.onmessage = (event) => {
        try {
          if (event.data === "pong" || event.data === '{"type":"pong"}' || event.data === '{"type": "pong"}') {
            return;
          }
          const data = JSON.parse(event.data);
          if (data.type === "pong") return;

          if (data.event_type || data.event_id) {
            const obsEvent: ObservatoryEvent = {
              event_id: String(data.event_id || Date.now()),
              run_id: String(data.run_id || data.task_id || "unknown"),
              task_id: String(data.task_id || data.run_id || "unknown"),
              timestamp: data.timestamp || new Date().toISOString(),
              event_type: data.event_type || "UNKNOWN",
              status: data.status || "running",
              step_index: data.step_index || 0,
              message: data.message || "",
              metadata: data.metadata || {},
            };

            setEvents((prev) => {
              // Avoid duplicate event_id
              if (prev.some((e) => e.event_id === obsEvent.event_id)) {
                return prev;
              }
              return [...prev, obsEvent];
            });

            // If task started or run changed
            if (obsEvent.event_type === "TASK_STARTED") {
              setActiveRunId(obsEvent.run_id);
              if (obsEvent.metadata?.input_text) {
                setTaskTitle(obsEvent.metadata.input_text);
              }
            } else if (obsEvent.run_id && obsEvent.run_id !== "unknown") {
              setActiveRunId((cur) => cur || obsEvent.run_id);
            }
          }
        } catch {}
      };

      ws.onclose = () => {
        if (pingTimer) clearInterval(pingTimer);
        if (wsRef.current !== ws) return;
        setStatus((s) => ({ ...s, event_stream_connected: false }));
        // Exponential backoff reconnect
        reconnectTimeoutRef.current = setTimeout(() => {
          if (wsRef.current === ws || !wsRef.current) {
            backoffRef.current = Math.min(8000, backoffRef.current * 1.5);
            connectWebSocket();
          }
        }, backoffRef.current);
      };

      ws.onerror = () => {
        if (pingTimer) clearInterval(pingTimer);
        if (wsRef.current !== ws) return;
        ws.close();
      };
    } catch {
      setStatus((s) => ({ ...s, event_stream_connected: false }));
    }
  }, []);

  useEffect(() => {
    connectWebSocket();
    return () => {
      if (reconnectTimeoutRef.current) clearTimeout(reconnectTimeoutRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;
        wsRef.current.onerror = null;
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [connectWebSocket]);

  // Load specific historical run
  const handleSelectRun = async (runId: string) => {
    try {
      const res = await fetch(`/api/runs/${runId}`);
      if (res.ok) {
        const data = await res.json();
        setActiveRunId(runId);
        setEvents(data.events || []);
        if (data.performance) setMetrics(data.performance);
        if (data.state?.input_text) setTaskTitle(data.state.input_text);
        setActiveTab("live");
      }
    } catch (err) {
      console.error("Failed to load run details:", err);
    }
  };

  return (
    <div className="min-h-screen flex flex-col bg-[#0a0d14] text-slate-100 pb-12">
      <Header
        status={status}
        activeTab={activeTab}
        setActiveTab={setActiveTab}
        activeRunId={activeRunId}
        taskTitle={taskTitle}
        onReconnect={connectWebSocket}
      />

      <main className="max-w-[1700px] mx-auto w-full px-6 py-5 flex-1 flex flex-col gap-5">
        <ErrorBoundary>
          {activeTab === "live" && (
            <>
              <BlockedAlertBanner events={events} />

              {/* Top Row: Model Router & Task Plan */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <ModelRouterPanel events={events} />
                <TaskPlanPanel events={events} />
              </div>

              {/* Middle Row: Observation & Vision */}
              <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">
                <ObservationPanel events={events} activeRunId={activeRunId} />
                <div className="flex flex-col gap-5">
                  <VisionObservabilityPanel events={events} />
                  <PerformancePanel metrics={metrics} />
                </div>
              </div>

              {/* Decision & Action */}
              <DecisionActionPanel events={events} />

              {/* Verification */}
              <VerificationPanel events={events} />

              {/* Live Trace Timeline */}
              <TimelineTrace events={events} />
            </>
          )}

          {activeTab === "history" && <RunHistoryView onSelectRun={handleSelectRun} />}

          {activeTab === "experiences" && <ExperienceView />}

          {activeTab === "langgraph" && <LangGraphStateView activeRunId={activeRunId} />}
        </ErrorBoundary>
      </main>
    </div>
  );
};
