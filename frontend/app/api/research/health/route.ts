import { proxyResearchJson } from "@/lib/server-api";

export async function GET() {
  return proxyResearchJson("/research/health");
}
