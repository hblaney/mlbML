const MLB_WEBCAST_ORIGIN = "https://mlbwebcast.com";

export type WatchStreamSource = {
  embedUrl: string;
  livePageUrl: string;
  alternates: string[];
};

function teamStream(liveSlug: string, streamSlug: string): WatchStreamSource {
  return {
    embedUrl: `/api/stream/embed/${streamSlug}`,
    livePageUrl: `${MLB_WEBCAST_ORIGIN}/${liveSlug}-live/`,
    alternates: [`/api/stream/embed/${streamSlug}2`, `/api/stream/embed/${streamSlug}3`]
  };
}

export const teamWatchStreams: Record<string, WatchStreamSource> = {
  ari: teamStream("arizona-diamondbacks", "diamondbacks"),
  ath: teamStream("oakland-athletics", "athletics"),
  atl: teamStream("atlanta-braves", "braves"),
  bal: teamStream("baltimore-orioles", "orioles"),
  bos: teamStream("boston-red-sox", "redsox"),
  chc: teamStream("chicago-cubs", "cubs"),
  cws: teamStream("chicago-white-sox", "whitesox"),
  cin: teamStream("cincinnati-reds", "reds"),
  cle: teamStream("cleveland-guardians", "guardians"),
  col: teamStream("colorado-rockies", "rockies"),
  det: teamStream("detroit-tigers", "tigers"),
  hou: teamStream("houston-astros", "astros"),
  kc: teamStream("kansas-city-royals", "royals"),
  laa: teamStream("los-angeles-angels", "angels"),
  lad: teamStream("los-angeles-dodgers", "dodgers"),
  mia: teamStream("miami-marlins", "marlins"),
  mil: teamStream("milwaukee-brewers", "brewers"),
  min: teamStream("minnesota-twins", "twins"),
  nym: teamStream("new-york-mets", "mets"),
  nyy: teamStream("new-york-yankees", "yankees"),
  phi: teamStream("philadelphia-phillies", "phillies"),
  pit: teamStream("pittsburgh-pirates", "pirates"),
  sd: teamStream("san-diego-padres", "padres"),
  sf: teamStream("san-francisco-giants", "giants"),
  sea: teamStream("seattle-mariners", "mariners"),
  stl: teamStream("st-louis-cardinals", "cardinals"),
  tb: teamStream("tampa-bay-rays", "rays"),
  tex: teamStream("texas-rangers", "rangers"),
  tor: teamStream("toronto-blue-jays", "jays"),
  wsh: teamStream("washington-nationals", "nationals")
};

export const mlbNetworkStream: WatchStreamSource = {
  embedUrl: "/api/stream/embed/mlbnetwork",
  livePageUrl: `${MLB_WEBCAST_ORIGIN}/mlb-network-live/`,
  alternates: ["/api/stream/embed/mlbnetwork2", "/api/stream/embed/mlbnetwork3"]
};

export function getTeamWatchStream(teamId: string) {
  return teamWatchStreams[teamId];
}
