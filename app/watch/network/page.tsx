import Link from "next/link";
import { StreamEmbed } from "@/components/StreamEmbed";
import { mlbNetworkStream } from "@/lib/watch-streams";

export default function WatchNetworkPage() {
  return (
    <main className="shell stack">
      <section className="panel strong team-stream-hero">
        <div>
          <p className="eyebrow">National feed</p>
          <h1>MLB Network</h1>
          <p className="lead">Embedded player with source links.</p>
          <div className="stream-actions">
            <Link href="/watch">Back to teams</Link>
            <a href={mlbNetworkStream.livePageUrl} rel="noopener noreferrer" target="_blank">
              Open on MLB Webcast
            </a>
          </div>
        </div>
      </section>

      <section className="panel">
        <StreamEmbed sources={mlbNetworkStream.sources} title="MLB Network stream" />
      </section>
    </main>
  );
}
