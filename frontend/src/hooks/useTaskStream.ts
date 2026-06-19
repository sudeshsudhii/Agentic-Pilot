import { useEffect, useState } from "react";
import { API_BASE, TaskEvent } from "../api/client";

export function useTaskStream(taskId: string | null) {
  const [events, setEvents] = useState<TaskEvent[]>([]);

  useEffect(() => {
    setEvents([]);
    if (!taskId) {
      return;
    }

    const source = new EventSource(`${API_BASE}/api/tasks/${taskId}/stream`);
    const appendEvent = (message: MessageEvent) => {
      const event = JSON.parse(message.data) as TaskEvent;
      setEvents((current) => {
        if (current.some((item) => item.id === event.id)) {
          return current;
        }
        return [...current, event];
      });
    };
    const closeAfterAppend = (message: MessageEvent) => {
      appendEvent(message);
      source.close();
    };
    source.onmessage = appendEvent;
    for (const name of [
      "queued",
      "started",
      "intent_parsed",
      "approval_required",
      "approval_approved",
      "approval_rejected",
      "BROWSER_LAUNCHED",
      "TAB_CREATED",
      "NAVIGATION_STARTED",
      "NAVIGATION_COMPLETED",
      "ACTION_CLICK",
      "ACTION_TYPE",
      "ACTION_SCROLL",
      "CURRENT_URL_CHANGED",
      "VERIFICATION_STARTED",
      "VERIFICATION_PASSED",
      "SCREENSHOT_TAKEN",
      "BROWSER_RETAINED",
      "BROWSER_CLOSED",
      "BROWSER_TIMEOUT"
    ]) {
      source.addEventListener(name, appendEvent);
    }
    source.addEventListener("completed", closeAfterAppend);
    source.addEventListener("failed", closeAfterAppend);
    source.addEventListener("cancelled", closeAfterAppend);

    return () => source.close();
  }, [taskId]);

  return events;
}
