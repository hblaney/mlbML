import { STREAM_IFRAME_FALLBACKS, iframeFallbackForSlug } from "@/lib/stream-embed-fallbacks";
import {
  buildEmbedPlayerHtml,
  buildIframeEmbedHtml,
  isAllowedIframeHost,
  isBuffstreamsSlug,
  proxyHlsUrl,
  resolveIframeEmbedUrl,
  resolveStreamePlayback
} from "@/lib/stream-proxy";

// Node runtime: Vercel Edge IPs are often Cloudflare-blocked by MLB Webcast.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type EmbedRouteProps = {
  params: Promise<{ slug: string }>;
};

const SLUG_PATTERN = /^[a-z0-9]+$/i;
const NO_STORE = {
  "Content-Type": "text/html; charset=utf-8",
  "Cache-Control": "no-store"
} as const;

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

function html(body: string) {
  return new Response(body, { status: 200, headers: NO_STORE });
}

async function channelUrlForSlug(slug: string): Promise<string | null> {
  const isNumbered = /\d$/.test(slug);
  const scrapeSlugs = isNumbered ? [slug] : [`${slug}2`, slug];

  for (const candidate of scrapeSlugs) {
    try {
      const iframeEmbedUrl = await resolveIframeEmbedUrl(candidate);
      if (iframeEmbedUrl) {
        return iframeEmbedUrl;
      }
    } catch {
      // Vercel is often 403'd by mlbwebcast — use today's fallback map.
    }
  }

  return (
    STREAM_IFRAME_FALLBACKS[slug] ??
    STREAM_IFRAME_FALLBACKS[`${slug.replace(/\d+$/, "")}2`] ??
    null
  );
}

export async function GET(_request: Request, { params }: EmbedRouteProps) {
  const { slug } = await params;
  const normalized = slug.toLowerCase();

  if (!SLUG_PATTERN.test(normalized)) {
    return new Response("Invalid stream slug", { status: 400 });
  }

  if (isBuffstreamsSlug(normalized)) {
    return html(buildEmbedPlayerHtml(normalized));
  }

  const channelUrl = await channelUrlForSlug(normalized);

  if (channelUrl) {
    try {
      const host = new URL(channelUrl).hostname;
      if (isAllowedIframeHost(host) && host.includes("streame")) {
        const playback = await resolveStreamePlayback(channelUrl);
        // Prefer our HLS player — streame's Clappr page is ad-heavy and often
        // blank when nested inside this site. Open webcast still works because
        // it is a top-level mlbwebcast page.
        if (playback.m3u8Url) {
          try {
            return html(buildEmbedPlayerHtml(normalized, proxyHlsUrl(playback.m3u8Url)));
          } catch {
            // m3u8 host not allow-listed — fall through
          }
        }
        if (playback.hlsPlayerUrl) {
          return html(buildIframeEmbedHtml(playback.hlsPlayerUrl));
        }
      }

      if (isAllowedIframeHost(new URL(channelUrl).hostname)) {
        return html(buildIframeEmbedHtml(channelUrl));
      }
    } catch {
      // fall through
    }
  }

  if (!/\d$/.test(normalized)) {
    return html(buildEmbedPlayerHtml(normalized));
  }

  return html(unavailableHtml(normalized));
}
