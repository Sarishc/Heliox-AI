"use client";

/**
 * Toast Notification System
 * Enterprise-grade notifications
 */

import { createContext, useContext, useState, useCallback, ReactNode } from "react";
import { motion, AnimatePresence, useReducedMotion } from "framer-motion";
import { X, CheckCircle, AlertCircle, Info, AlertTriangle } from "lucide-react";

type ToastType = "success" | "error" | "info" | "warning";

interface Toast {
  id: string;
  type: ToastType;
  title: string;
  message?: string;
  duration?: number;
}

interface ToastContextType {
  showToast: (toast: Omit<Toast, "id">) => void;
  showSuccess: (title: string, message?: string) => void;
  showError: (title: string, message?: string) => void;
  showInfo: (title: string, message?: string) => void;
  showWarning: (title: string, message?: string) => void;
}

const ToastContext = createContext<ToastContextType | undefined>(undefined);

export function useToast() {
  const context = useContext(ToastContext);
  if (!context) {
    throw new Error("useToast must be used within ToastProvider");
  }
  return context;
}

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([]);

  const removeToast = useCallback((id: string) => {
    setToasts((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const showToast = useCallback(
    (toast: Omit<Toast, "id">) => {
      const id = Math.random().toString(36).substring(7);
      const newToast = { ...toast, id };
      setToasts((prev) => [...prev, newToast]);

      // Auto-remove after duration
      const duration = toast.duration || 5000;
      setTimeout(() => {
        removeToast(id);
      }, duration);
    },
    [removeToast]
  );

  const showSuccess = useCallback(
    (title: string, message?: string) => {
      showToast({ type: "success", title, message });
    },
    [showToast]
  );

  const showError = useCallback(
    (title: string, message?: string) => {
      showToast({ type: "error", title, message });
    },
    [showToast]
  );

  const showInfo = useCallback(
    (title: string, message?: string) => {
      showToast({ type: "info", title, message });
    },
    [showToast]
  );

  const showWarning = useCallback(
    (title: string, message?: string) => {
      showToast({ type: "warning", title, message });
    },
    [showToast]
  );

  return (
    <ToastContext.Provider
      value={{ showToast, showSuccess, showError, showInfo, showWarning }}
    >
      {children}
      <ToastContainer toasts={toasts} onRemove={removeToast} />
    </ToastContext.Provider>
  );
}

function ToastContainer({
  toasts,
  onRemove,
}: {
  toasts: Toast[];
  onRemove: (id: string) => void;
}) {
  return (
    <div className="fixed top-4 right-4 z-50 flex flex-col gap-3 max-w-md">
      <AnimatePresence>
        {toasts.map((toast) => (
          <ToastItem key={toast.id} toast={toast} onRemove={onRemove} />
        ))}
      </AnimatePresence>
    </div>
  );
}

function ToastItem({
  toast,
  onRemove,
}: {
  toast: Toast;
  onRemove: (id: string) => void;
}) {
  const reduceMotion = useReducedMotion();
  const config = {
    success: {
      icon: CheckCircle,
      bg: "bg-success-50 dark:bg-success-500/10",
      border: "border-success-200 dark:border-success-500/20",
      iconColor: "text-success-600 dark:text-success-500",
      textColor: "text-success-900 dark:text-success-100",
    },
    error: {
      icon: AlertCircle,
      bg: "bg-danger-50 dark:bg-danger-500/10",
      border: "border-danger-200 dark:border-danger-500/20",
      iconColor: "text-danger-600 dark:text-danger-500",
      textColor: "text-danger-900 dark:text-danger-100",
    },
    info: {
      icon: Info,
      bg: "bg-info-50 dark:bg-info-500/10",
      border: "border-info-200 dark:border-info-500/20",
      iconColor: "text-info-600 dark:text-info-500",
      textColor: "text-info-900 dark:text-info-100",
    },
    warning: {
      icon: AlertTriangle,
      bg: "bg-warning-50 dark:bg-warning-500/10",
      border: "border-warning-200 dark:border-warning-500/20",
      iconColor: "text-warning-600 dark:text-warning-500",
      textColor: "text-warning-900 dark:text-warning-100",
    },
  };

  const { icon: Icon, bg, border, iconColor, textColor } = config[toast.type];

  return (
    <motion.div
      initial={reduceMotion ? false : { opacity: 0, y: -16, scale: 0.97 }}
      animate={{ opacity: 1, y: 0, scale: 1 }}
      exit={reduceMotion ? { opacity: 0 } : { opacity: 0, x: 40, scale: 0.98 }}
      transition={reduceMotion ? { duration: 0 } : { type: "spring", stiffness: 430, damping: 34 }}
      className={`
        flex items-start gap-3 p-4 rounded-xl border shadow-lg
        ${bg} ${border}
      `}
    >
      <Icon className={`w-5 h-5 ${iconColor} flex-shrink-0 mt-0.5`} />
      <div className="flex-1 min-w-0">
        <p className={`font-semibold text-sm ${textColor}`}>{toast.title}</p>
        {toast.message && (
          <p className={`text-sm mt-1 ${textColor} opacity-90`}>{toast.message}</p>
        )}
      </div>
      <button
        onClick={() => onRemove(toast.id)}
        className={`${textColor} opacity-60 hover:opacity-100 transition-opacity`}
      >
        <X className="w-4 h-4" />
      </button>
    </motion.div>
  );
}
