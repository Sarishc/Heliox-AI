"use client";

/**
 * Command Palette (⌘K)
 * Quick navigation and actions
 */

import { useState, useEffect, useMemo, useCallback } from "react";
import { useRouter } from "next/navigation";
import { motion, AnimatePresence } from "framer-motion";
import {
  Search,
  LayoutDashboard,
  BarChart3,
  TrendingUp,
  Sparkles,
  AlertTriangle,
  Zap,
  Blocks,
  CreditCard,
  Settings,
  Command,
} from "lucide-react";

interface CommandItem {
  id: string;
  label: string;
  description?: string;
  icon: React.ReactNode;
  action: () => void;
  keywords?: string[];
}

export function CommandPalette() {
  const router = useRouter();
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);

  const commands: CommandItem[] = useMemo(
    () => [
      {
        id: "dashboard",
        label: "Dashboard",
        description: "GPU cost command center",
        icon: <LayoutDashboard className="w-5 h-5" />,
        action: () => router.push("/"),
        keywords: ["home", "overview", "main"],
      },
      {
        id: "analytics",
        label: "Analytics",
        description: "Detailed cost analytics",
        icon: <BarChart3 className="w-5 h-5" />,
        action: () => router.push("/analytics"),
        keywords: ["charts", "data", "metrics"],
      },
      {
        id: "forecast",
        label: "Forecasting",
        description: "Cost predictions and trends",
        icon: <TrendingUp className="w-5 h-5" />,
        action: () => router.push("/forecast"),
        keywords: ["prediction", "future", "trends"],
      },
      {
        id: "optimization",
        label: "Optimization",
        description: "Cost saving recommendations",
        icon: <Sparkles className="w-5 h-5" />,
        action: () => router.push("/optimization"),
        keywords: ["optimize", "savings", "efficiency"],
      },
      {
        id: "budgets",
        label: "Budgets",
        description: "Budget alerts and tracking",
        icon: <AlertTriangle className="w-5 h-5" />,
        action: () => router.push("/budgets"),
        keywords: ["limits", "alerts", "thresholds"],
      },
      {
        id: "proxy",
        label: "Proxy",
        description: "LLM proxy and caching",
        icon: <Zap className="w-5 h-5" />,
        action: () => router.push("/proxy"),
        keywords: ["llm", "cache", "requests"],
      },
      {
        id: "integrations",
        label: "Integrations",
        description: "Cloud integrations",
        icon: <Blocks className="w-5 h-5" />,
        action: () => router.push("/settings/integrations"),
        keywords: ["aws", "gcp", "connect"],
      },
      {
        id: "billing",
        label: "Billing",
        description: "Plans and subscriptions",
        icon: <CreditCard className="w-5 h-5" />,
        action: () => router.push("/billing"),
        keywords: ["pricing", "subscription", "plans"],
      },
      {
        id: "settings",
        label: "Settings",
        description: "Account and preferences",
        icon: <Settings className="w-5 h-5" />,
        action: () => router.push("/settings"),
        keywords: ["account", "preferences", "config"],
      },
    ],
    [router]
  );

  const filteredCommands = useMemo(() => {
    if (!search.trim()) return commands;

    const searchLower = search.toLowerCase();
    return commands.filter(
      (cmd) =>
        cmd.label.toLowerCase().includes(searchLower) ||
        cmd.description?.toLowerCase().includes(searchLower) ||
        cmd.keywords?.some((k) => k.includes(searchLower))
    );
  }, [commands, search]);

  // Open/close with Cmd+K or Ctrl+K
  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, []);

  // Handle keyboard navigation
  useEffect(() => {
    if (!isOpen) return;

    const handleKeyDown = (e: KeyboardEvent) => {
      if (e.key === "Escape") {
        setIsOpen(false);
        setSearch("");
        setSelectedIndex(0);
      } else if (e.key === "ArrowDown") {
        e.preventDefault();
        setSelectedIndex((prev) =>
          prev < filteredCommands.length - 1 ? prev + 1 : prev
        );
      } else if (e.key === "ArrowUp") {
        e.preventDefault();
        setSelectedIndex((prev) => (prev > 0 ? prev - 1 : 0));
      } else if (e.key === "Enter") {
        e.preventDefault();
        if (filteredCommands[selectedIndex]) {
          filteredCommands[selectedIndex].action();
          setIsOpen(false);
          setSearch("");
          setSelectedIndex(0);
        }
      }
    };

    document.addEventListener("keydown", handleKeyDown);
    return () => document.removeEventListener("keydown", handleKeyDown);
  }, [isOpen, filteredCommands, selectedIndex]);

  // Reset selection when search changes
  useEffect(() => {
    setSelectedIndex(0);
  }, [search]);

  // Prevent body scroll when open
  useEffect(() => {
    if (isOpen) {
      document.body.style.overflow = "hidden";
    } else {
      document.body.style.overflow = "unset";
    }
    return () => {
      document.body.style.overflow = "unset";
    };
  }, [isOpen]);

  const handleSelect = useCallback(
    (command: CommandItem) => {
      command.action();
      setIsOpen(false);
      setSearch("");
      setSelectedIndex(0);
    },
    []
  );

  return (
    <AnimatePresence>
      {isOpen && (
        <>
          {/* Backdrop */}
          <motion.div
            initial={{ opacity: 0 }}
            animate={{ opacity: 1 }}
            exit={{ opacity: 0 }}
            transition={{ duration: 0.15 }}
            onClick={() => setIsOpen(false)}
            className="fixed inset-0 bg-black/50 backdrop-blur-sm z-50"
          />

          {/* Command Palette */}
          <div className="fixed inset-0 z-50 flex items-start justify-center pt-[20vh]">
            <motion.div
              initial={{ opacity: 0, scale: 0.95, y: -20 }}
              animate={{ opacity: 1, scale: 1, y: 0 }}
              exit={{ opacity: 0, scale: 0.95, y: -20 }}
              transition={{ duration: 0.15 }}
              className="w-full max-w-2xl mx-4 bg-card border border-border rounded-2xl shadow-2xl overflow-hidden"
            >
              {/* Search Input */}
              <div className="flex items-center gap-3 px-4 py-4 border-b border-border">
                <Search className="w-5 h-5 text-muted-foreground" />
                <input
                  type="text"
                  placeholder="Search commands..."
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  autoFocus
                  className="flex-1 bg-transparent text-foreground placeholder:text-muted-foreground outline-none text-lg"
                />
                <kbd className="hidden sm:inline-flex items-center gap-1 px-2 py-1 text-xs font-semibold bg-muted rounded border border-border">
                  <Command className="w-3 h-3" />K
                </kbd>
              </div>

              {/* Commands List */}
              <div className="max-h-96 overflow-y-auto p-2">
                {filteredCommands.length === 0 ? (
                  <div className="py-12 text-center text-muted-foreground">
                    No commands found
                  </div>
                ) : (
                  <div className="space-y-1">
                    {filteredCommands.map((command, index) => (
                      <button
                        key={command.id}
                        onClick={() => handleSelect(command)}
                        onMouseEnter={() => setSelectedIndex(index)}
                        className={`
                          w-full flex items-center gap-3 px-4 py-3 rounded-lg
                          text-left transition-colors
                          ${
                            index === selectedIndex
                              ? "bg-brand-50 dark:bg-brand-500/10"
                              : "hover:bg-muted"
                          }
                        `}
                      >
                        <div
                          className={`
                          p-2 rounded-lg
                          ${
                            index === selectedIndex
                              ? "bg-brand-600 text-white"
                              : "bg-muted text-muted-foreground"
                          }
                        `}
                        >
                          {command.icon}
                        </div>
                        <div className="flex-1 min-w-0">
                          <div className="font-medium text-foreground">
                            {command.label}
                          </div>
                          {command.description && (
                            <div className="text-sm text-muted-foreground">
                              {command.description}
                            </div>
                          )}
                        </div>
                      </button>
                    ))}
                  </div>
                )}
              </div>

              {/* Footer */}
              <div className="flex items-center justify-between px-4 py-3 border-t border-border bg-muted/30 text-xs text-muted-foreground">
                <div className="flex items-center gap-4">
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-background rounded border border-border">
                      ↑↓
                    </kbd>
                    Navigate
                  </span>
                  <span className="flex items-center gap-1">
                    <kbd className="px-1.5 py-0.5 bg-background rounded border border-border">
                      ↵
                    </kbd>
                    Select
                  </span>
                </div>
                <span className="flex items-center gap-1">
                  <kbd className="px-1.5 py-0.5 bg-background rounded border border-border">
                    ESC
                  </kbd>
                  Close
                </span>
              </div>
            </motion.div>
          </div>
        </>
      )}
    </AnimatePresence>
  );
}
