"use client";

import { useCallback, useEffect, useRef, useState } from "react";

export type EventSeverity = "high" | "medium" | "low" | "info";

export interface HelioxEvent {
  event_id: string;
  event_type: string;
  team_id: string;
  payload: Record<string, unknown>;
  timestamp: string;
  read: boolean;
}

export type EventHandler = (event: HelioxEvent) => void;

interface UseEventStreamOptions {
  /** Called for every new event before it is added to the events list. */
  onEvent?: EventHandler;
  /** Max events to keep in memory. Default: 50. */
  maxEvents?: number;
}

interface UseEventStreamReturn {
  events: HelioxEvent[];
  unreadCount: number;
  connected: boolean;
  markRead: (eventId: string) => Promise<void>;
  markAllRead: () => Promise<void>;
  clearEvents: () => void;
}

const SSE_URL = "/api/v1/events/stream";
const RECENT_URL = "/api/v1/events/recent";
const READ_URL = (id: string) => `/api/v1/events/${id}/read`;

/** Route event_type → action path for click-through navigation. */
export function eventPath(event: HelioxEvent): string {
  const t = event.event_type;
  if (t === "anomaly.detected" || t === "cost.spike") return "/alerts";
  if (t.startsWith("budget.")) return "/budgets";
  if (t.startsWith("sync.")) return "/settings/integrations";
  if (t === "inference.alert") return "/optimization";
  return "/";
}

export function eventLabel(event: HelioxEvent): string {
  const map: Record<string, string> = {
    "anomaly.detected": "Anomaly detected",
    "budget.warning": "Budget warning",
    "budget.breach": "Budget breached",
    "sync.completed": "Sync completed",
    "sync.failed": "Sync failed",
    "cost.spike": "Cost spike",
    "inference.alert": "Inference cost alert",
  };
  return map[event.event_type] ?? event.event_type;
}

export function eventSeverity(event: HelioxEvent): EventSeverity {
  if (
    event.event_type === "budget.breach" ||
    event.event_type === "anomaly.detected"
  )
    return "high";
  if (
    event.event_type === "budget.warning" ||
    event.event_type === "cost.spike" ||
    event.event_type === "inference.alert"
  )
    return "medium";
  if (event.event_type === "sync.failed") return "medium";
  return "info";
}

export function useEventStream({
  onEvent,
  maxEvents = 50,
}: UseEventStreamOptions = {}): UseEventStreamReturn {
  const [events, setEvents] = useState<HelioxEvent[]>([]);
  const [unreadCount, setUnreadCount] = useState(0);
  const [connected, setConnected] = useState(false);
  const esRef = useRef<EventSource | null>(null);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  // Load recent events from REST endpoint on mount
  useEffect(() => {
    fetch(RECENT_URL, { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data) => {
        if (data?.events) {
          setEvents(data.events.slice(0, maxEvents));
          setUnreadCount(data.unread_count ?? 0);
        }
      })
      .catch(() => {});
  }, [maxEvents]);

  // SSE connection
  useEffect(() => {
    let es: EventSource;

    function connect() {
      es = new EventSource(SSE_URL, { withCredentials: true });
      esRef.current = es;

      es.onopen = () => setConnected(true);

      es.onerror = () => {
        setConnected(false);
        // EventSource auto-reconnects; just update the connected state
      };

      // Handle all event types via a generic message listener
      const EVENT_TYPES = [
        "anomaly.detected",
        "budget.warning",
        "budget.breach",
        "sync.completed",
        "sync.failed",
        "cost.spike",
        "inference.alert",
      ];

      EVENT_TYPES.forEach((type) => {
        es.addEventListener(type, (e: MessageEvent) => {
          try {
            const payload = JSON.parse(e.data) as HelioxEvent;
            const ev: HelioxEvent = {
              ...payload,
              read: false,
            };

            setEvents((prev) => [ev, ...prev].slice(0, maxEvents));
            setUnreadCount((n) => n + 1);
            onEventRef.current?.(ev);
          } catch {
            // ignore malformed events
          }
        });
      });
    }

    connect();

    return () => {
      esRef.current?.close();
      esRef.current = null;
      setConnected(false);
    };
  }, [maxEvents]);

  const markRead = useCallback(async (eventId: string) => {
    try {
      await fetch(READ_URL(eventId), {
        method: "POST",
        credentials: "include",
      });
    } catch {
      // non-fatal
    }
    setEvents((prev) =>
      prev.map((e) => (e.event_id === eventId ? { ...e, read: true } : e))
    );
    setUnreadCount((n) => Math.max(0, n - 1));
  }, []);

  const markAllRead = useCallback(async () => {
    const unread = events.filter((e) => !e.read);
    await Promise.allSettled(
      unread.map((e) =>
        fetch(READ_URL(e.event_id), { method: "POST", credentials: "include" })
      )
    );
    setEvents((prev) => prev.map((e) => ({ ...e, read: true })));
    setUnreadCount(0);
  }, [events]);

  const clearEvents = useCallback(() => {
    setEvents([]);
    setUnreadCount(0);
  }, []);

  return { events, unreadCount, connected, markRead, markAllRead, clearEvents };
}
