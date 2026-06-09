import {
  MLB_WEBCAST_ORIGIN,
  rewriteEmbedHtml,
  upstreamFetchHeaders
} from "@/lib/stream-proxy";

type EmbedRouteProps = {
  params: Promise<{ slug: string }>;
};

const SLUG_PATTERN = /^[a-z0-9]+$/i;

export async function GET(_request: Request, { params }: EmbedRouteProps) {
  const { slug } = await params;

  if (!SLUG_PATTERN.test(slug)) {
    return new Response("Invalid stream slug", { status: 400 });
  }

  const upstreamUrl = `${MLB_WEBCAST_ORIGIN}/stream/${slug}.html`;
  const upstream = await fetch(upstreamUrl, {
    cache: "no-store",
    headers: upstreamFetchHeaders(`/stream/${slug}.html`)
  });

  if (!upstream.ok) {
    return new Response("Stream page unavailable", { status: upstream.status });
  }

  const html = rewriteEmbedHtml(await upstream.text(), slug);

  return new Response(html, {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
