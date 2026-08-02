"use client";

import { useState } from "react";
import {
  getDefaultEmbedSource,
  hasBuffstreamsFeeds,
  type StreamLink
} from "@/lib/watch-streams";

type StreamEmbedProps = {
  title: string;
  sources: StreamLink[];
};

export function StreamEmbed({ title, sources }: StreamEmbedProps) {
  const [activeSource, setActiveSource] = useState(() => getDefaultEmbedSource(sources));

  if (sources.length === 0 || !activeSource) {
    return null;
  }

  function handleSourceClick(source: StreamLink) {
    if (source.external) {
      window.open(source.url, "_blank", "noopener,noreferrer");
      return;
    }

    setActiveSource(source.url);
  }

  return (
    <div className="stream-player">
      <div className="iframe-wrap">
        <iframe
          allow="encrypted-media; fullscreen"
          allowFullScreen
          key={activeSource}
          referrerPolicy="strict-origin-when-cross-origin"
          src={activeSource}
          title={title}
        />
      </div>
      {sources.length > 1 ? (
        <>
          <div className="stream-source-row">
            {sources.map((source) => (
              <button
                className={
                  source.external
                    ? "stream-source external"
                    : source.url === activeSource
                      ? "stream-source active"
                      : "stream-source"
                }
                key={`${source.label}-${source.url}`}
                onClick={() => handleSourceClick(source)}
                type="button"
              >
                {source.external ? `${source.label} ↗` : source.label}
              </button>
            ))}
          </div>
          <p className="muted stream-feed-note">
            Home is the default feed. HD is an alternate. If one is blank, try another button — or Open
            site.
            {hasBuffstreamsFeeds(sources) ? " Backup is an extra source when available." : ""}
          </p>
        </>
      ) : null}
    </div>
  );
}
