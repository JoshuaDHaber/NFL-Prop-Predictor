import type { GameWeather, Kind } from "./api";

export const KIND_LABEL: Record<Kind, string> = {
  rush: "Rushing yds", rec: "Receiving yds", pass: "Passing yds", rr: "Rush+Rec yds", td: "Anytime TD",
};
export const KIND_SHORT: Record<Kind, string> = { rush: "Rushing", rec: "Receiving", pass: "Passing", rr: "Rush+Rec", td: "Anytime TD" };

/** A projection as shown to a reader: yards, or for anytime TD the chance of scoring (mu is a probability there). */
export const fmtProj = (kind: Kind, mu: number) => (kind === "td" ? `${(mu * 100).toFixed(0)}%` : mu.toFixed(0));

/** What a play is called. Yardage is "Over 54.5"; anytime TD is stored as an over 0.5, shown as "Anytime TD" / "No TD". */
export const playLabel = (kind: Kind, side: "Over" | "Under", line: number) =>
  kind === "td" ? (side === "Over" ? "Anytime TD" : "No TD") : `${side} ${line}`;

/** Edge between the projection and the line: yards for yardage markets, percentage points for anytime TD. */
export const fmtEdge = (kind: Kind, edge: number) => `${edge >= 0 ? "+" : ""}${edge.toFixed(1)}${kind === "td" ? " pts" : ""}`;

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

/** "Dome", or the kickoff forecast: "78°F · wind 19 mph (gusts 27) · 40% rain". null when there is nothing to say. */
export function weatherText(w: GameWeather | null | undefined): string | null {
  if (!w) return null;
  if (w.indoor) return w.roof === "dome" ? "Dome" : w.roof === "closed" ? "Roof closed" : w.roof === "retractable" ? "Retractable roof" : null;
  if (w.source !== "forecast" || w.temp == null || w.wind == null) return null;
  const parts = [`${Math.round(w.temp)}°F`, `wind ${Math.round(w.wind)} mph${w.gust != null && w.gust >= w.wind + 5 ? ` (gusts ${Math.round(w.gust)})` : ""}`];
  if ((w.snow ?? 0) > 0.05) parts.push(`snow ${w.snow!.toFixed(1)}"`);
  else if ((w.precip_prob ?? 0) >= 30) parts.push(`${Math.round(w.precip_prob!)}% rain`);
  else if (w.precip_prob == null && (w.precip ?? 0) >= 0.05) parts.push(`rain ${w.precip!.toFixed(2)}"`);
  return parts.join(" · ");
}

/** Worth flagging on a row: wind, cold, or wet enough to matter. */
export function notableWeather(w: GameWeather | null | undefined): boolean {
  if (!w || w.indoor || w.source !== "forecast") return false;
  return (w.wind ?? 0) >= 12 || (w.temp ?? 60) <= 40 || (w.precip_prob ?? 0) >= 60 || (w.snow ?? 0) > 0.05;
}

/** The one condition that stands out, with an icon: "💨 19 mph", "❄️ snow", "🌧️ 70% rain", "🥶 31°F". */
export function weatherShort(w: GameWeather): string {
  if ((w.snow ?? 0) > 0.05) return "❄️ snow";
  if ((w.wind ?? 0) >= 12) return `💨 ${Math.round(w.wind!)} mph`;
  if ((w.precip_prob ?? 0) >= 60) return `🌧️ ${Math.round(w.precip_prob!)}% rain`;
  if ((w.temp ?? 60) <= 40) return `🥶 ${Math.round(w.temp!)}°F`;
  return `💨 ${Math.round(w.wind ?? 0)} mph`;
}

/** The weather adjustment as a percentage ("-22%"), or null when it is (effectively) none. */
export const wxEffect = (wx: number | null | undefined) =>
  wx != null && Math.abs(wx - 1) >= 0.005 ? `${wx > 1 ? "+" : "−"}${Math.abs((wx - 1) * 100).toFixed(0)}%` : null;

const POINTS = ["N", "NNE", "NE", "ENE", "E", "ESE", "SE", "SSE", "S", "SSW", "SW", "WSW", "W", "WNW", "NW", "NNW"];
/** Compass point for a bearing: 300 -> "WNW". */
export const compassPoint = (deg: number) => POINTS[Math.round((((deg % 360) + 360) % 360) / 22.5) % 16];

/** An icon for a sky description; clear skies at night kickoffs (7 pm ET or later) get a moon. */
export function skyIcon(sky: string | null | undefined, gametime = ""): string {
  const s = (sky ?? "").toLowerCase();
  if (s.includes("thunder")) return "⛈️";
  if (s.includes("snow") || s.includes("flurr")) return "🌨️";
  if (/rain|shower|drizzle/.test(s)) return "🌧️";
  if (s.includes("fog")) return "🌫️";
  if (s.includes("overcast") || /^(mostly )?cloudy/.test(s)) return "☁️";
  if (s.includes("partly")) return "⛅";
  return parseInt(gametime, 10) >= 19 ? "🌙" : "☀️";
}
