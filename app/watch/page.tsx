import { getTeam, predictions, streamEmbeds } from "@/lib/data";

export default function WatchPage() {
  return (
    <main className="shell stack">
      <section className="panel strong">
        <p className="eyebrow">Approved embeds only</p>
        <h1>Watch</h1>
        <p className="lead">
          Stream cards are designed for MLB Webcast-approved iframe URLs. Keep this as an embed integration so the
          provider controls tokens, bandwidth, and source changes.
        </p>
      </section>

      <section className="grid two">
        {streamEmbeds.map((stream) => {
          const game = predictions.find((item) => item.id === stream.gameId);
          const away = game ? getTeam(game.awayTeam) : null;
          const home = game ? getTeam(game.homeTeam) : null;

          return (
            <article className="panel stack" key={`${stream.gameId}-${stream.feed}`}>
              <div className="matchup">
                <div>
                  <h2>{stream.label}</h2>
                  <p className="muted">{away?.name} @ {home?.name}</p>
                </div>
                <span className="badge">{stream.provider}</span>
              </div>
              <div className="iframe-wrap">
                <iframe
                  src={stream.embedUrl}
                  title={stream.label}
                  allow="encrypted-media; fullscreen"
                  allowFullScreen
                  referrerPolicy="strict-origin-when-cross-origin"
                />
              </div>
              <p className="muted">
                Replace this sample URL with the approved embed URL/API response provided by MLB Webcast.
              </p>
            </article>
          );
        })}
      </section>
    </main>
  );
}
