"use client";

/**
 * Dropdown Menu Component
 * Enterprise dropdown with animations
 */

import { useState, useRef, useEffect, ReactNode } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { ChevronDown } from "lucide-react";

interface DropdownProps {
  trigger: ReactNode;
  children: ReactNode;
  align?: "left" | "right";
  className?: string;
}

export function Dropdown({
  trigger,
  children,
  align = "left",
  className = "",
}: DropdownProps) {
  const [isOpen, setIsOpen] = useState(false);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // Close on click outside
  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        dropdownRef.current &&
        !dropdownRef.current.contains(event.target as Node)
      ) {
        setIsOpen(false);
      }
    };

    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, []);

  // Close on escape
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) {
        setIsOpen(false);
      }
    };
    document.addEventListener("keydown", handleEscape);
    return () => document.removeEventListener("keydown", handleEscape);
  }, [isOpen]);

  return (
    <div ref={dropdownRef} className={`relative ${className}`}>
      <div onClick={() => setIsOpen(!isOpen)}>{trigger}</div>

      <AnimatePresence>
        {isOpen && (
          <motion.div
            initial={{ opacity: 0, y: -10, scale: 0.95 }}
            animate={{ opacity: 1, y: 0, scale: 1 }}
            exit={{ opacity: 0, y: -10, scale: 0.95 }}
            transition={{ duration: 0.15 }}
            className={`
              absolute top-full mt-2 z-50
              min-w-[200px] max-w-xs
              bg-card border border-border rounded-xl shadow-xl
              py-2
              ${align === "right" ? "right-0" : "left-0"}
            `}
          >
            <div onClick={() => setIsOpen(false)}>{children}</div>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

export function DropdownItem({
  children,
  onClick,
  icon,
  destructive = false,
  disabled = false,
}: {
  children: ReactNode;
  onClick?: () => void;
  icon?: ReactNode;
  destructive?: boolean;
  disabled?: boolean;
}) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      className={`
        w-full flex items-center gap-3 px-4 py-2.5
        text-sm font-medium text-left
        transition-colors
        ${
          destructive
            ? "text-danger-600 hover:bg-danger-50 dark:hover:bg-danger-500/10"
            : disabled
            ? "text-muted-foreground opacity-50 cursor-not-allowed"
            : "text-foreground hover:bg-muted"
        }
      `}
    >
      {icon && <span className="w-5 h-5">{icon}</span>}
      <span className="flex-1">{children}</span>
    </button>
  );
}

export function DropdownDivider() {
  return <div className="my-2 h-px bg-border" />;
}

export function DropdownLabel({ children }: { children: ReactNode }) {
  return (
    <div className="px-4 py-2 text-xs font-semibold text-muted-foreground uppercase tracking-wide">
      {children}
    </div>
  );
}
