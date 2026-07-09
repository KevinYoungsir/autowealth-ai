const RESEARCH_API_BASE_URL =
  process.env.RESEARCH_API_BASE_URL ?? "http://127.0.0.1:8001";

export async function proxyResearchJson(path: string, init?: RequestInit) {
  try {
    const response = await fetch(`${RESEARCH_API_BASE_URL}${path}`, {
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
