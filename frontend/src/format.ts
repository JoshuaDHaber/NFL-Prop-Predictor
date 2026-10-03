import type { Kind } from "./api";

export const KIND_LABEL: Record<Kind, string> = {
  rush: "Rushing yds", rec: "Receiving yds", pass: "Passing yds", rr: "Rush+Rec yds",
};
export const KIND_SHORT: Record<Kind, string> = { rush: "Rushing", rec: "Receiving", pass: "Passing", rr: "Rush+Rec" };

export const pct = (x: number, digits = 1) => `${(x * 100).toFixed(digits)}%`;
export const signedPct = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(1)}%`;
export const signed = (x: number, digits = 1) => `${x >= 0 ? "+" : ""}${x.toFixed(digits)}`;
export const americanOdds = (o: number) => (o > 0 ? `+${o}` : `${o}`);
export const matchup = (opp: string, home: boolean) => `${home ? "vs" : "@"} ${opp}`;

export function kickoff(gameday: string, gametime: string): string {
  const d = new Date(`${gameday}T12:00:00`);
  const day = isNaN(d.getTime()) ? "" : d.toLocaleDateString("en-US", { weekday: "short" });
  return [day, gametime].filter(Boolean).join(" ");
}

export function timeAgo(iso: string, now = Date.now()): string {
  const mins = Math.max(0, Math.round((now - new Date(iso + "Z").getTime()) / 60000));
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins} min ago`;
  if (mins < 60 * 48) return `${Math.round(mins / 60)} h ago`;
  return `${Math.round(mins / 1440)} d ago`;
}
