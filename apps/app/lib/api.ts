/**
 * API utility functions for consistent API calls across the application.
 *
 * Centralizes API base URL handling, cookie-based auth, retry logic, and error handling.
 * Uses httpOnly cookies for auth - no token storage in localStorage.
 */

// ── Demo block modal integration ─────────────────────────────────────────────
// Components import DemoBlockModal directly and call showDemoBlockModal() to
// trigger it from anywhere in the app without prop-drilling.

type DemoBlockHandler = (signupUrl?: string) => void;
let _demoBlockHandler: DemoBlockHandler | null = null;

/**
 * Register the global demo-block modal trigger (called once from a root client component).
 * Separating registration from usage avoids circular deps and SSR issues.
 */
export function registerDemoBlockHandler(fn: DemoBlockHandler): void {
  _demoBlockHandler = fn;
}

/** Trigger the demo-block modal, or fall back to a simple alert. */
export function showDemoBlockModal(signupUrl?: string): void {
  if (_demoBlockHandler) {
    _demoBlockHandler(signupUrl);
  }
}

const MAX_RETRIES = 2;

/**
 * Get the API base URL from environment variables.
 *
 * - When empty in dev: use "" (relative URLs) so Next.js proxy routes to backend. Fixes cross-origin cookies.
 * - When set: use that URL (e.g., "https://api.example.com" or "http://localhost:8001").
 *
 * @returns API base URL or "" for same-origin (proxy) in dev
 */
export function getApiBaseUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  if (typeof window !== "undefined" && !apiBaseUrl && process.env.NODE_ENV === "production") {
    console.warn(
      "NEXT_PUBLIC_API_BASE_URL is not set. API calls will fail. " +
        "Set this environment variable in your deployment settings."
    );
  }

  if (!apiBaseUrl && process.env.NODE_ENV === "production") {
    return "";
  }

  // Empty = use relative URLs (Next.js proxy). In dev this fixes cross-origin cookie auth.
  if (!apiBaseUrl) {
    return "";
  }

  return apiBaseUrl;
}

/**
 * Get the full API URL for a given endpoint path.
 *
 * @param path - API endpoint path (e.g., "/api/v1/recommendations" or "/health")
 * @returns Full URL
 */
export function getApiUrl(path: string): string {
  const baseUrl = getApiBaseUrl();

  // Ensure path starts with /
  const normalizedPath = path.startsWith("/") ? path : `/${path}`;

  return `${baseUrl}${normalizedPath}`;
}

/** CSRF cookie name (must match backend). */
const CSRF_COOKIE = "heliox_csrf";

/** Get CSRF token from cookie for OWASP CSRF protection. */
function getCsrfToken(): string | null {
  if (typeof document === "undefined") return null;
  const match = document.cookie.match(new RegExp(`(^| )${CSRF_COOKIE}=([^;]+)`));
  return match ? decodeURIComponent(match[2]) : null;
}

/**
 * Redirect to login on 401 (expired/missing session).
 */
function redirectToLogin(): void {
  if (typeof window === "undefined") return;
  const current = window.location.pathname;
  if (current !== "/login" && current !== "/signup") {
    window.location.href = `/login?redirect=${encodeURIComponent(current)}`;
  }
}

/**
 * Fetch from API with credentials (cookies), retry logic, and error handling.
 *
 * - credentials: 'include' sends httpOnly auth cookie (no tokens in localStorage)
 * - 401 triggers redirect to login
 * - Retries up to MAX_RETRIES on network/5xx errors
 *
 * @param endpoint - API endpoint path
 * @param options - Fetch options
 * @returns Response or throws error
 */
export async function fetchApi(
  endpoint: string,
  options?: RequestInit & { skipAuthRedirect?: boolean }
): Promise<Response> {
  const url = getApiUrl(endpoint);
  const skipAuthRedirect = options?.skipAuthRedirect ?? false;
  const { skipAuthRedirect: _, ...fetchOptions } = options ?? {};

  const doFetch = async (attempt: number): Promise<Response> => {
    const method = (fetchOptions?.method ?? "GET").toUpperCase();
    const isStateChange = ["POST", "PUT", "DELETE", "PATCH"].includes(method);
    const csrfToken = isStateChange ? getCsrfToken() : null;

    const response = await fetch(url, {
      ...fetchOptions,
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        ...(csrfToken ? { "X-CSRF-Token": csrfToken } : {}),
        ...fetchOptions?.headers,
      },
    });

    if (response.status === 401 && !skipAuthRedirect) {
      // Don't redirect in demo mode — let components handle 401 gracefully
      const isDemo =
        typeof window !== "undefined" &&
        localStorage.getItem("heliox_demo_mode") === "true";
      if (!isDemo) {
        redirectToLogin();
        throw new Error("Session expired. Redirecting to login.");
      }
      throw new Error("Demo mode: API not available.");
    }

    // Show demo-block modal for demo_mode 403s on write operations
    if (response.status === 403) {
      try {
        const clone = response.clone();
        const body = await clone.json();
        if (body?.error === "demo_mode") {
          showDemoBlockModal(body?.signup_url);
          throw new Error("demo_mode");
        }
      } catch (e) {
        if (e instanceof Error && e.message === "demo_mode") throw e;
      }
    }

    return response;
  };

  let lastError: unknown;
  for (let attempt = 0; attempt <= MAX_RETRIES; attempt++) {
    try {
      const response = await doFetch(attempt);
      // Retry on 5xx or network failure
      if (response.status >= 500 && attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, 300 * (attempt + 1)));
        continue;
      }
      return response;
    } catch (error) {
      lastError = error;
      if (error instanceof Error && error.message.includes("Redirecting to login")) throw error;
      if (attempt < MAX_RETRIES) {
        await new Promise((r) => setTimeout(r, 300 * (attempt + 1)));
      } else {
        break;
      }
    }
  }

  // Detect network/fetch failures (Chrome: "Failed to fetch", Safari: "Load failed", etc.)
  const errMsg = lastError instanceof Error ? lastError.message : String(lastError);
  const isNetworkError =
    lastError instanceof TypeError ||
    /fetch|load failed|network|connection refused|cors/i.test(errMsg);
  if (isNetworkError) {
    throw new Error(
      "Unable to connect to API. Please check your connection and ensure the backend is running."
    );
  }
  throw lastError;
}

/**
 * No API key or token storage - auth is cookie-only (httpOnly).
 * API keys are for programmatic access (CLI); copy from Settings when created.
 */
export function getStoredApiKey(): string | null {
  return null;
}

/** No-op: API keys must not be stored in JS-accessible storage. */
export function setStoredApiKey(_key: string) {
  // No-op: use cookie auth only
}

/** No-op: no stored API key to clear. */
export function clearStoredApiKey() {
  // No-op
}

/** @deprecated Auth uses httpOnly cookies - no token storage. */
export function getStoredAccessToken(): string | null {
  return null;
}

/** @deprecated Auth uses httpOnly cookies - no-op. */
export function setStoredAccessToken(_token: string) {
  // No-op: auth is cookie-based
}

/** @deprecated Auth uses httpOnly cookies - no-op. Use logout endpoint. */
export function clearStoredAccessToken() {
  // No-op
}

/**
 * No-op: Dev bootstrap removed for security.
 * Users must sign up and log in; use onboarding to create a team.
 */
export async function bootstrapDevApiKey(): Promise<void> {
  // No-op: cookie-only auth; no API key storage
}

/**
 * Fetch JSON from API with error handling.
 *
 * @param endpoint - API endpoint path
 * @param options - Fetch options (skipAuthRedirect to avoid redirect on 401)
 * @returns Parsed JSON response
 */
export async function fetchJson<T = unknown>(
  endpoint: string,
  options?: RequestInit & { skipAuthRedirect?: boolean }
): Promise<T> {
  const response = await fetchApi(endpoint, options);

  if (!response.ok) {
    let detail = response.statusText;
    try {
      const body = await response.json();
      detail = body?.detail ?? body?.message ?? detail;
    } catch {
      // ignore
    }
    throw new Error(typeof detail === "string" ? detail : JSON.stringify(detail));
  }

  return response.json();
}
