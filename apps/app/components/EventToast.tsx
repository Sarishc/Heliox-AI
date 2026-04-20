"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  eventLabel,
  eventPath,
  eventSeverity,
  type HelioxEvent,
} from "@/hooks/useEventStream";

interface ToastItem {
  event: HelioxEvent;
  id: string;
}

interface EventToastProps {
  event: HelioxEvent | null;
}

const SEVERITY_STYLES: Record<string, string> = {
  high: "border-l-4 border-red-500 bg-red-950/80",
  medium: "border-l-4 border-yellow-500 bg-yellow-950/80",
  info: "border-l-4 border-blue-500 bg-blue-950/80",
};

const SEVERITY_ICON: Record<string, string> = {
  high: "🔴",
  medium: "🟡",
  info: "🔵",
};

function getToastMessage(event: HelioxEvent): string {
  const p = event.payload;
  switch (event.event_type) {
    case "anomaly.detected":
      return (p.message as string) || "Cost anomaly detected.";
    case "budget.warning":
      return `Budget at ${p.percent_used ?? ""}% — $${p.mtd_spend_usd ?? ""} of $${p.budget_usd ?? ""}`;
    case "budget.breach":
      return `Budget BREACHED at ${p.percent_used ?? ""}%`;
    case "sync.completed":
      return `${p.provider ?? "Integration"} sync completed (${p.records_saved ?? 0} records)`;
    case "sync.failed":
      return `${p.provider ?? "Integration"} sync failed`;
    case "inference.alert":
      return `${p.model_name ?? "Model"} cost spike: ${p.multiple ?? ""}x baseline`;
    default:
      return eventLabel(event);
  }
}

/** Single toast item — auto-dismisses after 5 s. */
function Toast({
  item,
  onDismiss,
}: {
  item: ToastItem;
  onDismiss: (id: string) => void;
}) {
  const router = useRouter();
  const severity = eventSeverity(item.event);
  const styles = SEVERITY_STYLES[severity] ?? SEVERITY_STYLES.info;
  const icon = SEVERITY_ICON[severity] ?? "🔵";
  const path = eventPath(item.event);

  useEffect(() => {
    const t = setTimeout(() => onDismiss(item.id), 5000);
    return () => clearTimeout(t);
  }, [item.id, onDismiss]);

  return (
    <div
      className={`relative flex items-start gap-3 rounded-lg px-4 py-3 shadow-lg backdrop-blur-sm cursor-pointer transition-all duration-300 animate-slide-in ${styles}`}
      onClick={() => {
        onDismiss(item.id);
        router.push(path);
      }}
      role="alert"
    >
      <span className="text-base leading-5 mt-0.5">{icon}</span>
      <div className="flex-1 min-w-0">
        <p className="text-sm font-semibold text-white leading-5">
          {eventLabel(item.event)}
        </p>
        <p className="text-xs text-gray-300 mt-0.5 truncate">
          {getToastMessage(item.event)}
        </p>
      </div>
      <button
        onClick={(e) => {
          e.stopPropagation();
          onDismiss(item.id);
        }}
        className="ml-1 text-gray-400 hover:text-white transition-colors text-lg leading-none"
        aria-label="Dismiss"
      >
        ×
      </button>
    </div>
  );
}

/**
 * EventToastProvider — renders a toast stack in the top-right corner.
 *
 * Usage: render once near the top of the layout, then call the exported
 * `showEventToast(event)` singleton from anywhere.
 */
let _showToast: ((event: HelioxEvent) => void) | null = null;

export function showEventToast(event: HelioxEvent): void {
  _showToast?.(event);
}

export function EventToastProvider() {
  const [toasts, setToasts] = useState<ToastItem[]>([]);

  useEffect(() => {
    _showToast = (event: HelioxEvent) => {
      const id = `toast-${Date.now()}-${Math.random()}`;
      setToasts((prev) => [...prev.slice(-4), { event, id }]);
    };
    return () => {
      _showToast = null;
    };
  }, []);

  const dismiss = (id: string) =>
    setToasts((prev) => prev.filter((t) => t.id !== id));

  if (toasts.length === 0) return null;

  return (
    <div
      className="fixed top-4 right-4 z-50 flex flex-col gap-2 w-80 max-w-[calc(100vw-2rem)]"
      aria-live="polite"
    >
      {toasts.map((item) => (
        <Toast key={item.id} item={item} onDismiss={dismiss} />
      ))}
    </div>
  );
}
