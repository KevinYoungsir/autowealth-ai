const DEFAULT_RESEARCH_API_BASE_URL = "http://127.0.0.1:8001";

const RESEARCH_API_BASE_URL = (
  process.env.NEXT_PUBLIC_API_BASE_URL?.trim() ||
  process.env.RESEARCH_API_BASE_URL?.trim() ||
  DEFAULT_RESEARCH_API_BASE_URL
).replace(/\/+$/, "");

function buildResearchApiUrl(path: string) {
  if (path !== "/research" && !path.startsWith("/research/")) {
    throw new Error("Only research API paths can be proxied");
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
    return new Response(body, {
      status: response.status,
      headers: {
        "Content-Type": response.headers.get("Content-Type") ?? "application/json"
      }
    });
  } catch (error) {
    return Response.json(
      {
        detail:
          error instanceof Error
            ? error.message
            : "Research API is unavailable"
      },
      { status: 502 }
    );
  }
}
