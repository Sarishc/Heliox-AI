"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import {
  eventLabel,
  eventPath,
  eventSeverity,
  useEventStream,
  type HelioxEvent,
} from "@/hooks/useEventStream";
import { showEventToast } from "@/components/EventToast";

const SEVERITY_DOT: Record<string, string> = {
  high: "bg-red-500",
  medium: "bg-yellow-400",
  info: "bg-blue-400",
};

function timeAgo(iso: string): string {
  const diff = Date.now() - new Date(iso).getTime();
  const mins = Math.floor(diff / 60_000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hrs = Math.floor(mins / 60);
  if (hrs < 24) return `${hrs}h ago`;
  return `${Math.floor(hrs / 24)}d ago`;
}

function EventRow({
  event,
  onRead,
}: {
  event: HelioxEvent;
  onRead: (id: string) => void;
}) {
  const router = useRouter();
  const severity = eventSeverity(event);
  const dot = SEVERITY_DOT[severity] ?? SEVERITY_DOT.info;

  return (
    <button
      className={`w-full flex items-start gap-3 px-4 py-3 text-left hover:bg-white/5 transition-colors ${event.read ? "opacity-60" : ""}`}
      onClick={() => {
        onRead(event.event_id);
        router.push(eventPath(event));
      }}
    >
      <span className={`mt-1.5 h-2 w-2 flex-shrink-0 rounded-full ${dot}`} />
      <div className="flex-1 min-w-0">
        <p className="text-sm font-medium text-white truncate">
          {eventLabel(event)}
        </p>
        <p className="text-xs text-gray-400 mt-0.5">
          {timeAgo(event.timestamp)}
        </p>
      </div>
      {!event.read && (
        <span className="mt-1.5 h-1.5 w-1.5 flex-shrink-0 rounded-full bg-cyan-400" />
      )}
    </button>
  );
}

export function NotificationBell() {
  const [open, setOpen] = useState(false);
  const [pulse, setPulse] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  const { events, unreadCount, connected, markRead, markAllRead } =
    useEventStream({
      onEvent: (ev) => {
        showEventToast(ev);
        setPulse(true);
        setTimeout(() => setPulse(false), 1500);
      },
    });

  // Close dropdown on outside click
  useEffect(() => {
    function handleClick(e: MouseEvent) {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(e.target as Node)
      ) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClick);
    return () => document.removeEventListener("mousedown", handleClick);
  }, []);

  const displayEvents = events.slice(0, 10);

  return (
    <div className="relative" ref={dropdownRef}>
      {/* Bell button */}
      <button
        onClick={() => setOpen((v) => !v)}
        className="relative p-2 rounded-lg text-gray-400 hover:text-white hover:bg-white/10 transition-colors"
        aria-label={`Notifications${unreadCount > 0 ? ` (${unreadCount} unread)` : ""}`}
      >
        <svg
          className={`h-5 w-5 transition-transform ${pulse ? "scale-125" : "scale-100"}`}
          fill="none"
          viewBox="0 0 24 24"
          stroke="currentColor"
          strokeWidth={2}
        >
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            d="M15 17h5l-1.405-1.405A2.032 2.032 0 0118 14.158V11a6.002 6.002 0 00-4-5.659V5a2 2 0 10-4 0v.341C7.67 6.165 6 8.388 6 11v3.159c0 .538-.214 1.055-.595 1.436L4 17h5m6 0v1a3 3 0 11-6 0v-1m6 0H9"
          />
        </svg>

        {/* Unread badge */}
        {unreadCount > 0 && (
          <span className="absolute top-1 right-1 flex h-4 w-4 items-center justify-center rounded-full bg-red-500 text-[10px] font-bold text-white">
            {unreadCount > 9 ? "9+" : unreadCount}
          </span>
        )}

        {/* Connection indicator */}
        <span
          className={`absolute bottom-1.5 right-1.5 h-1.5 w-1.5 rounded-full ${connected ? "bg-green-400" : "bg-gray-500"}`}
          title={connected ? "Live" : "Reconnecting…"}
        />
      </button>

      {/* Dropdown */}
      {open && (
        <div className="absolute right-0 mt-2 w-80 rounded-xl border border-white/10 bg-gray-900 shadow-2xl z-50 overflow-hidden">
          {/* Header */}
          <div className="flex items-center justify-between px-4 py-3 border-b border-white/10">
            <div className="flex items-center gap-2">
              <h3 className="text-sm font-semibold text-white">
                Notifications
              </h3>
              <span
                className={`h-1.5 w-1.5 rounded-full ${connected ? "bg-green-400" : "bg-gray-500"}`}
                title={connected ? "Connected" : "Disconnected"}
              />
            </div>
            {unreadCount > 0 && (
              <button
                onClick={markAllRead}
                className="text-xs text-cyan-400 hover:text-cyan-300 transition-colors"
              >
                Mark all read
              </button>
            )}
          </div>

          {/* Event list */}
          <div className="max-h-80 overflow-y-auto">
            {displayEvents.length === 0 ? (
              <p className="px-4 py-6 text-sm text-gray-500 text-center">
                No notifications yet.
                <br />
                <span className="text-xs text-gray-600">
                  Anomalies, budget alerts, and sync completions will appear
                  here.
                </span>
              </p>
            ) : (
              displayEvents.map((ev) => (
                <EventRow key={ev.event_id} event={ev} onRead={markRead} />
              ))
            )}
          </div>

          {/* Footer */}
          {events.length > 10 && (
            <div className="border-t border-white/10 px-4 py-2">
              <p className="text-xs text-gray-500 text-center">
                Showing 10 of {events.length} notifications
              </p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
