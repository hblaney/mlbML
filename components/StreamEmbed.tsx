"use client";

import { useState } from "react";
import {
  getDefaultEmbedSource,
  hasBuffstreamsFeeds,
  hasExternalTeamFeeds,
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
          {hasBuffstreamsFeeds(sources) ? (
            <p className="muted stream-feed-note">
              Home and Backup use the Buffstreams team broadcast. Link 3 and Link 4 are alternate feeds.
            </p>
          ) : hasExternalTeamFeeds(sources) ? (
            <p className="muted stream-feed-note">
              Home and Away open the team broadcast on MLB Webcast. Link 3 and Link 4 stay embedded here.
            </p>
          ) : null}
        </>
      ) : null}
    </div>
  );
}
