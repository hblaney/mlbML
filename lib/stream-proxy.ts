export const MLB_WEBCAST_ORIGIN = "https://mlbwebcast.com";

const ALLOWED_UPSTREAM_HOSTS = new Set([
  "mlbwebcast.com",
  "www.mlbwebcast.com",
  "cdn.jsdelivr.net"
]);

const STREAM_HOST_SUFFIXES = [".m3u8", ".ts", ".m4s", ".mp4", ".key"];
const STREAM_TOKEN_PATTERN = /var _d=\[(\d+),'(\d+)','([a-f0-9]+)'\]/i;

export type StreamManifest = {
  url: string | null;
  message: string;
  upstreamStatus?: number;
};

function isPrivateHostname(hostname: string) {
  const host = hostname.toLowerCase();

  return (
    host === "localhost" ||
    host.endsWith(".local") ||
    host.startsWith("127.") ||
    host.startsWith("10.") ||
    host.startsWith("192.168.") ||
    /^172\.(1[6-9]|2\d|3[0-1])\./.test(host)
  );
}

export function isAllowedUpstreamHost(hostname: string) {
  if (ALLOWED_UPSTREAM_HOSTS.has(hostname)) {
    return true;
  }

  return (
    hostname.endsWith(".cloudfront.net") ||
    hostname.endsWith(".akamaized.net") ||
    hostname.endsWith(".fastly.net") ||
    hostname.endsWith(".llnwi.net") ||
    hostname.endsWith(".cloudflare.com") ||
    hostname.endsWith(".googlevideo.com")
  );
}

export function assertAllowedUpstreamUrl(rawUrl: string) {
  let parsed: URL;

  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error("Invalid upstream URL");
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error("Unsupported protocol");
  }

  if (!isAllowedUpstreamHost(parsed.hostname)) {
    throw new Error("Upstream host is not allowed");
  }

  return parsed;
}

export function assertAllowedStreamUrl(rawUrl: string) {
  let parsed: URL;

  try {
    parsed = new URL(rawUrl);
  } catch {
    throw new Error("Invalid stream URL");
  }

  if (parsed.protocol !== "https:" && parsed.protocol !== "http:") {
    throw new Error("Unsupported protocol");
  }

  if (isPrivateHostname(parsed.hostname)) {
    throw new Error("Private stream hosts are not allowed");
  }

  return parsed;
}

export function upstreamFetchHeaders(refererPath = "/stream/") {
  return {
    "User-Agent":
      "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    Accept:
      "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Cache-Control": "no-cache",
    Pragma: "no-cache",
    Referer: `${MLB_WEBCAST_ORIGIN}${refererPath}`,
    Origin: MLB_WEBCAST_ORIGIN,
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "Sec-Fetch-Site": "same-origin",
    "Sec-Fetch-User": "?1",
    "Upgrade-Insecure-Requests": "1"
  };
}

function buildFetchUrl(targetUrl: string) {
  const proxyBase = process.env.STREAM_FETCH_PROXY?.trim();

  if (!proxyBase) {
    return targetUrl;
  }

  const separator = proxyBase.includes("?") ? "&" : "?";
  return `${proxyBase}${separator}url=${encodeURIComponent(targetUrl)}`;
}

export async function fetchStreamAsset(targetUrl: string, refererPath = "/stream/") {
  const fetchUrl = buildFetchUrl(targetUrl);

  return fetch(fetchUrl, {
    cache: "no-store",
    redirect: "follow",
    headers: {
      ...upstreamFetchHeaders(refererPath),
      Accept: "*/*"
    }
  });
}

export async function fetchMlbWebcast(path: string, refererPath?: string) {
  const normalizedPath = path.replace(/^\//, "");
  const targetUrl = `${MLB_WEBCAST_ORIGIN}/${normalizedPath}`;
  const fetchUrl = buildFetchUrl(targetUrl);
  const headers = upstreamFetchHeaders(refererPath ?? `/${normalizedPath}`);

  let lastResponse: Response | null = null;

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const response = await fetch(fetchUrl, {
      cache: "no-store",
      redirect: "follow",
      headers
    });

    lastResponse = response;

    if (response.ok || ![403, 429, 500, 502, 503, 504].includes(response.status)) {
      return response;
    }

    await new Promise((resolve) => setTimeout(resolve, 300));
  }

  return lastResponse as Response;
}

export function parseStreamTokens(html: string) {
  const match = html.match(STREAM_TOKEN_PATTERN);
  if (!match) {
    return null;
  }

  return {
    id: match[1],
    ts: match[2],
    pt: match[3]
  };
}

export async function resolveStreamManifest(slug: string): Promise<StreamManifest> {
  const refererPath = `/stream/${slug}.html`;
  const pageResponse = await fetchMlbWebcast(`stream/${slug}.html`, refererPath);

  if (!pageResponse.ok) {
    const blocked = pageResponse.status === 403;
    return {
      url: null,
      upstreamStatus: pageResponse.status,
      message: blocked
        ? "MLB Webcast blocked the deployed server. Use the direct MLB Webcast link below."
        : "Stream page is unavailable right now."
    };
  }

  const tokens = parseStreamTokens(await pageResponse.text());
  if (!tokens) {
    return {
      url: null,
      message: "Could not read stream settings from MLB Webcast."
    };
  }

  const query = new URLSearchParams({
    id: tokens.id,
    ts: tokens.ts,
    pt: tokens.pt
  });
  const streamResponse = await fetchMlbWebcast(`stream/check_stream.php?${query.toString()}`, refererPath);

  if (!streamResponse.ok) {
    return {
      url: null,
      upstreamStatus: streamResponse.status,
      message:
        streamResponse.status === 404
          ? "No live stream is available for this feed right now."
          : "Stream lookup failed. Try another source link or open MLB Webcast directly."
    };
  }

  const contentType = streamResponse.headers.get("content-type") ?? "";
  if (!contentType.includes("json")) {
    return {
      url: null,
      upstreamStatus: streamResponse.status,
      message: "No live stream is available for this feed right now."
    };
  }

  try {
    const responseText = await streamResponse.text();
    const payload = JSON.parse(responseText.replace(/^\uFEFF/, "").trim()) as { url?: string };
    if (!payload.url) {
      return {
        url: null,
        message: "No live stream is available for this feed right now."
      };
    }

    const allowed = assertAllowedStreamUrl(payload.url);
    return {
      url: proxyHlsUrl(allowed.toString()),
      message: "ok"
    };
  } catch {
    return {
      url: null,
      message: "Stream lookup returned an invalid response."
    };
  }
}

export function buildEmbedPlayerHtml(slug: string) {
  const safeSlug = slug.replace(/[^a-z0-9]/gi, "");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/@clappr/player@0.8/dist/clappr.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body,html{background:#000;overflow:hidden;height:100%;color:#fff;font-family:system-ui,sans-serif}
#player-wrap{width:100%;height:100vh;position:relative}
#player{width:100%;height:100%}
#status{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#cbd5e1;background:#000}
.player-error-screen{display:none!important}
</style>
</head>
<body>
<div id="player-wrap">
  <div id="status">Connecting to stream...</div>
  <div id="player"></div>
</div>
<script>
(function(){
  var slug=${JSON.stringify(safeSlug)};
  var statusEl=document.getElementById('status');
  function showError(message){
    statusEl.textContent=message;
    statusEl.style.display='flex';
  }
  fetch('/api/stream/manifest/'+slug,{cache:'no-store'})
    .then(function(response){return response.json();})
    .then(function(data){
      if(!data.url){
        showError(data.message||'Stream unavailable.');
        return;
      }
      statusEl.style.display='none';
      var player=new Clappr.Player({
        parentId:'#player',
        height:'100%',
        width:'100%',
        autoPlay:false,
        playInline:true
      });
      player.load({source:data.url});
      player.on(Clappr.Events.PLAYER_ERROR,function(){
        showError('Playback failed. Try another source link on the watch page.');
      });
    })
    .catch(function(){
      showError('Could not reach the stream service from this site.');
    });
})();
</script>
</body>
</html>`;
}

export function looksLikePlaylist(contentType: string, body: string) {
  if (contentType.includes("mpegurl") || contentType.includes("m3u8")) {
    return true;
  }

  return body.trimStart().startsWith("#EXTM3U");
}

export function rewritePlaylistUrls(playlist: string, baseUrl: string) {
  const base = new URL(baseUrl);

  return playlist
    .split("\n")
    .map((line) => {
      const trimmed = line.trim();

      if (!trimmed || trimmed.startsWith("#")) {
        if (trimmed.startsWith("#") && trimmed.includes('URI="')) {
          return trimmed.replace(/URI="([^"]+)"/g, (_match, uri: string) => {
            const absolute = new URL(uri, base).toString();
            return `URI="${proxyHlsUrl(absolute)}"`;
          });
        }

        return line;
      }

      const absolute = new URL(trimmed, base).toString();
      return proxyHlsUrl(absolute);
    })
    .join("\n");
}

export function proxyHlsUrl(absoluteUrl: string) {
  assertAllowedStreamUrl(absoluteUrl);
  return `/api/stream/hls?url=${encodeURIComponent(absoluteUrl)}`;
}

export function isStreamAssetPath(pathname: string) {
  const lower = pathname.toLowerCase();
  return STREAM_HOST_SUFFIXES.some((suffix) => lower.endsWith(suffix));
}
