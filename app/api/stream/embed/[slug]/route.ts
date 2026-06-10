import {
  buildEmbedPlayerHtml,
  buildIframeEmbedHtml,
  fetchMlbWebcast,
  isBuffstreamsSlug,
  parseStreamTokens,
  resolveIframeEmbedUrl
} from "@/lib/stream-proxy";

export const runtime = "edge";
export const dynamic = "force-dynamic";

type EmbedRouteProps = {
  params: Promise<{ slug: string }>;
};

const SLUG_PATTERN = /^[a-z0-9]+$/i;

export async function GET(_request: Request, { params }: EmbedRouteProps) {
  const { slug } = await params;

  if (!SLUG_PATTERN.test(slug)) {
    return new Response("Invalid stream slug", { status: 400 });
  }

  if (isBuffstreamsSlug(slug)) {
    return new Response(buildEmbedPlayerHtml(slug), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store"
      }
    });
  }

  const iframeEmbedUrl = await resolveIframeEmbedUrl(slug);
  if (iframeEmbedUrl) {
    return new Response(buildIframeEmbedHtml(iframeEmbedUrl), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store"
      }
    });
  }

  const refererPath = `/stream/${slug}.html`;
  const pageResponse = await fetchMlbWebcast(`stream/${slug}.html`, refererPath);

  if (!pageResponse.ok) {
    return new Response("Stream page unavailable", { status: pageResponse.status });
  }

  if (!parseStreamTokens(await pageResponse.text())) {
    return new Response("Stream page unavailable", { status: 404 });
  }

  return new Response(buildEmbedPlayerHtml(slug), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
