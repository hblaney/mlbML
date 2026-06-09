import { teams } from "./data";
import { mlbTeamIdToLocalId } from "./standings";

const localTeamIdToMlbId = Object.fromEntries(
  Object.entries(mlbTeamIdToLocalId).map(([mlbId, localId]) => [localId, Number(mlbId)])
) as Record<string, number>;

export function getTeamLogoUrl(teamId: string) {
  const mlbTeamId = localTeamIdToMlbId[teamId];
  return mlbTeamId ? `https://www.mlbstatic.com/team-logos/${mlbTeamId}.svg` : null;
}

export function getWatchTeams() {
  return teams
    .map((team) => ({
      ...team,
      logoUrl: getTeamLogoUrl(team.id)
    }))
    .sort((left, right) => left.name.localeCompare(right.name));
}
