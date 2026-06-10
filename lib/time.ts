export function formatCentralGameTime(startsAt: string) {
  return new Intl.DateTimeFormat("en-US", {
    month: "short",
    day: "numeric",
    year: "numeric",
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Chicago",
    timeZoneName: "short"
  }).format(new Date(startsAt));
}

export function formatCentralDate(value: Date | string = new Date()) {
  return new Intl.DateTimeFormat("en-US", {
    month: "numeric",
    day: "numeric",
    year: "numeric",
    timeZone: "America/Chicago"
  }).format(typeof value === "string" ? new Date(value) : value);
}

function formatCentralWatchDateTime(startsAt: string) {
  const date = new Date(startsAt);
  const datePart = new Intl.DateTimeFormat("en-US", {
    month: "numeric",
    day: "numeric",
    timeZone: "America/Chicago"
  }).format(date);
  const timePart = new Intl.DateTimeFormat("en-US", {
    hour: "numeric",
    minute: "2-digit",
    timeZone: "America/Chicago",
    timeZoneName: "short"
  }).format(date);

  return `${datePart} @ ${timePart}`;
}

export function formatCentralGameSchedule(startsAt: string, opponentAbbrev?: string) {
  const schedule = formatCentralWatchDateTime(startsAt);

  if (!opponentAbbrev) {
    return schedule;
  }

  return `${schedule} vs. ${opponentAbbrev}`;
}
