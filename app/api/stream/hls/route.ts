import {
  assertAllowedStreamUrl,
  fetchStreamAsset,
  looksLikePlaylist,
  rewritePlaylistUrls
} from "@/lib/stream-proxy";

export const runtime = "edge";
export const dynamic = "force-dynamic";

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const rawUrl = searchParams.get("url");

  if (!rawUrl) {
    return new Response("Missing stream URL", { status: 400 });
  }

  let targetUrl: URL;

  try {
    targetUrl = assertAllowedStreamUrl(rawUrl);
  } catch {
    return new Response("Forbidden stream URL", { status: 403 });
  }

  const upstream = await fetchStreamAsset(targetUrl.toString());

  if (!upstream.ok) {
    return new Response("Stream request failed", { status: upstream.status });
  }

  const contentType = upstream.headers.get("content-type") ?? "application/octet-stream";
  const body = await upstream.arrayBuffer();
  const bodyText = new TextDecoder().decode(body);

  if (looksLikePlaylist(contentType, bodyText)) {
    const rewritten = rewritePlaylistUrls(bodyText, targetUrl.toString());
    return new Response(rewritten, {
      status: 200,
      headers: {
        "Content-Type": "application/vnd.apple.mpegurl",
        "Cache-Control": "no-store"
      }
    });
  }

  return new Response(body, {
    status: 200,
    headers: {
      "Content-Type": contentType,
      "Cache-Control": "no-store"
    }
  });
}
