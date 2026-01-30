/**
 * API utility functions for consistent API calls across the application.
 *
 * Centralizes API base URL handling and provides type-safe API methods.
 */

/**
 * Get the API base URL from environment variables.
 *
 * In production, NEXT_PUBLIC_API_BASE_URL must be set.
 * Falls back to localhost for development only.
 *
 * @returns API base URL (e.g., "https://api.example.com" or "http://localhost:8000")
 */
export function getApiBaseUrl(): string {
  const apiBaseUrl = process.env.NEXT_PUBLIC_API_BASE_URL;

  // In production builds, warn if API URL is not set
  if (typeof window !== "undefined" && !apiBaseUrl && process.env.NODE_ENV === "production") {
    console.warn(
      "NEXT_PUBLIC_API_BASE_URL is not set. API calls will fail. " +
        "Set this environment variable in your deployment settings."
    );
  }

  // Fallback to localhost only in development
  // In production, empty string will cause clear errors (better than silent failures)
  if (!apiBaseUrl && process.env.NODE_ENV === "production") {
    return "";
  }

  return apiBaseUrl || "http://localhost:8000";
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

/**
 * Fetch from API with consistent error handling.
 *
 * @param endpoint - API endpoint path
 * @param options - Fetch options
 * @returns Response or throws error
 */
export async function fetchApi(
  endpoint: string,
  options?: RequestInit
): Promise<Response> {
  const url = getApiUrl(endpoint);
  const apiKey = getStoredApiKey();
  const devApiKey = "hlx_jjN3llgYZZIHY63Qk0JdhqSNvra8JG4k4u3SAs_wKvY"; // Dev API key for localhost
  const accessToken = getStoredAccessToken();
  const isLocalhost = typeof window !== 'undefined' && 
    (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1');

  try {
    const response = await fetch(url, {
      ...options,
      headers: {
        "Content-Type": "application/json",
        // Use stored API key if available, otherwise use dev key on localhost
        ...(apiKey ? { "X-API-Key": apiKey } : (isLocalhost ? { "X-API-Key": devApiKey } : {})),
        ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
        ...options?.headers
      },
    });

    return response;
  } catch (error) {
    // Network error - API is unreachable
    if (error instanceof TypeError && error.message.includes("fetch")) {
      throw new Error(
        "Unable to connect to API. Please check your connection and ensure the backend is running."
      );
    }
    throw error;
  }
}

const API_KEY_STORAGE = "heliox_api_key";
const ACCESS_TOKEN_STORAGE = "heliox_access_token";
const DEV_BOOTSTRAP_STORAGE = "heliox_dev_bootstrap_done";

export function getStoredApiKey(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(API_KEY_STORAGE);
}

export function setStoredApiKey(key: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(API_KEY_STORAGE, key);
}

export function clearStoredApiKey() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(API_KEY_STORAGE);
}

export function getStoredAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ACCESS_TOKEN_STORAGE);
}

export function setStoredAccessToken(token: string) {
  if (typeof window === "undefined") return;
  localStorage.setItem(ACCESS_TOKEN_STORAGE, token);
}

export function clearStoredAccessToken() {
  if (typeof window === "undefined") return;
  localStorage.removeItem(ACCESS_TOKEN_STORAGE);
}

export async function bootstrapDevApiKey(): Promise<void> {
  if (typeof window === "undefined") return;
  if (getStoredApiKey()) return;
  if (localStorage.getItem(DEV_BOOTSTRAP_STORAGE) === "done") return;

  const hostname = window.location.hostname;
  const isLocalhost = hostname === "localhost" || hostname === "127.0.0.1";
  if (!isLocalhost) return;

  const devAdminKey = "dev-admin-key-change-me";

  const baseUrl = getApiBaseUrl();
  const adminHeaders = {
    "Content-Type": "application/json",
    "X-API-Key": devAdminKey,
  };

  try {
    console.log("[Bootstrap] Starting dev environment bootstrap...");
    
    const teamsResponse = await fetch(`${baseUrl}/api/v1/admin/teams`, {
      headers: adminHeaders,
    });

    if (!teamsResponse.ok) {
      console.error("[Bootstrap] Failed to fetch teams:", teamsResponse.status);
      return;
    }

    const teams = await teamsResponse.json();
    let teamId: string | null = teams?.[0]?.id ?? null;
    let apiKey: string | null = null;

    if (!teamId) {
      console.log("[Bootstrap] No teams found, creating demo team...");
      const onboardResponse = await fetch(`${baseUrl}/api/v1/admin/onboard`, {
        method: "POST",
        headers: adminHeaders,
        body: JSON.stringify({
          team_name: "Demo Team",
          api_key_name: "Local Dev Key",
          monthly_budget_usd: 25000,
        }),
      });

      if (onboardResponse.ok) {
        const onboardPayload = await onboardResponse.json();
        teamId = onboardPayload.team_id ?? null;
        apiKey = onboardPayload.api_key ?? null;
        console.log("[Bootstrap] Demo team created:", teamId);
      } else {
        console.error("[Bootstrap] Failed to create team:", onboardResponse.status);
      }
    } else {
      console.log("[Bootstrap] Found existing team:", teamId);
    }

    if (!apiKey && teamId) {
      console.log("[Bootstrap] Creating API key for team...");
      const keyResponse = await fetch(`${baseUrl}/api/v1/admin/teams/${teamId}/api-keys`, {
        method: "POST",
        headers: adminHeaders,
        body: JSON.stringify({ team_id: teamId, key_name: "Local Dev Key" }),
      });

      if (keyResponse.ok) {
        const keyPayload = await keyResponse.json();
        apiKey = keyPayload.api_key ?? null;
        console.log("[Bootstrap] API key created");
      } else {
        console.error("[Bootstrap] Failed to create API key:", keyResponse.status);
      }
    }

    if (apiKey) {
      setStoredApiKey(apiKey);
      localStorage.setItem(DEV_BOOTSTRAP_STORAGE, "done");
      console.log("[Bootstrap] API key saved to localStorage");

      console.log("[Bootstrap] Seeding demo data...");
      const seedResponse = await fetch(`${baseUrl}/api/v1/admin/demo/seed`, {
        method: "POST",
        headers: adminHeaders,
      });
      
      if (seedResponse.ok) {
        console.log("[Bootstrap] Demo data seeded successfully");
      } else {
        console.error("[Bootstrap] Failed to seed demo data:", seedResponse.status);
      }
    }
  } catch (error) {
    console.error("[Bootstrap] Bootstrap failed:", error);
    // Ignore bootstrap failures to avoid blocking the UI.
  }
}

/**
 * Fetch JSON from API with error handling.
 *
 * @param endpoint - API endpoint path
 * @param options - Fetch options
 * @returns Parsed JSON response
 */
export async function fetchJson<T = unknown>(
  endpoint: string,
  options?: RequestInit
): Promise<T> {
  const response = await fetchApi(endpoint, options);

  if (!response.ok) {
    throw new Error(
      `API request failed: ${response.status} ${response.statusText}`
    );
  }

  return response.json();
}
