"use client";

/**
 * Enterprise Topbar — Top 0.1% Design
 * Stripe / Linear / Vercel inspired
 */

import { useState } from "react";
import { Search, Bell, ChevronDown, Moon, Sun, Menu, LogOut } from "lucide-react";
import { fetchJson } from "@/lib/api";
import { Button } from "../ui/Button";
import { DemoModeToggle } from "../ui/DemoModeToggle";

interface TopbarProps {
  teamName?: string;
  onMenuClick?: () => void;
}

export function Topbar({ teamName = "Demo Team", onMenuClick }: TopbarProps) {
  const [darkMode, setDarkMode] = useState(false);
  const [userOpen, setUserOpen] = useState(false);

  const handleLogout = async () => {
    setUserOpen(false);
    try {
      await fetchJson("/api/v1/auth/logout", { method: "POST" });
    } catch {
      // ignore
    }
    window.location.href = "/login";
  };

  const toggleDarkMode = () => {
    setDarkMode(!darkMode);
    document.documentElement.classList.toggle("dark");
  };

  return (
    <header
      className="sticky top-0 z-40 w-full"
      style={{
        background: "rgba(246,248,252,0.85)",
        backdropFilter: "blur(12px)",
        WebkitBackdropFilter: "blur(12px)",
        borderBottom: "1px solid var(--border)",
      }}
    >
      <div className="flex h-14 items-center justify-between gap-4 px-6">

        {/* ── Left: mobile menu + search ────────────── */}
        <div className="flex flex-1 items-center gap-3">
          <button
            onClick={onMenuClick}
            className="lg:hidden rounded-lg p-1.5 text-muted-foreground transition-colors hover:bg-muted"
          >
            <Menu className="h-5 w-5" />
          </button>

          {/* Search bar */}
          <div className="relative w-full max-w-[320px]">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2"
              style={{ color: "var(--heliox-text-muted)" }}
            />
            <input
              type="text"
              placeholder="Search or jump to…"
              className="w-full rounded-xl py-2 pl-9 pr-10 text-[13px] outline-none transition-all duration-150"
              style={{
                background: "var(--card)",
                border: "1px solid var(--border)",
                color: "var(--foreground)",
                boxShadow: "var(--shadow-xs)",
              }}
              onFocus={(e) => {
                (e.target as HTMLInputElement).style.borderColor = "#6366f1";
                (e.target as HTMLInputElement).style.boxShadow =
                  "0 0 0 3px rgba(99,102,241,0.12)";
              }}
              onBlur={(e) => {
                (e.target as HTMLInputElement).style.borderColor = "var(--border)";
                (e.target as HTMLInputElement).style.boxShadow = "var(--shadow-xs)";
              }}
            />
            <kbd
              className="pointer-events-none absolute right-3 top-1/2 -translate-y-1/2 rounded-md px-1.5 py-0.5 text-[10px] font-medium"
              style={{
                background: "var(--muted)",
                color: "var(--muted-foreground)",
                border: "1px solid var(--border)",
              }}
            >
              ⌘K
            </kbd>
          </div>
        </div>

        {/* ── Right: controls ───────────────────────── */}
        <div className="flex items-center gap-2">

          {/* Team selector */}
          <button
            className="hidden sm:flex items-center gap-2 rounded-xl px-3 py-1.5 text-[13px] font-medium transition-all duration-150"
            style={{
              background: "var(--card)",
              border: "1px solid var(--border)",
              color: "var(--foreground)",
              boxShadow: "var(--shadow-xs)",
            }}
            onMouseEnter={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "#6366f1";
            }}
            onMouseLeave={(e) => {
              (e.currentTarget as HTMLButtonElement).style.borderColor = "var(--border)";
            }}
          >
            <span
              className="flex h-5 w-5 items-center justify-center rounded-md text-[10px] font-bold text-white"
              style={{ background: "linear-gradient(135deg, #6366f1, #8b5cf6)" }}
            >
              {teamName.charAt(0)}
            </span>
            <span className="max-w-[100px] truncate">{teamName}</span>
            <ChevronDown className="h-3.5 w-3.5" style={{ color: "var(--muted-foreground)" }} />
          </button>

          {/* Demo mode toggle */}
          <DemoModeToggle />

          {/* Dark mode */}
          <button
            onClick={toggleDarkMode}
            className="rounded-xl p-2 transition-colors"
            style={{ color: "var(--muted-foreground)" }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "var(--muted)")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "transparent")}
            aria-label="Toggle dark mode"
          >
            {darkMode ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>

          {/* Notifications */}
          <button
            className="relative rounded-xl p-2 transition-colors"
            style={{ color: "var(--muted-foreground)" }}
            onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "var(--muted)")}
            onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "transparent")}
          >
            <Bell className="h-4 w-4" />
            <span
              className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full"
              style={{
                background: "#ef4444",
                border: "2px solid var(--background)",
              }}
            />
          </button>

          {/* User avatar */}
          <div className="relative">
            <button
              onClick={() => setUserOpen(!userOpen)}
              className="flex items-center gap-2 rounded-xl px-2 py-1.5 transition-colors"
              onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "var(--muted)")}
              onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "transparent")}
            >
              <div
                className="flex h-7 w-7 items-center justify-center rounded-full text-[12px] font-bold text-white"
                style={{ background: "linear-gradient(135deg, #818cf8, #6366f1)" }}
              >
                U
              </div>
              <ChevronDown
                className="hidden h-3.5 w-3.5 sm:block"
                style={{ color: "var(--muted-foreground)" }}
              />
            </button>

            {userOpen && (
              <>
                <div
                  className="fixed inset-0 z-40"
                  onClick={() => setUserOpen(false)}
                  aria-hidden="true"
                />
                <div
                  className="absolute right-0 top-full z-50 mt-1.5 w-44 overflow-hidden rounded-xl py-1"
                  style={{
                    background: "var(--card)",
                    border: "1px solid var(--border)",
                    boxShadow: "var(--shadow-lg)",
                  }}
                >
                  <button
                    onClick={handleLogout}
                    className="flex w-full items-center gap-2.5 px-4 py-2.5 text-[13px] font-medium transition-colors"
                    style={{ color: "var(--foreground)" }}
                    onMouseEnter={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "var(--muted)")}
                    onMouseLeave={(e) => ((e.currentTarget as HTMLButtonElement).style.background = "transparent")}
                  >
                    <LogOut className="h-4 w-4" style={{ color: "var(--muted-foreground)" }} />
                    Log out
                  </button>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  );
}
