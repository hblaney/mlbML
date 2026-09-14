"""Refresh streame channel fallbacks from today's mlbwebcast *2 pages.

Vercel is often 403'd by mlbwebcast, so the embed route uses this map when
the live scrape fails. Channels remap daily — run this with the board update.
"""

from __future__ import annotations

import re
import ssl
import sys
import urllib.request
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "lib" / "stream-embed-fallbacks.ts"

SLUGS = [
    "diamondbacks",
    "athletics",
    "braves",
    "orioles",
    "redsox",
    "cubs",
    "whitesox",
    "reds",
    "guardians",
    "rockies",
    "tigers",
    "astros",
    "royals",
    "angels",
    "dodgers",
    "marlins",
    "brewers",
    "twins",
    "mets",
    "yankees",
    "phillies",
    "pirates",
    "padres",
    "giants",
    "mariners",
    "cardinals",
    "rays",
    "rangers",
    "jays",
    "nationals",
]

IFRAME_SRC = re.compile(r'<iframe[^>]+src=["\']([^"\']+)["\']', re.I)
UA = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
    "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
)


def fetch(url: str) -> str:
    req = urllib.request.Request(
        url,
        headers={"User-Agent": UA, "Referer": "https://mlbwebcast.com/"},
    )
    ctx = ssl.create_default_context()
    with urllib.request.urlopen(req, timeout=15, context=ctx) as response:
        return response.read().decode("utf-8", "replace")


def channel_for(slug: str) -> str | None:
    html = fetch(f"https://mlbwebcast.com/stream/{slug}2.html")
    for src in IFRAME_SRC.findall(html):
        if "streame.center" in src or "embedstreams" in src:
            if src.startswith("//"):
                return f"https:{src}"
            return src
    return None


def render(mapping: dict[str, str]) -> str:
    today = date.today().isoformat()
    lines = [
        "/**",
        " * Last-resort embed URLs for when live mlbwebcast scrape fails (Vercel 403).",
        f" * Refreshed {today} from /stream/{{slug}}2.html — these remap daily.",
        " * Prefer live scrape in /api/stream/embed; do not treat this map as truth.",
        " * Regenerate with: python3 scripts/model/refresh_stream_fallbacks.py",
        " */",
        f'export const STREAM_FALLBACKS_REFRESHED_AT = "{today}";',
        "",
        "export const STREAM_IFRAME_FALLBACKS: Record<string, string> = {",
    ]
    for slug in SLUGS:
        url = mapping[slug]
        lines.append(f'  {slug}2: "{url}",')
        lines.append(f'  {slug}3: "{url}",')
    lines.extend(
        [
            '  mlbnetwork2: "https://embedstreams.top/embed/alpha/mlb-network/1",',
            '  mlbnetwork3: "https://embedstreams.top/embed/alpha/mlb-network/1"',
            "};",
            "",
            "export function iframeFallbackForSlug(slug: string): string | null {",
            "  const key = slug.toLowerCase();",
            "  return STREAM_IFRAME_FALLBACKS[key] ?? STREAM_IFRAME_FALLBACKS[`${key.replace(/\\d+$/, \"\")}2`] ?? null;",
            "}",
            "",
        ]
    )
    return "\n".join(lines)


def main() -> int:
    mapping: dict[str, str] = {}
    for slug in SLUGS:
        try:
            url = channel_for(slug)
        except Exception as exc:
            print(f"{slug}2 scrape failed: {exc}", file=sys.stderr)
            continue
        if not url:
            print(f"{slug}2: no streame iframe", file=sys.stderr)
            continue
        mapping[slug] = url
        print(f"{slug}2 -> {url}")

    if len(mapping) < 20:
        print("too few channels scraped; leaving existing fallbacks", file=sys.stderr)
        return 0

    OUT_PATH.write_text(render(mapping), encoding="utf-8")
    print(f"wrote {OUT_PATH} ({len(mapping)} teams)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
