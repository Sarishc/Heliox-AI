"use client";

/**
 * Thin client wrapper that mounts the EventToastProvider once at the root.
 * Kept separate so layout.tsx stays a Server Component.
 */
import { EventToastProvider } from "@/components/EventToast";

export function EventProviders({ children }: { children: React.ReactNode }) {
  return (
    <>
      {children}
      <EventToastProvider />
    </>
  );
}
