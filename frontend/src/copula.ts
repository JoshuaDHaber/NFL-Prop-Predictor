import type { Kind } from "./api";

/**
 * Same-game parlay pricing: a Gaussian copula over the legs, with correlations fitted on the backtest (backend
 * engine/correlation.py builds the table and holds the reference implementation these mirror).
 * Each leg keeps its own chance p; it "hits" when a latent standard normal falls below Phi^-1(p), and two legs' latent
 * normals share the correlation for who they are to each other: the same player, teammates or opponents, by market and
 * position. An Under flips its leg's sign. Legs in different games are independent.
 */

/** Pair key -> latent correlation. Empty means price every leg as independent. */
export type CorrTable = Record<string, number>;

/** What the copula needs from a leg (a Pick has all of it). */
export interface CopulaLeg { player_id: string; team: string; game_id: string; kind: Kind; pos: string; side: "Over" | "Under"; prob: number }

export const legDesc = (kind: Kind, pos: string) => `${kind}:${pos === "FB" ? "RB" : pos}`;
export const pairKey = (rel: "same" | "team" | "opp", a: string, b: string) => (a <= b ? `${rel}|${a}|${b}` : `${rel}|${b}|${a}`);

/** The table's correlation for two legs (before their sides are applied); 0 across games or for a pair it doesn't know. */
export function legRho(a: CopulaLeg, b: CopulaLeg, corr: CorrTable): number {
  if (a.game_id !== b.game_id) return 0;
  const rel = a.player_id === b.player_id ? "same" : a.team === b.team ? "team" : "opp";
  return corr[pairKey(rel, legDesc(a.kind, a.pos), legDesc(b.kind, b.pos))] ?? 0;
}

export const normPdf = (x: number) => Math.exp(-0.5 * x * x) / Math.sqrt(2 * Math.PI);

/** Standard normal CDF (W. J. Cody's erfc rational approximation via Hart's algorithm; |error| < 1e-14). */
export function normCdf(x: number): number {
  const z = Math.abs(x);
  let p: number;
  if (z > 37) p = 0;
  else {
    const e = Math.exp(-z * z / 2);
    if (z < 7.07106781186547) {
      const n = ((((((0.0352624965998911 * z + 0.700383064443688) * z + 6.37396220353165) * z + 33.912866078383) * z + 112.079291497871) * z + 221.213596169931) * z + 220.206867912376);
      const d = (((((((0.0883883476483184 * z + 1.75566716318264) * z + 16.064177579207) * z + 86.7807322029461) * z + 296.564248779674) * z + 637.333633378831) * z + 793.826512519948) * z + 440.413735824752);
      p = e * n / d;
    } else {
      p = e / (z + 1 / (z + 2 / (z + 3 / (z + 4 / (z + 0.65))))) / 2.506628274631;
    }
  }
  return x > 0 ? 1 - p : p;
}

/** Inverse standard normal CDF (Acklam's algorithm, one Newton step: |error| < 1e-12). */
export function normInv(p: number): number {
  if (p <= 0) return -Infinity;
  if (p >= 1) return Infinity;
  const a = [-39.69683028665376, 220.9460984245205, -275.9285104469687, 138.357751867269, -30.66479806614716, 2.506628277459239];
  const b = [-54.47609879822406, 161.5858368580409, -155.6989798598866, 66.80131188771972, -13.28068155288572];
  const c = [-0.007784894002430293, -0.3223964580411365, -2.400758277161838, -2.549732539343734, 4.374664141464968, 2.938163982698783];
  const d = [0.007784695709041462, 0.3224671290700398, 2.445134137142996, 3.754408661907416];
  const lo = 0.02425;
  let x: number;
  if (p < lo) {
    const q = Math.sqrt(-2 * Math.log(p));
    x = (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  } else if (p <= 1 - lo) {
    const q = p - 0.5, r = q * q;
    x = (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1);
  } else {
    const q = Math.sqrt(-2 * Math.log(1 - p));
    x = -(((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1);
  }
  const e = normCdf(x) - p;
  return x - e * Math.sqrt(2 * Math.PI) * Math.exp(x * x / 2);   // Newton step
}

/**
 * Chance every leg hits: P(all X_i < Phi^-1(p_i)) with X ~ N(0, R), R_ij = s_i s_j rho_ij (s = -1 for an Under).
 * Mendell-Elston: condition on one leg at a time, likeliest to miss first, standing in a normal with the truncated leg's
 * mean and variance. Deterministic and fast enough to run inside the ladder search; within about a tenth of a point of
 * simulation for the correlations in the table (backend tests check the Python twin against simulation).
 */
export function jointProb(probs: number[], signs: number[], rho: number[][]): number {
  const n = probs.length;
  if (!n) return 1;
  const order = probs.map((_, i) => i).sort((i, j) => probs[i] - probs[j]);
  const z = order.map((i) => normInv(Math.min(Math.max(probs[i], 1e-9), 1 - 1e-9)));
  const r = order.map((i) => order.map((j) => (i === j ? 1 : rho[i][j] * signs[i] * signs[j])));
  let out = 1;
  for (let k = 0; k < n; k++) {
    const pk = normCdf(z[k]);
    out *= pk;
    if (k === n - 1 || pk <= 0) break;
    const a = normPdf(z[k]) / pk;
    const shrink = z[k] * a + a * a;   // the variance truncation removes: 1 - Var(X | X < z)
    const scale: number[] = [];
    for (let i = k + 1; i < n; i++) scale[i] = Math.sqrt(Math.max(1 - r[i][k] * r[i][k] * shrink, 1e-9));
    for (let i = k + 1; i < n; i++) {
      for (let j = i + 1; j < n; j++) {
        r[i][j] = r[j][i] = (r[i][j] - r[i][k] * r[j][k] * shrink) / (scale[i] * scale[j]);
      }
    }
    for (let i = k + 1; i < n; i++) z[i] = (z[i] + r[i][k] * a) / scale[i];
  }
  return out;
}

/** The chance every leg of a parlay hits: legs multiplied, except same-game legs, which go through the copula with `corr`. */
export function parlayProb(legs: CopulaLeg[], corr?: CorrTable): number {
  if (!corr || legs.length < 2) return legs.reduce((q, l) => q * l.prob, 1);
  const rho = legs.map((a) => legs.map((b) => (a === b ? 1 : legRho(a, b, corr))));
  if (rho.every((row, i) => row.every((v, j) => i === j || v === 0))) return legs.reduce((q, l) => q * l.prob, 1);
  return jointProb(legs.map((l) => l.prob), legs.map((l) => (l.side === "Over" ? 1 : -1)), rho);
}
