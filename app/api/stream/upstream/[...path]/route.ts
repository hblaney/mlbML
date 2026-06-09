import {
  assertAllowedStreamUrl,
  assertAllowedUpstreamUrl,
  MLB_WEBCAST_ORIGIN,
  proxyHlsUrl,
  upstreamFetchHeaders
} from "@/lib/stream-proxy";

type UpstreamRouteProps = {
  params: Promise<{ path: string[] }>;
};

export async function GET(request: Request, { params }: UpstreamRouteProps) {
  const { path } = await params;
  const upstreamPath = path.join("/");
  const { searchParams } = new URL(request.url);
  const query = searchParams.toString();
  const upstreamUrl = `${MLB_WEBCAST_ORIGIN}/${upstreamPath}${query ? `?${query}` : ""}`;

  try {
    assertAllowedUpstreamUrl(upstreamUrl);
  } catch {
    return new Response("Forbidden upstream target", { status: 403 });
  }

  const upstream = await fetch(upstreamUrl, {
    cache: "no-store",
    headers: upstreamFetchHeaders()
  });

  if (!upstream.ok) {
    return new Response("Upstream request failed", { status: upstream.status });
  }

  const contentType = upstream.headers.get("content-type") ?? "application/octet-stream";

  if (contentType.includes("json") || upstreamPath.endsWith(".php")) {
    try {
      const payload = (await upstream.json()) as { url?: string };
      if (payload.url) {
        const allowed = assertAllowedStreamUrl(payload.url);
        payload.url = proxyHlsUrl(allowed.toString());
      }

      return Response.json(payload, {
        headers: { "Cache-Control": "no-store" }
      });
    } catch {
      return new Response("Invalid upstream JSON", { status: 502 });
    }
  }

  const body = await upstream.arrayBuffer();
  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    }
  });
}
