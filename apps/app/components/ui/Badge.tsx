/**
 * Badge Component
 * Status indicators and labels
 */

import { ReactNode } from "react";

interface BadgeProps {
  children: ReactNode;
  variant?: "default" | "success" | "warning" | "danger" | "info" | "brand";
  size?: "sm" | "md" | "lg";
  className?: string;
}

export function Badge({
  children,
  variant = "default",
  size = "md",
  className = "",
}: BadgeProps) {
  const variantStyles = {
    default: "bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300",
    success: "bg-success-50 text-success-700 dark:bg-success-500/10 dark:text-success-400",
    warning: "bg-warning-50 text-warning-700 dark:bg-warning-500/10 dark:text-warning-400",
    danger: "bg-danger-50 text-danger-700 dark:bg-danger-500/10 dark:text-danger-400",
    info: "bg-info-50 text-info-700 dark:bg-info-500/10 dark:text-info-400",
    brand: "bg-brand-50 text-brand-700 dark:bg-brand-500/10 dark:text-brand-400",
  };

  const sizeStyles = {
    sm: "px-2 py-0.5 text-xs",
    md: "px-2.5 py-1 text-sm",
    lg: "px-3 py-1.5 text-base",
  };

  return (
    <span
      className={`
        inline-flex items-center gap-1
        font-medium rounded-md
        ${variantStyles[variant]}
        ${sizeStyles[size]}
        ${className}
      `}
    >
      {children}
    </span>
  );
}

export function DotBadge({
  variant = "default",
  className = "",
}: {
  variant?: "default" | "success" | "warning" | "danger" | "info";
  className?: string;
}) {
  const colors = {
    default: "bg-gray-400",
    success: "bg-success-500",
    warning: "bg-warning-500",
    danger: "bg-danger-500",
    info: "bg-info-500",
  };

  return (
    <span className={`w-2 h-2 rounded-full ${colors[variant]} ${className}`} />
  );
}
