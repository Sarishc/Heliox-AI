"use client";

import { useEffect, useState } from "react";
import { fetchJson } from "@/lib/api";

interface BudgetEvent {
  id: string;
  date: string;
  threshold: number;
  spend_usd: number;
  budget_usd: number;
  predicted_breach_date?: string | null;
  delivered_via: string;
}

export default function BudgetEventsList() {
  const [events, setEvents] = useState<BudgetEvent[]>([]);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const load = async () => {
      try {
        const response = await fetchJson<BudgetEvent[]>("/api/v1/budgets/events?limit=20");
        setEvents(response);
      } catch (err) {
        setError(err instanceof Error ? err.message : "Unable to load budget events.");
      }
    };
    load();
  }, []);

  return (
    <div className="rounded-2xl border border-slate-200 bg-white p-5 shadow-sm">
      <h3 className="text-lg font-semibold text-slate-900">Recent budget events</h3>
      <p className="text-sm text-slate-500 mt-1">
        Threshold crossings and delivery status for the current month.
      </p>

      {error ? (
        <p className="mt-4 text-sm text-rose-600">{error}</p>
      ) : events.length === 0 ? (
        <p className="mt-4 text-sm text-slate-500">No budget events yet.</p>
      ) : (
        <div className="mt-4 space-y-3 text-sm text-slate-600">
          {events.map((event) => (
            <div
              key={event.id}
              className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-slate-100 bg-slate-50 px-3 py-2"
            >
              <div>
                <span className="font-semibold text-slate-900">
                  {(event.threshold * 100).toFixed(0)}% threshold
                </span>
                <span className="ml-2 text-xs text-slate-500">{event.date}</span>
              </div>
              <div>
                ${event.spend_usd.toLocaleString()} / $
                {event.budget_usd.toLocaleString()}
              </div>
              <div className="text-xs text-slate-500">
                Slack: {event.delivered_via}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
