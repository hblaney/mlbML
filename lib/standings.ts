export type TeamStanding = {
  teamId: string;
  wins: number;
  losses: number;
  winningPercentage: number;
  runDifferential: number;
  divisionRank: string;
  leagueRank: string;
  wildCardRank?: string;
  gamesBack: string;
  divisionName: string;
  last10: string;
};

export const mlbTeamIdToLocalId: Record<number, string> = {
  108: "laa",
  109: "ari",
  110: "bal",
  111: "bos",
  112: "chc",
  113: "cin",
  114: "cle",
  115: "col",
  116: "det",
  117: "hou",
  118: "kc",
  119: "lad",
  120: "wsh",
  121: "nym",
  133: "ath",
  134: "pit",
  135: "sd",
  136: "sea",
  137: "sf",
  138: "stl",
  139: "tb",
  140: "tex",
  141: "tor",
  142: "min",
  143: "phi",
  144: "atl",
  145: "cws",
  146: "mia",
  147: "nyy",
  158: "mil"
};

type MlbTeamRecord = {
  team: { id: number };
  wins: number;
  losses: number;
  winningPercentage?: string;
  runDifferential?: number;
  divisionRank?: string;
  leagueRank?: string;
  wildCardRank?: string;
  gamesBack?: string;
  records?: {
    splitRecords?: {
      type: string;
      wins: number;
      losses: number;
    }[];
  };
};

type MlbStandingResponse = {
  records?: {
    division?: { name?: string };
    teamRecords?: MlbTeamRecord[];
  }[];
};

function formatLast10(record: MlbTeamRecord) {
  const lastTen = record.records?.splitRecords?.find((split) => split.type === "lastTen");
  return lastTen ? `${lastTen.wins}-${lastTen.losses}` : "-";
}

export function formatStandingRecord(standing?: Pick<TeamStanding, "wins" | "losses">) {
  return standing ? `${standing.wins}-${standing.losses}` : "Record unavailable";
}

export async function loadLiveStandings(): Promise<TeamStanding[]> {
  const season = new Date().getFullYear();
  const url = `https://statsapi.mlb.com/api/v1/standings?leagueId=103,104&season=${season}&standingsTypes=regularSeason`;

  try {
    const response = await fetch(url, { cache: "no-store" });

    if (!response.ok) {
      return [];
    }

    const data = (await response.json()) as MlbStandingResponse;

    return (data.records ?? []).flatMap((division) =>
      (division.teamRecords ?? []).flatMap((record) => {
        const teamId = mlbTeamIdToLocalId[record.team.id];

        if (!teamId) {
          return [];
        }

        return {
          teamId,
          wins: record.wins,
          losses: record.losses,
          winningPercentage: Number(record.winningPercentage ?? 0),
          runDifferential: record.runDifferential ?? 0,
          divisionRank: record.divisionRank ?? "-",
          leagueRank: record.leagueRank ?? "-",
          wildCardRank: record.wildCardRank,
          gamesBack: record.gamesBack ?? "-",
          divisionName: division.division?.name ?? "MLB",
          last10: formatLast10(record)
        };
      })
    );
  } catch {
    return [];
  }
}
