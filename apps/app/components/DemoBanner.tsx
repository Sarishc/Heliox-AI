"use client";

import { useEffect, useState } from "react";
import { getApiUrl } from "@/lib/api";

interface DemoStatus {
  is_demo: boolean;
  demo_user_email?: string;
  demo_password?: string;
  expires_at?: string;
  signup_url?: string;
}

/**
 * Persistent top banner shown when the app is running in demo mode.
 * Non-dismissable. Calls GET /api/v1/demo/status on mount.
 */
export function DemoBanner() {
  const [status, setStatus] = useState<DemoStatus | null>(null);

  useEffect(() => {
    fetch(getApiUrl("/api/v1/demo/status"), { credentials: "include" })
      .then((r) => (r.ok ? r.json() : null))
      .then((data: DemoStatus | null) => {
        if (data?.is_demo) setStatus(data);
      })
      .catch(() => {});
  }, []);

  if (!status?.is_demo) return null;

  const signupUrl = status.signup_url ?? "https://app.heliox.ai/signup";

  return (
    <div
      role="banner"
      aria-label="Demo environment notice"
      style={{
        position: "fixed",
        top: 0,
        left: 0,
        right: 0,
        zIndex: 9999,
        background: "linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%)",
        color: "#fff",
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        gap: "1.25rem",
        padding: "0.55rem 1rem",
        fontSize: "0.875rem",
        fontWeight: 500,
        letterSpacing: "0.01em",
        boxShadow: "0 2px 8px rgba(0,0,0,0.18)",
      }}
    >
      <span>
        You&apos;re exploring a live demo — data resets daily
      </span>
      {status.demo_user_email && (
        <span style={{ opacity: 0.8, fontSize: "0.8rem" }}>
          Login: <strong>{status.demo_user_email}</strong> / <strong>{status.demo_password}</strong>
        </span>
      )}
      <a
        href={signupUrl}
        target="_blank"
        rel="noopener noreferrer"
        style={{
          background: "#fff",
          color: "#4f46e5",
          borderRadius: "0.375rem",
          padding: "0.3rem 0.9rem",
          fontWeight: 700,
          fontSize: "0.82rem",
          textDecoration: "none",
          whiteSpace: "nowrap",
          transition: "opacity 0.15s",
        }}
        onMouseOver={(e) => (e.currentTarget.style.opacity = "0.85")}
        onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
      >
        Sign up free →
      </a>
    </div>
  );
}

/** Height reserved for the demo banner so page content doesn't overlap. */
export const DEMO_BANNER_HEIGHT = "2.5rem";
