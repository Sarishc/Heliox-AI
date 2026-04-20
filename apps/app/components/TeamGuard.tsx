"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { fetchJson } from "@/lib/api";

interface MeResponse {
  team_id: string;
  role: string;
  feature_flags?: Record<string, boolean>;
}

const PUBLIC_PATHS = ["/login", "/signup", "/onboarding"];

export function TeamGuard({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (typeof window === "undefined") return;
    if (PUBLIC_PATHS.some((p) => pathname?.startsWith(p))) {
      setReady(true);
      return;
    }

    // NOTE: demo mode (heliox_demo_mode localStorage flag) only controls which
    // DATA is displayed (demo data vs real data). It does NOT bypass authentication.
    // All protected routes must still pass the /api/v1/me check regardless of demo mode.

    let cancelled = false;
    fetchJson<MeResponse>("/api/v1/me", { skipAuthRedirect: true })
      .then((me) => {
        if (cancelled) return;
        if (!me.team_id) {
          window.location.href = "/onboarding";
          return;
        }
        setReady(true);
      })
      .catch(() => {
        if (cancelled) return;
        // Not authenticated — redirect to login
        if (window.location.pathname !== "/login") {
          window.location.href = `/login?redirect=${encodeURIComponent(window.location.pathname)}`;
        }
      });

    return () => {
      cancelled = true;
    };
  }, [pathname]);

  if (!ready) {
    return (
      <div className="min-h-screen flex items-center justify-center">
        <div className="animate-spin rounded-full h-12 w-12 border-b-2 border-blue-600" />
      </div>
    );
  }

  return <>{children}</>;
}
