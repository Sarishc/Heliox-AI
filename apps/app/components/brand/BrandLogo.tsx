import Link from "next/link";

export function BrandMark({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg className={className} viewBox="0 0 64 64" role="img" aria-label="Heliox">
      <defs>
        <linearGradient id="heliox-violet" x1="14" y1="8" x2="50" y2="56" gradientUnits="userSpaceOnUse">
          <stop stopColor="#C4B5FD" />
          <stop offset=".48" stopColor="#8B5CF6" />
          <stop offset="1" stopColor="#6D28D9" />
        </linearGradient>
      </defs>
      <path d="M17 10v44" fill="none" stroke="url(#heliox-violet)" strokeWidth="8" strokeLinecap="round" />
      <path d="M47 10v44" fill="none" stroke="url(#heliox-violet)" strokeWidth="8" strokeLinecap="round" />
      <path d="M17 21c9 0 21 22 30 22" fill="none" stroke="#EDE9FE" strokeWidth="6" strokeLinecap="round" />
      <path d="M47 21c-9 0-21 22-30 22" fill="none" stroke="#8B5CF6" strokeWidth="6" strokeLinecap="round" />
    </svg>
  );
}
export function BrandLogo({
  href = "/",
  compact = false,
  className = "",
}: {
  href?: string;
  compact?: boolean;
  className?: string;
}) {
  return (
    <Link href={href} className={`inline-flex items-center gap-3 ${className}`} aria-label="Heliox home">
      <BrandMark className={compact ? "h-7 w-7" : "h-9 w-9"} />
      {!compact && (
        <span className="text-[22px] font-semibold tracking-[-0.055em] text-white">
          heliox<span className="ml-1 inline-block h-1.5 w-1.5 rounded-full bg-violet-500 align-baseline" />
        </span>
      )}
    </Link>
  );
}
