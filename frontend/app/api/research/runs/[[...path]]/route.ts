import { proxyResearchJson } from "@/lib/server-api";

type RouteContext = {
  params: { path?: string[] };
};

export async function GET(request: Request, context: RouteContext) {
  const suffix = (context.params.path ?? [])
    .map((segment) => encodeURIComponent(segment))
    .join("/");
  const url = new URL(request.url);
  const query = url.searchParams.toString();
  const path = `/research/runs${suffix ? `/${suffix}` : ""}${query ? `?${query}` : ""}`;
  return proxyResearchJson(path);
}
