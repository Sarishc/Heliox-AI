const BETA_ACCESS_STORAGE_KEY = "heliox_beta_access";

function configuredAccessCode(): string {
  return process.env.NEXT_PUBLIC_BETA_ACCESS_CODE?.trim() ?? "";
}

export function hasBetaAccess(): boolean {
  const accessCode = configuredAccessCode();
  if (!accessCode) {
    return true;
  }

  if (typeof window === "undefined") {
    return false;
  }

  return window.localStorage.getItem(BETA_ACCESS_STORAGE_KEY) === accessCode;
}

export function verifyBetaAccess(candidate: string): boolean {
  const accessCode = configuredAccessCode();
  const allowed = !accessCode || candidate === accessCode;

  if (allowed && typeof window !== "undefined" && accessCode) {
    window.localStorage.setItem(BETA_ACCESS_STORAGE_KEY, accessCode);
  }

  return allowed;
}
