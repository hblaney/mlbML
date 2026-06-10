export const MLB_WEBCAST_ORIGIN = "https://mlbwebcast.com";
export const BUFFSTREAMS_PLAYLIST_ORIGIN = "https://chatgpt.hereisman.net";
export const BUFFSTREAMS_REFERER = "https://gooz.aapmains.net/";

const ALLOWED_UPSTREAM_HOSTS = new Set([
  "mlbwebcast.com",
  "www.mlbwebcast.com",
  "cdn.jsdelivr.net"
]);

const STREAM_HOST_SUFFIXES = [".m3u8", ".ts", ".m4s", ".mp4", ".key"];
const STREAM_TOKEN_PATTERN = /var _d=\[(\d+),'(\d+)','([a-f0-9]+)'\]/i;
const IFRAME_SRC_PATTERN = /<iframe[^>]+src=['"]([^'"]+)['"]/i;

const ALLOWED_IFRAME_HOSTS = new Set([
  "streams.center",
  "www.streams.center",
  "embedstreams.top",
  "www.embedstreams.top"
]);

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

  const host = hostname.toLowerCase();

  return (
    host.endsWith(".cloudfront.net") ||
    host.endsWith(".akamaized.net") ||
    host.endsWith(".fastly.net") ||
    host.endsWith(".llnwi.net") ||
    host.endsWith(".cloudflare.com") ||
    host.endsWith(".googlevideo.com") ||
    host.endsWith(".hereisman.net") ||
    host.endsWith(".r2.cloudflarestorage.com") ||
    host.includes("kamfir")
  );
}

function isBuffstreamsStreamHost(hostname: string) {
  const host = hostname.toLowerCase();
  return host.endsWith(".hereisman.net") || host.includes("kamfir") || host.endsWith(".r2.cloudflarestorage.com");
}

export function isBuffstreamsSlug(slug: string) {
  return /^buff\d+$/i.test(slug);
}

export function buffstreamsStreamId(slug: string) {
  return slug.replace(/^buff/i, "");
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

  if (!isAllowedUpstreamHost(parsed.hostname)) {
    throw new Error("Stream host is not allowed");
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
  const referer = isBuffstreamsStreamHost(new URL(targetUrl).hostname)
    ? BUFFSTREAMS_REFERER
    : `${MLB_WEBCAST_ORIGIN}${refererPath}`;

  return fetch(fetchUrl, {
    cache: "no-store",
    redirect: "follow",
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
      Accept: "*/*",
      Referer: referer,
      Origin: new URL(referer).origin
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

export function isAllowedIframeHost(hostname: string) {
  return ALLOWED_IFRAME_HOSTS.has(hostname.toLowerCase());
}

export function parseIframeEmbedUrl(html: string) {
  const match = html.match(IFRAME_SRC_PATTERN);
  if (!match) {
    return null;
  }

  const rawSrc = match[1].trim();
  if (!rawSrc || rawSrc.startsWith("/cdn-cgi/")) {
    return null;
  }

  try {
    const parsed = new URL(rawSrc, MLB_WEBCAST_ORIGIN);
    if (!isAllowedIframeHost(parsed.hostname)) {
      return null;
    }

    return parsed.toString();
  } catch {
    return null;
  }
}

export async function resolveIframeEmbedUrl(slug: string) {
  const refererPath = `/stream/${slug}.html`;
  const pageResponse = await fetchMlbWebcast(`stream/${slug}.html`, refererPath);

  if (!pageResponse.ok) {
    return null;
  }

  return parseIframeEmbedUrl(await pageResponse.text());
}

export function buildIframeEmbedHtml(embedUrl: string) {
  const safeUrl = embedUrl.replace(/"/g, "&quot;");

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<style>
*{margin:0;padding:0;box-sizing:border-box}
html,body{height:100%;background:#000;overflow:hidden}
iframe{width:100%;height:100%;border:0}
</style>
</head>
<body>
<iframe allow="encrypted-media; fullscreen" allowfullscreen src="${safeUrl}"></iframe>
</body>
</html>`;
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

export async function resolveBuffstreamsManifest(streamId: string): Promise<StreamManifest> {
  const playlistUrl = `${BUFFSTREAMS_PLAYLIST_ORIGIN}/playlist/${streamId}/load-playlist`;

  try {
    const response = await fetchStreamAsset(playlistUrl);

    if (!response.ok) {
      return {
        url: null,
        upstreamStatus: response.status,
        message: "Buffstreams feed is unavailable right now."
      };
    }

    return {
      url: proxyHlsUrl(playlistUrl),
      message: "ok"
    };
  } catch {
    return {
      url: null,
      message: "Could not load the Buffstreams feed."
    };
  }
}

export async function resolveStreamManifest(slug: string): Promise<StreamManifest> {
  if (isBuffstreamsSlug(slug)) {
    return resolveBuffstreamsManifest(buffstreamsStreamId(slug));
  }
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

export function buildEmbedPlayerHtml(slug: string, manifestPath?: string) {
  const safeSlug = slug.replace(/[^a-z0-9]/gi, "");
  const manifestUrl = manifestPath ?? `/api/stream/manifest/${safeSlug}`;

  return `<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<script src="https://cdn.jsdelivr.net/npm/hls.js@1.5.17/dist/hls.min.js"></script>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body,html{background:#000;overflow:hidden;height:100%;color:#fff;font-family:system-ui,sans-serif}
#player-wrap{width:100%;height:100vh;position:relative}
#player{width:100%;height:100%}
#player video{width:100%;height:100%;background:#000}
#status{position:absolute;inset:0;display:flex;align-items:center;justify-content:center;padding:24px;text-align:center;color:#cbd5e1;background:#000;z-index:1}
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
  var playerEl=document.getElementById('player');
  function showError(message){
    statusEl.textContent=message;
    statusEl.style.display='flex';
  }
  function startPlayback(source){
    var video=document.createElement('video');
    video.controls=true;
    video.playsInline=true;
    video.setAttribute('playsinline','');
    playerEl.appendChild(video);
    if(window.Hls&&Hls.isSupported()){
      var hls=new Hls({
        enableWorker:true,
        liveSyncDurationCount:3,
        manifestLoadingMaxRetry:8,
        manifestLoadingRetryDelay:1000,
        levelLoadingMaxRetry:8,
        levelLoadingRetryDelay:1000,
        fragLoadingMaxRetry:8,
        fragLoadingRetryDelay:1000
      });
      hls.loadSource(source);
      hls.attachMedia(video);
      hls.on(Hls.Events.MANIFEST_PARSED,function(){
        statusEl.style.display='none';
        video.play().catch(function(){});
      });
      hls.on(Hls.Events.ERROR,function(_event,data){
        if(data.fatal){
          showError('Playback failed. Stream may be offline or blocked.');
        }
      });
      return;
    }
    if(video.canPlayType('application/vnd.apple.mpegurl')){
      video.src=source;
      video.addEventListener('loadedmetadata',function(){
        statusEl.style.display='none';
        video.play().catch(function(){});
      });
      video.addEventListener('error',function(){
        showError('Playback failed. Stream may be offline or blocked.');
      });
      return;
    }
    showError('This browser does not support HLS playback.');
  }
  fetch('${manifestUrl}',{cache:'no-store'})
    .then(function(response){return response.json();})
    .then(function(data){
      if(!data.url){
        showError(data.message||'Stream unavailable.');
        return;
      }
      startPlayback(data.url);
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
