import { buildEmbedPlayerHtml } from "@/lib/stream-proxy";

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

  return new Response(buildEmbedPlayerHtml(slug), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
