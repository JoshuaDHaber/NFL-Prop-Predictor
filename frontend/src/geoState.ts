// Which US state the device is in: browser geolocation, then a point-in-polygon test against bundled
// state outlines (us-atlas), so the location never leaves the device.

type Ring = [number, number][];
export interface StateShape { code: string; polygons: Ring[][] }

const FIPS: Record<string, string> = {
  "01": "AL", "02": "AK", "04": "AZ", "05": "AR", "06": "CA", "08": "CO", "09": "CT", "10": "DE", "11": "DC",
  "12": "FL", "13": "GA", "15": "HI", "16": "ID", "17": "IL", "18": "IN", "19": "IA", "20": "KS", "21": "KY",
  "22": "LA", "23": "ME", "24": "MD", "25": "MA", "26": "MI", "27": "MN", "28": "MS", "29": "MO", "30": "MT",
  "31": "NE", "32": "NV", "33": "NH", "34": "NJ", "35": "NM", "36": "NY", "37": "NC", "38": "ND", "39": "OH",
  "40": "OK", "41": "OR", "42": "PA", "44": "RI", "45": "SC", "46": "SD", "47": "TN", "48": "TX", "49": "UT",
  "50": "VT", "51": "VA", "53": "WA", "54": "WV", "55": "WI", "56": "WY", "60": "AS", "66": "GU", "69": "MP",
  "72": "PR", "78": "VI",
};

/** Even-odd ray casting over every ring, so holes (lakes, enclaves) count as outside. */
function inside(lon: number, lat: number, rings: Ring[]) {
  let hit = false;
  for (const ring of rings) {
    for (let i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      const [xi, yi] = ring[i], [xj, yj] = ring[j];
      if ((yi > lat) !== (yj > lat) && lon < ((xj - xi) * (lat - yi)) / (yj - yi) + xi) hit = !hit;
    }
  }
  return hit;
}

export function stateAt(lon: number, lat: number, shapes: StateShape[]): string | null {
  return shapes.find((s) => s.polygons.some((p) => inside(lon, lat, p)))?.code ?? null;
}

let shapes: Promise<StateShape[]> | null = null;
export function loadShapes() {
  shapes ??= Promise.all([import("us-atlas/states-10m.json"), import("topojson-client")]).then(([atlas, topo]) => {
    const t = (atlas.default ?? atlas) as unknown as Parameters<typeof topo.feature>[0] & { objects: { states: Parameters<typeof topo.feature>[1] } };
    const fc = topo.feature(t, t.objects.states) as unknown as GeoJSON.FeatureCollection<GeoJSON.Polygon | GeoJSON.MultiPolygon>;
    return fc.features.flatMap((f) => {
      const code = FIPS[String(f.id)];
      if (!code || !f.geometry) return [];
      const polygons = (f.geometry.type === "Polygon" ? [f.geometry.coordinates] : f.geometry.coordinates) as Ring[][];
      return [{ code, polygons }];
    });
  });
  return shapes;
}

export type Located = { state: string } | { error: string };

export async function detectState(): Promise<Located> {
  if (!("geolocation" in navigator) || !window.isSecureContext) return { error: "Location isn't available on this page." };
  const pos = await new Promise<GeolocationPosition | GeolocationPositionError>((resolve) =>
    navigator.geolocation.getCurrentPosition(resolve, resolve, { maximumAge: 10 * 60_000, timeout: 15_000 }));
  if (!("coords" in pos)) return { error: pos.code === pos.PERMISSION_DENIED ? "Location access is blocked." : "Couldn't get your location." };
  const state = stateAt(pos.coords.longitude, pos.coords.latitude, await loadShapes());
  return state ? { state } : { error: "Your location isn't in a US state." };
}
