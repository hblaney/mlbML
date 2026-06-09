type MlbPerson = {
  id: number;
  fullName: string;
  active?: boolean;
  primaryNumber?: string;
  primaryPosition?: { name?: string; abbreviation?: string };
  batSide?: { code?: string };
  pitchHand?: { code?: string };
};

type MlbSearchResponse = {
  people?: MlbPerson[];
};

type MlbStatsResponse = {
  stats?: {
    group?: { displayName?: string };
    splits?: {
      team?: { name?: string };
      stat?: Record<string, string | number>;
    }[];
  }[];
};

function pickStats(stats: MlbStatsResponse["stats"], group: "hitting" | "pitching") {
  return stats?.find((item) => item.group?.displayName === group)?.splits?.[0] ?? null;
}

export async function GET(request: Request) {
  const { searchParams } = new URL(request.url);
  const query = searchParams.get("q")?.trim();
  const season = new Date().getFullYear();

  if (!query || query.length < 2) {
    return Response.json({ players: [] });
  }

  try {
    const searchUrl = `https://statsapi.mlb.com/api/v1/people/search?names=${encodeURIComponent(query)}`;
    const searchResponse = await fetch(searchUrl, { cache: "no-store" });

    if (!searchResponse.ok) {
      return Response.json({ players: [] });
    }

    const searchData = (await searchResponse.json()) as MlbSearchResponse;
    const people = (searchData.people ?? []).filter((person) => person.active !== false).slice(0, 8);

    const players = await Promise.all(
      people.map(async (person) => {
        const statsUrl = `https://statsapi.mlb.com/api/v1/people/${person.id}/stats?stats=season&group=hitting,pitching&season=${season}`;
        const statsResponse = await fetch(statsUrl, { cache: "no-store" });
        const statsData = statsResponse.ok ? ((await statsResponse.json()) as MlbStatsResponse) : {};
        const hitting = pickStats(statsData.stats, "hitting");
        const pitching = pickStats(statsData.stats, "pitching");

        return {
          id: person.id,
          name: person.fullName,
          number: person.primaryNumber ?? null,
          position: person.primaryPosition?.abbreviation ?? person.primaryPosition?.name ?? "Player",
          bats: person.batSide?.code ?? null,
          throws: person.pitchHand?.code ?? null,
          team: hitting?.team?.name ?? pitching?.team?.name ?? "Free agent / no season stats",
          headshotUrl: `https://img.mlbstatic.com/mlb-photos/image/upload/w_240,q_auto:best/v1/people/${person.id}/headshot/67/current`,
          hitting: hitting?.stat ?? null,
          pitching: pitching?.stat ?? null
        };
      })
    );

    return Response.json({ players });
  } catch {
    return Response.json({ players: [] });
  }
}
