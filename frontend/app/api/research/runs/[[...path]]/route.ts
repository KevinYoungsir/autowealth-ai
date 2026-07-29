import { proxyResearchJson } from "@/lib/server-api";

type RouteContext = {
  params: Promise<{
    path?: string[];
  }>;
};

export async function GET(request: Request, context: RouteContext) {
  const { path = [] } = await context.params;
  const suffix = path.map((segment) => encodeURIComponent(segment)).join("/");
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  const proxyPath = `/research/runs${suffix ? `/${suffix}` : ""}${query ? `?${query}` : ""}`;
  return proxyResearchJson(proxyPath);
}
