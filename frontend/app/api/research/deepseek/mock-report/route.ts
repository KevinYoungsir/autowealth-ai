import { proxyResearchJson } from "@/lib/server-api";

export async function POST(request: Request) {
  const body = await request.json();
  return proxyResearchJson("/research/deepseek/mock-report", {
    method: "POST",
    body: JSON.stringify(body)
  });
}
