import type { BuffstreamsMatch } from "./buffstreams";

const MLB_WEBCAST_ORIGIN = "https://mlbwebcast.com";

export type StreamLink = {
  label: string;
  url: string;
  external?: boolean;
};

export type WatchStreamSource = {
  livePageUrl: string;
  sources: StreamLink[];
};

type TeamStreamConfig = {
  liveSlug: string;
  streamSlug: string;
};

const teamStreamConfig: Record<string, TeamStreamConfig> = {
  ari: { liveSlug: "arizona-diamondbacks", streamSlug: "diamondbacks" },
  ath: { liveSlug: "oakland-athletics", streamSlug: "athletics" },
  atl: { liveSlug: "atlanta-braves", streamSlug: "braves" },
  bal: { liveSlug: "baltimore-orioles", streamSlug: "orioles" },
  bos: { liveSlug: "boston-red-sox", streamSlug: "redsox" },
  chc: { liveSlug: "chicago-cubs", streamSlug: "cubs" },
  cws: { liveSlug: "chicago-white-sox", streamSlug: "whitesox" },
  cin: { liveSlug: "cincinnati-reds", streamSlug: "reds" },
  cle: { liveSlug: "cleveland-guardians", streamSlug: "guardians" },
  col: { liveSlug: "colorado-rockies", streamSlug: "rockies" },
  det: { liveSlug: "detroit-tigers", streamSlug: "tigers" },
  hou: { liveSlug: "houston-astros", streamSlug: "astros" },
  kc: { liveSlug: "kansas-city-royals", streamSlug: "royals" },
  laa: { liveSlug: "los-angeles-angels", streamSlug: "angels" },
  lad: { liveSlug: "los-angeles-dodgers", streamSlug: "dodgers" },
  mia: { liveSlug: "miami-marlins", streamSlug: "marlins" },
  mil: { liveSlug: "milwaukee-brewers", streamSlug: "brewers" },
  min: { liveSlug: "minnesota-twins", streamSlug: "twins" },
  nym: { liveSlug: "new-york-mets", streamSlug: "mets" },
  nyy: { liveSlug: "new-york-yankees", streamSlug: "yankees" },
  phi: { liveSlug: "philadelphia-phillies", streamSlug: "phillies" },
  pit: { liveSlug: "pittsburgh-pirates", streamSlug: "pirates" },
  sd: { liveSlug: "san-diego-padres", streamSlug: "padres" },
  sf: { liveSlug: "san-francisco-giants", streamSlug: "giants" },
  sea: { liveSlug: "seattle-mariners", streamSlug: "mariners" },
  stl: { liveSlug: "st-louis-cardinals", streamSlug: "cardinals" },
  tb: { liveSlug: "tampa-bay-rays", streamSlug: "rays" },
  tex: { liveSlug: "texas-rangers", streamSlug: "rangers" },
  tor: { liveSlug: "toronto-blue-jays", streamSlug: "jays" },
  wsh: { liveSlug: "washington-nationals", streamSlug: "nationals" }
};

function embedPath(streamSlug: string) {
  return `/api/stream/embed/${streamSlug}`;
}

function webcastStreamUrl(streamSlug: string) {
  return `${MLB_WEBCAST_ORIGIN}/stream/${streamSlug}.html`;
}

function buildTeamStream(
  config: TeamStreamConfig,
  opponentTeamId?: string,
  buffstreams?: BuffstreamsMatch | null
): WatchStreamSource {
  const sources: StreamLink[] = [];

  if (buffstreams?.streamIds.length) {
    sources.push({
      label: "Home",
      url: embedPath(`buff${buffstreams.streamIds[0]}`)
    });

    if (buffstreams.streamIds[1]) {
      sources.push({
        label: "Backup",
        url: embedPath(`buff${buffstreams.streamIds[1]}`)
      });
    }
  }

  sources.push(
    { label: "Link 3", url: embedPath(`${config.streamSlug}2`) },
    { label: "Link 4", url: embedPath(`${config.streamSlug}3`) }
  );

  if (!buffstreams?.streamIds.length) {
    sources.push({
      label: "Home",
      url: webcastStreamUrl(config.streamSlug),
      external: true
    });

    const opponentConfig = opponentTeamId ? teamStreamConfig[opponentTeamId] : undefined;
    if (opponentConfig) {
      sources.push({
        label: "Away",
        url: webcastStreamUrl(opponentConfig.streamSlug),
        external: true
      });
    }
  }

  return {
    livePageUrl: buffstreams?.pageUrl ?? `${MLB_WEBCAST_ORIGIN}/${config.liveSlug}-live/`,
    sources
  };
}

export const mlbNetworkStream: WatchStreamSource = {
  livePageUrl: `${MLB_WEBCAST_ORIGIN}/mlb-network-live/`,
  sources: [
    { label: "Link 3", url: embedPath("mlbnetwork2") },
    { label: "Link 4", url: embedPath("mlbnetwork3") },
    { label: "Home", url: webcastStreamUrl("mlbnetwork"), external: true }
  ]
};

export function getTeamWatchStream(
  teamId: string,
  opponentTeamId?: string,
  buffstreams?: BuffstreamsMatch | null
) {
  const config = teamStreamConfig[teamId];
  if (!config) {
    return undefined;
  }

  return buildTeamStream(config, opponentTeamId, buffstreams);
}

export function hasBuffstreamsFeeds(sources: StreamLink[]) {
  return sources.some((source) => source.url.includes("/api/stream/embed/buff"));
}

export function getDefaultEmbedSource(sources: StreamLink[]) {
  return sources.find((source) => !source.external)?.url ?? "";
}

export function hasExternalTeamFeeds(sources: StreamLink[]) {
  return sources.some((source) => source.external);
}
