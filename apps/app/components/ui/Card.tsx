/**
 * Enterprise Card Component
 * Premium card design with variants, hover states, and loading
 */

import { ReactNode } from "react";

interface CardProps {
  children: ReactNode;
  className?: string;
  variant?: "default" | "bordered" | "elevated" | "flat";
  padding?: "none" | "sm" | "md" | "lg";
  hoverable?: boolean;
  loading?: boolean;
}

export function Card({
  children,
  className = "",
  variant = "default",
  padding = "md",
  hoverable = false,
  loading = false,
}: CardProps) {
  const variantStyles = {
    default:
      "bg-card border border-border shadow-sm",
    bordered: "bg-card border-2 border-border",
    elevated: "bg-card border border-border shadow-lg",
    flat: "bg-muted border border-transparent",
  };

  const paddingStyles = {
    none: "",
    sm: "p-4",
    md: "p-6",
    lg: "p-8",
  };

  const hoverStyles = hoverable
    ? "transition-all duration-200 hover:shadow-md hover:-translate-y-0.5 cursor-pointer"
    : "";

  if (loading) {
    return (
      <div
        className={`
          ${variantStyles[variant]}
          ${paddingStyles[padding]}
          rounded-xl
          animate-pulse
          ${className}
        `}
      >
        <div className="space-y-3">
          <div className="h-4 bg-muted rounded w-3/4"></div>
          <div className="h-8 bg-muted rounded w-1/2"></div>
          <div className="h-3 bg-muted rounded w-full"></div>
        </div>
      </div>
    );
  }

  return (
    <div
      className={`
        ${variantStyles[variant]}
        ${paddingStyles[padding]}
        ${hoverStyles}
        rounded-xl
        transition-colors
        ${className}
      `}
    >
      {children}
    </div>
  );
}

export function CardHeader({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mb-4 ${className}`}>
      {children}
    </div>
  );
}

export function CardTitle({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h3 className={`text-lg font-semibold text-foreground ${className}`}>
      {children}
    </h3>
  );
}

export function CardDescription({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <p className={`text-sm text-muted-foreground mt-1 ${className}`}>
      {children}
    </p>
  );
}

export function CardContent({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={className}>{children}</div>;
}

export function CardFooter({
  children,
  className = "",
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <div className={`mt-6 pt-4 border-t border-border ${className}`}>
      {children}
    </div>
  );
}
