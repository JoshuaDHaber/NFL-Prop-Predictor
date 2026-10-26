import type { League } from "../league";

/** How the numbers are made, once, on the model page (the footer links here instead of repeating it on every page). */
export default function Methodology({ league = "nfl" }: { league?: League }) {
  return (
    <div className="card prose methodology" id="how-it-works">
      <h3>How the numbers work</h3>
      {league === "nba" ? (
        <p>
          Points, rebounds, assists, threes, steals and blocks = projected minutes × a per-minute rate, recency-weighted and shrunk toward the position's average,
          adjusted for the opponent; PRA, PR and PA are the sums of those projections. Double- and triple-double chances combine each stat's chance of reaching 10,
          calibrated on past games. Teammates' injuries don't move a player's projection yet.
        </p>
      ) : (
        <p>
          Yards (and receptions) = volume × efficiency, recency-weighted and shrunk to position means, adjusted for opponent, game script and, at outdoor
          stadiums, kickoff wind and cold.
        </p>
      )}
      <p>
        Win probabilities come from the backtest's own errors{league === "nba" ? " (threes, steals and blocks: Poisson counts)" : ""}, blended with the
        market's no-vig price. Team win chances come from point-margin ratings and lean heavily on the moneyline market. Large edges usually mean the model is
        missing context. Not betting advice.
      </p>
    </div>
  );
}
