import { getTeam, normalizeTeamId } from "./data";
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

function teamFeed(teamId: string): StreamLink | null {
  const id = normalizeTeamId(teamId);
  const config = teamStreamConfig[id];
  if (!config) return null;
  // Numbered "2" feed is the reliable streame.center fallback. Unnumbered HD and
  // duplicate "3" links were confusing labels that often blanked out.
  return {
    label: getTeam(id).abbreviation,
    url: embedPath(`${config.streamSlug}2`)
  };
}

/**
 * Matchup streams labeled by team abbreviation (DET / ATH), not Home/HD/Link 3.
 * Focus team's feed is listed first (default player).
 */
export function getMatchupWatchStream(options: {
  focusTeamId: string;
  awayTeamId: string;
  homeTeamId: string;
  buffstreams?: BuffstreamsMatch | null;
}): WatchStreamSource | undefined {
  const focusId = normalizeTeamId(options.focusTeamId);
  const awayId = normalizeTeamId(options.awayTeamId);
  const homeId = normalizeTeamId(options.homeTeamId);
  const focusConfig = teamStreamConfig[focusId];
  if (!focusConfig) {
    return undefined;
  }

  const sources: StreamLink[] = [];
  const seen = new Set<string>();

  const pushUnique = (link: StreamLink | null) => {
    if (!link || seen.has(link.url)) return;
    seen.add(link.url);
    sources.push(link);
  };

  // Focus feed first so the default embed is the team the user picked.
  pushUnique(teamFeed(focusId));
  pushUnique(teamFeed(homeId));
  pushUnique(teamFeed(awayId));

  if (options.buffstreams?.streamIds.length) {
    pushUnique({
      label: "Backup",
      url: embedPath(`buff${options.buffstreams.streamIds[0]}`)
    });
  }

  sources.push({
    label: "Open webcast",
    url: webcastStreamUrl(focusConfig.streamSlug),
    external: true
  });

  return {
    livePageUrl:
      options.buffstreams?.pageUrl ?? `${MLB_WEBCAST_ORIGIN}/${focusConfig.liveSlug}-live/`,
    sources
  };
}

function buildTeamStream(
  config: TeamStreamConfig,
  opponentTeamId?: string,
  buffstreams?: BuffstreamsMatch | null,
  focusTeamId?: string
): WatchStreamSource {
  // Legacy path when only a focus + opponent are known.
  const focusId =
    focusTeamId && teamStreamConfig[normalizeTeamId(focusTeamId)]
      ? normalizeTeamId(focusTeamId)
      : Object.entries(teamStreamConfig).find(([, value]) => value.streamSlug === config.streamSlug)?.[0] ??
        "nyy";
  const opponentId = opponentTeamId ? normalizeTeamId(opponentTeamId) : undefined;

  return (
    getMatchupWatchStream({
      focusTeamId: focusId,
      awayTeamId: opponentId ?? focusId,
      homeTeamId: focusId,
      buffstreams
    }) ?? {
      livePageUrl: `${MLB_WEBCAST_ORIGIN}/${config.liveSlug}-live/`,
      sources: [
        { label: getTeam(focusId).abbreviation, url: embedPath(`${config.streamSlug}2`) },
        { label: "Open webcast", url: webcastStreamUrl(config.streamSlug), external: true }
      ]
    }
  );
}

export const mlbNetworkStream: WatchStreamSource = {
  livePageUrl: `${MLB_WEBCAST_ORIGIN}/mlb-network-live/`,
  sources: [
    { label: "MLB Network", url: embedPath("mlbnetwork2") },
    { label: "Open webcast", url: webcastStreamUrl("mlbnetwork"), external: true }
  ]
};

export function getTeamWatchStream(
  teamId: string,
  opponentTeamId?: string,
  buffstreams?: BuffstreamsMatch | null
) {
  const id = normalizeTeamId(teamId);
  const config = teamStreamConfig[id];
  if (!config) {
    return undefined;
  }

  return buildTeamStream(config, opponentTeamId, buffstreams, id);
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
