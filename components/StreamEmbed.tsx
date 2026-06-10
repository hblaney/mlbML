"use client";

import { useState } from "react";

type StreamEmbedProps = {
  title: string;
  embedUrl: string;
  alternates?: string[];
};

export function StreamEmbed({ title, embedUrl, alternates = [] }: StreamEmbedProps) {
  const sources = [embedUrl, ...alternates];
  const [activeSource, setActiveSource] = useState(embedUrl);

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
        <div className="stream-source-row">
          {sources.map((source, index) => (
            <button
              className={source === activeSource ? "stream-source active" : "stream-source"}
              key={source}
              onClick={() => setActiveSource(source)}
              type="button"
            >
              {`Link ${index + 3}`}
            </button>
          ))}
        </div>
      ) : null}
    </div>
  );
}
