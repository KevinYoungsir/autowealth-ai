import { ui } from "@/i18n";

const DEFAULT_RESEARCH_API_BASE_URL = "http://127.0.0.1:8001";

const isProduction = process.env.NODE_ENV === "production";
const configuredApiBaseUrl =
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  (!isProduction ? process.env.RESEARCH_API_BASE_URL?.trim() : "");
const RESEARCH_API_BASE_URL = (
  configuredApiBaseUrl || (!isProduction ? DEFAULT_RESEARCH_API_BASE_URL : "")
).replace(/\/+$/, "");

function buildResearchApiUrl(path: string) {
  if (!RESEARCH_API_BASE_URL) {
    throw new Error(
      ui.errors.productionApiRequired
    );
  }
  if (path !== "/research" && !path.startsWith("/research/")) {
    throw new Error(ui.errors.researchPathsOnly);
  }
  let target: URL;
  try {
    target = new URL(RESEARCH_API_BASE_URL);
  } catch {
    throw new Error(ui.errors.invalidApiBaseUrl);
  }
  const localTarget = target.hostname === "127.0.0.1" || target.hostname === "localhost";
  if (!localTarget && target.protocol !== "https:") {
    throw new Error(ui.errors.productionHttpsRequired);
  }
  return `${RESEARCH_API_BASE_URL}${path}`;
}

export async function proxyResearchJson(path: string, init?: RequestInit) {
  try {
    const response = await fetch(buildResearchApiUrl(path), {
      ...init,
      headers: {
        "Content-Type": "application/json",
        ...(init?.headers ?? {})
      },
      cache: "no-store"
    });
    const body = await response.text();
    const contentLanguage = response.headers.get("Content-Language");
    return new Response(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json",
        ...(contentLanguage ? { "Content-Language": contentLanguage } : {})
      }
    });
  } catch (error) {
    return Response.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : ui.errors.apiUnavailable
      },
      { status: 502 }
    );
  }
}
