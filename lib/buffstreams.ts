import { GamePrediction } from "./data";

const BUFFSTREAMS_ORIGIN = "https://buffstreams.plus";
const BUFFSTREAMS_MLB_LIST = `${BUFFSTREAMS_ORIGIN}/mlb-live-streams`;

export type BuffstreamsMatch = {
  pageUrl: string;
  streamIds: string[];
};

const buffstreamsSlugByTeamId: Record<string, string> = {
  ari: "arizona-diamondbacks",
  ath: "athletics",
  atl: "atlanta-braves",
  bal: "baltimore-orioles",
  bos: "boston-red-sox",
  chc: "chicago-cubs",
  cws: "chicago-white-sox",
  cin: "cincinnati-reds",
  cle: "cleveland-guardians",
  col: "colorado-rockies",
  det: "detroit-tigers",
  hou: "houston-astros",
  kc: "kansas-city-royals",
  laa: "los-angeles-angels",
  lad: "los-angeles-dodgers",
  mia: "miami-marlins",
  mil: "milwaukee-brewers",
  min: "minnesota-twins",
  nym: "new-york-mets",
  nyy: "new-york-yankees",
  phi: "philadelphia-phillies",
  pit: "pittsburgh-pirates",
  sd: "san-diego-padres",
  sf: "san-francisco-giants",
  sea: "seattle-mariners",
  stl: "st-louis-cardinals",
  tb: "tampa-bay-rays",
  tex: "texas-rangers",
  tor: "toronto-blue-jays",
  wsh: "washington-nationals"
};

function matchupMatchesSlug(slug: string, awayTeamId: string, homeTeamId: string) {
  const awaySlug = buffstreamsSlugByTeamId[awayTeamId];
  const homeSlug = buffstreamsSlugByTeamId[homeTeamId];

  if (!awaySlug || !homeSlug) {
    return false;
  }

  return slug.includes(awaySlug) && slug.includes(homeSlug);
}

function parseStreamIds(html: string) {
  const ids = new Set<string>();

  for (const match of html.matchAll(/stream-btn-(\d+)/g)) {
    ids.add(match[1]);
  }

  for (const match of html.matchAll(/changeStream\((\d+)\)/g)) {
    ids.add(match[1]);
  }

  return [...ids];
}

async function fetchBuffstreamsHtml(url: string) {
  const response = await fetch(url, {
    next: { revalidate: 120 },
    headers: {
      "User-Agent":
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36",
      Accept: "text/html,application/xhtml+xml"
    }
  });

  if (!response.ok) {
    return null;
  }

  return response.text();
}

export async function resolveBuffstreamsForGame(game: GamePrediction): Promise<BuffstreamsMatch | null> {
  const listHtml = await fetchBuffstreamsHtml(BUFFSTREAMS_MLB_LIST);
  if (!listHtml) {
    return null;
  }

  const gameLinks = [...listHtml.matchAll(/href="(https:\/\/buffstreams\.plus\/mlb\/([^/]+)\/\d+)"/g)];

  for (const [, pageUrl, slug] of gameLinks) {
    if (!matchupMatchesSlug(slug, game.awayTeam, game.homeTeam)) {
      continue;
    }

    const pageHtml = await fetchBuffstreamsHtml(pageUrl);
    if (!pageHtml) {
      continue;
    }

    const streamIds = parseStreamIds(pageHtml);
    if (streamIds.length === 0) {
      continue;
    }

    return { pageUrl, streamIds };
  }

  return null;
}
