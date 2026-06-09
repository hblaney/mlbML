export const MLB_WEBCAST_ORIGIN = "https://mlbwebcast.com";

const ALLOWED_UPSTREAM_HOSTS = new Set([
  "mlbwebcast.com",
  "www.mlbwebcast.com",
  "cdn.jsdelivr.net"
]);

const STREAM_HOST_SUFFIXES = [".m3u8", ".ts", ".m4s", ".mp4", ".key"];

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
      "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
    Accept: "*/*",
    Referer: `${MLB_WEBCAST_ORIGIN}${refererPath}`
  };
}

export function rewriteEmbedHtml(html: string, slug: string) {
  const refererPath = `/stream/${slug}.html`;

  return html
    .replaceAll("//cdn.jsdelivr.net", "https://cdn.jsdelivr.net")
    .replaceAll("fetch('check_stream.php", "fetch('/api/stream/upstream/check_stream.php")
    .replaceAll('fetch("check_stream.php', 'fetch("/api/stream/upstream/check_stream.php');
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
