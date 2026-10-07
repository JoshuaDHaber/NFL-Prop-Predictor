import type { GameWeather } from "../api";
import { notableWeather, weatherShort, weatherText, wxEffect } from "../format";

/** A small flag on a row when kickoff weather is notable, with the adjustment it made to this projection. */
export default function WeatherChip({ weather, wx }: { weather?: GameWeather | null; wx?: number | null }) {
  const effect = wxEffect(wx);
  if (!weather || (!notableWeather(weather) && !effect)) return null;
  const text = weatherText(weather);
  const title = `${weather.stadium ? weather.stadium + ": " : ""}${text ?? "forecast"} at kickoff.` +
    (effect ? ` Projection adjusted ${effect} for weather.` : " No adjustment for this market.");
  return (
    <span className={`wx-chip${effect ? (wx! < 1 ? " down" : " up") : ""}`} title={title}>
      {weatherShort(weather)}{effect && <> · {effect}</>}
    </span>
  );
}
