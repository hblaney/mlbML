"use client";

import { useMemo, useState } from "react";
import { FavoriteButton } from "@/components/FavoriteButton";
import type { Team, TeamStat } from "@/lib/data";
import type { TeamStanding } from "@/lib/standings";

type TeamRow = TeamStat & {
  team: Team;
  standing?: TeamStanding;
  winningPercentage: number;
  displayRunDifferential: number;
  displayLast10: string;
};

type SortKey = "team" | "record" | "runDifferential" | "wrcPlus" | "starterEra" | "bullpenEra" | "last10" | "elo";
type SortDirection = "asc" | "desc";

const columns: { key: SortKey; label: string; numeric?: boolean; lowerIsBetter?: boolean }[] = [
  { key: "team", label: "Team" },
  { key: "record", label: "Record", numeric: true },
  { key: "runDifferential", label: "Run Diff", numeric: true },
  { key: "wrcPlus", label: "wRC+", numeric: true },
  { key: "starterEra", label: "Starter ERA", numeric: true, lowerIsBetter: true },
  { key: "bullpenEra", label: "Bullpen ERA", numeric: true, lowerIsBetter: true },
  { key: "last10", label: "Last 10", numeric: true },
  { key: "elo", label: "Elo", numeric: true }
];

function last10Wins(value: string) {
  return Number(value.split("-")[0] ?? 0);
}

function compareRows(left: TeamRow, right: TeamRow, key: SortKey) {
  if (key === "team") {
    return left.team.name.localeCompare(right.team.name);
  }

  if (key === "record") {
    return left.winningPercentage - right.winningPercentage;
  }

  if (key === "last10") {
    return last10Wins(left.displayLast10) - last10Wins(right.displayLast10);
  }

  if (key === "runDifferential") {
    return left.displayRunDifferential - right.displayRunDifferential;
  }

  return left[key] - right[key];
}

function formatRunDifferential(value: number) {
  return value > 0 ? `+${value}` : value;
}

function recordFor(standing?: Pick<TeamStanding, "wins" | "losses">) {
  return standing ? `${standing.wins}-${standing.losses}` : "Record unavailable";
}

export function StatsClient({
  teams,
  teamStats,
  standings
}: {
  teams: Team[];
  teamStats: TeamStat[];
  standings: TeamStanding[];
}) {
  const [teamQuery, setTeamQuery] = useState("");
  const [sortKey, setSortKey] = useState<SortKey>("elo");
  const [sortDirection, setSortDirection] = useState<SortDirection>("desc");

  const teamById = useMemo(() => new Map(teams.map((team) => [team.id, team])), [teams]);
  const standingsByTeamId = useMemo(
    () => new Map(standings.map((standing) => [standing.teamId, standing])),
    [standings]
  );

  const teamRows = useMemo<TeamRow[]>(() => {
    const query = teamQuery.trim().toLowerCase();

    return teamStats
      .map<TeamRow | null>((stat) => {
        const team = teamById.get(stat.teamId);
        if (!team) {
          return null;
        }

        const standing = standingsByTeamId.get(stat.teamId);

        return {
          ...stat,
          team,
          standing,
          winningPercentage: standing?.winningPercentage ?? 0,
          displayRunDifferential: standing?.runDifferential ?? 0,
          displayLast10: standing?.last10 ?? "-"
        };
      })
      .filter((row): row is TeamRow => row !== null)
      .filter((row) => {
        if (!query) {
          return true;
        }

        return [row.team.name, row.team.shortName, row.team.abbreviation].some((value) =>
          value.toLowerCase().includes(query)
        );
      })
      .sort((left, right) => {
        const base = compareRows(left, right, sortKey);
        return sortDirection === "asc" ? base : -base;
      });
  }, [standingsByTeamId, teamById, teamQuery, teamStats, sortDirection, sortKey]);

  function updateSort(nextKey: SortKey) {
    if (nextKey === sortKey) {
      setSortDirection((current) => (current === "asc" ? "desc" : "asc"));
      return;
    }

    const column = columns.find((item) => item.key === nextKey);
    setSortKey(nextKey);
    setSortDirection(column?.lowerIsBetter ? "asc" : "desc");
  }

  return (
    <>
      <section className="panel stats-controls">
        <label>
          <span>Search teams</span>
          <input
            className="input"
            onChange={(event) => setTeamQuery(event.target.value)}
            placeholder="Dodgers, NYY, Mets..."
            type="search"
            value={teamQuery}
          />
        </label>
      </section>

      <section className="panel">
        <div className="section-heading compact">
          <div>
            <p className="eyebrow">Official standings + model inputs</p>
            <h2>Team Board</h2>
          </div>
          <span>{teamRows.length} teams</span>
        </div>
        <table className="table stats-table">
          <thead>
            <tr>
              {columns.map((column) => (
                <th key={column.key}>
                  <button className="sort-button" onClick={() => updateSort(column.key)} type="button">
                    {column.label}
                    {sortKey === column.key ? <span>{sortDirection === "asc" ? "Asc" : "Desc"}</span> : null}
                  </button>
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {teamRows.map((stat) => (
              <tr key={stat.teamId}>
                <td>
                  <div className="team-row">
                    <FavoriteButton kind="team" label={stat.team.name} teamId={stat.teamId} />
                    <span className="dot" style={{ background: stat.team.primary }} />
                    <strong>{stat.team.name}</strong>
                    <span className="team-record">{recordFor(stat.standing)}</span>
                  </div>
                </td>
                <td>
                  {recordFor(stat.standing)}
                  <p className="muted">{(stat.winningPercentage * 100).toFixed(1)}%</p>
                </td>
                <td>{formatRunDifferential(stat.displayRunDifferential)}</td>
                <td>{stat.wrcPlus}</td>
                <td>{stat.starterEra.toFixed(2)}</td>
                <td>{stat.bullpenEra.toFixed(2)}</td>
                <td>{stat.displayLast10}</td>
                <td>{stat.elo}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </section>

    </>
  );
}
