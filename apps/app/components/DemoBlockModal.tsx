"use client";

import { useEffect, useRef } from "react";

interface DemoBlockModalProps {
  open: boolean;
  onClose: () => void;
  signupUrl?: string;
}

/**
 * Modal shown when a demo user hits a 403 demo_mode error on a write action.
 * Two CTAs: "Sign up free" (primary) and "Maybe later" (dismiss).
 */
export function DemoBlockModal({
  open,
  onClose,
  signupUrl = "https://app.heliox.ai/signup",
}: DemoBlockModalProps) {
  const primaryRef = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    if (open) primaryRef.current?.focus();
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open, onClose]);

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-labelledby="demo-block-title"
      style={{
        position: "fixed",
        inset: 0,
        zIndex: 10000,
        display: "flex",
        alignItems: "center",
        justifyContent: "center",
        padding: "1rem",
      }}
    >
      {/* Backdrop */}
      <div
        onClick={onClose}
        style={{
          position: "absolute",
          inset: 0,
          background: "rgba(0,0,0,0.5)",
          backdropFilter: "blur(2px)",
        }}
        aria-hidden="true"
      />

      {/* Card */}
      <div
        style={{
          position: "relative",
          background: "#fff",
          borderRadius: "0.75rem",
          padding: "2rem",
          maxWidth: "420px",
          width: "100%",
          boxShadow: "0 20px 60px rgba(0,0,0,0.2)",
          textAlign: "center",
        }}
      >
        {/* Icon */}
        <div
          style={{
            width: "3.5rem",
            height: "3.5rem",
            borderRadius: "50%",
            background: "linear-gradient(135deg, #7c3aed 0%, #4f46e5 100%)",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            margin: "0 auto 1.25rem",
            fontSize: "1.5rem",
          }}
        >
          🔒
        </div>

        <h2
          id="demo-block-title"
          style={{
            fontSize: "1.2rem",
            fontWeight: 700,
            color: "#111",
            marginBottom: "0.75rem",
          }}
        >
          This is disabled in the demo
        </h2>

        <p style={{ color: "#555", fontSize: "0.9rem", lineHeight: 1.6, marginBottom: "1.75rem" }}>
          Create a free account to connect your cluster, configure alerts, and
          start tracking real GPU costs.
        </p>

        <div style={{ display: "flex", flexDirection: "column", gap: "0.75rem" }}>
          <a
            ref={primaryRef}
            href={signupUrl}
            target="_blank"
            rel="noopener noreferrer"
            style={{
              display: "block",
              background: "linear-gradient(90deg, #7c3aed 0%, #4f46e5 100%)",
              color: "#fff",
              borderRadius: "0.5rem",
              padding: "0.75rem 1rem",
              fontWeight: 700,
              fontSize: "0.95rem",
              textDecoration: "none",
              transition: "opacity 0.15s",
            }}
            onMouseOver={(e) => (e.currentTarget.style.opacity = "0.88")}
            onMouseOut={(e) => (e.currentTarget.style.opacity = "1")}
          >
            Sign up free →
          </a>

          <button
            onClick={onClose}
            style={{
              background: "transparent",
              border: "1px solid #e5e7eb",
              borderRadius: "0.5rem",
              padding: "0.7rem 1rem",
              color: "#555",
              fontSize: "0.9rem",
              cursor: "pointer",
              fontWeight: 500,
            }}
          >
            Maybe later
          </button>
        </div>
      </div>
    </div>
  );
}
