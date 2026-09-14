"use client";

import { useEffect, useState } from "react";
import {
  getDefaultEmbedSource,
  hasBuffstreamsFeeds,
  type StreamLink
} from "@/lib/watch-streams";

type StreamEmbedProps = {
  title: string;
  sources: StreamLink[];
  compact?: boolean;
};

export function StreamEmbed({ title, sources, compact = false }: StreamEmbedProps) {
  const [activeSource, setActiveSource] = useState(() => getDefaultEmbedSource(sources));

  // When the multi-view swaps games, reset to that card's default feed.
  useEffect(() => {
    setActiveSource(getDefaultEmbedSource(sources));
  }, [sources]);

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
    <div className={compact ? "stream-player compact" : "stream-player"}>
      <div className="iframe-wrap">
        <iframe
          allow="autoplay; encrypted-media; fullscreen"
          allowFullScreen
          key={activeSource}
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
                onClick={(event) => {
                  event.preventDefault();
                  event.stopPropagation();
                  handleSourceClick(source);
                }}
                type="button"
              >
                {source.external ? `${source.label} ↗` : source.label}
              </button>
            ))}
          </div>
          {compact ? null : (
            <p className="muted stream-feed-note">
              Buttons are that club&apos;s feed (scraped live from MLB Webcast). If one is blank,
              try the other team or Open webcast.
              {hasBuffstreamsFeeds(sources) ? " Backup is an extra source when available." : ""}
            </p>
          )}
        </>
      ) : null}
    </div>
  );
}
