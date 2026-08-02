import { STREAM_IFRAME_FALLBACKS, iframeFallbackForSlug } from "@/lib/stream-embed-fallbacks";
import {
  buildEmbedPlayerHtml,
  buildIframeEmbedHtml,
  isAllowedIframeHost,
  isBuffstreamsSlug,
  resolveIframeEmbedUrl
} from "@/lib/stream-proxy";

// Node runtime: Vercel Edge IPs are often Cloudflare-blocked by MLB Webcast.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type EmbedRouteProps = {
  params: Promise<{ slug: string }>;
};

const SLUG_PATTERN = /^[a-z0-9]+$/i;

function unavailableHtml(slug: string) {
  const openUrl = `https://mlbwebcast.com/stream/${slug}.html`;
  const alt = iframeFallbackForSlug(`${slug.replace(/\d+$/, "")}2`) ?? iframeFallbackForSlug(slug);
  return `<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#000;color:#cbd5e1;font-family:system-ui,sans-serif;padding:24px;text-align:center}
a{color:#fff}
.alt{margin-top:14px}
</style></head><body>
<div>
  <p>Could not load this feed through the site proxy.</p>
  <p><a href="${openUrl}" target="_blank" rel="noopener noreferrer">Open on MLB Webcast ↗</a></p>
  ${alt ? `<p class="alt"><a href="${alt}" target="_blank" rel="noopener noreferrer">Try alternate player ↗</a></p>` : ""}
</div>
</body></html>`;
}

export async function GET(_request: Request, { params }: EmbedRouteProps) {
  const { slug } = await params;
  const normalized = slug.toLowerCase();

  if (!SLUG_PATTERN.test(normalized)) {
    return new Response("Invalid stream slug", { status: 400 });
  }

  if (isBuffstreamsSlug(normalized)) {
    return new Response(buildEmbedPlayerHtml(normalized), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store"
      }
    });
  }

  // 1) Live scrape of the webcast page for its iframe player.
  try {
    const iframeEmbedUrl = await resolveIframeEmbedUrl(normalized);
    if (iframeEmbedUrl) {
      return new Response(buildIframeEmbedHtml(iframeEmbedUrl), {
        status: 200,
        headers: {
          "Content-Type": "text/html; charset=utf-8",
          "Cache-Control": "no-store"
        }
      });
    }
  } catch {
    // Continue to fallbacks — production scrapes are often blocked.
  }

  // 2) Static streame/embedstreams map (works even when mlbwebcast.com blocks the server).
  const fallback = STREAM_IFRAME_FALLBACKS[normalized];
  if (fallback) {
    try {
      const host = new URL(fallback).hostname;
      if (isAllowedIframeHost(host)) {
        return new Response(buildIframeEmbedHtml(fallback), {
          status: 200,
          headers: {
            "Content-Type": "text/html; charset=utf-8",
            "Cache-Control": "public, max-age=60"
          }
        });
      }
    } catch {
      // ignore bad fallback URL
    }
  }

  // 3) Primary (unnumbered) feeds use the HLS token player — don't preflight tokens
  //    (preflight was returning "Stream page unavailable" whenever Cloudflare challenged).
  if (!/\d$/.test(normalized)) {
    return new Response(buildEmbedPlayerHtml(normalized), {
      status: 200,
      headers: {
        "Content-Type": "text/html; charset=utf-8",
        "Cache-Control": "no-store"
      }
    });
  }

  // 4) Last resort: helpful HTML, never a bare error string in the iframe.
  return new Response(unavailableHtml(normalized), {
    status: 200,
    headers: {
      "Content-Type": "text/html; charset=utf-8",
      "Cache-Control": "no-store"
    }
  });
}
