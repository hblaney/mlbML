import { resolveStreamManifest } from "@/lib/stream-proxy";

// Node runtime: Edge IPs are often Cloudflare-blocked by MLB Webcast.
export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type ManifestRouteProps = {
  params: Promise<{ slug: string }>;
};

const SLUG_PATTERN = /^[a-z0-9]+$/i;

export async function GET(_request: Request, { params }: ManifestRouteProps) {
  const { slug } = await params;

  if (!SLUG_PATTERN.test(slug)) {
    return Response.json({ url: null, message: "Invalid stream slug." }, { status: 400 });
  }

  const manifest = await resolveStreamManifest(slug);

  return Response.json(manifest, {
    status: manifest.url ? 200 : 503,
    headers: { "Cache-Control": "no-store" }
  });
}
